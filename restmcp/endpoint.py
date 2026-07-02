import asyncio
import inspect
from abc import ABC

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from restmcp.exceptions import RestMCPException, ValidationError
from restmcp.logging import Logger

_logger = Logger("restmcp.endpoint")


async def run_callback(callback: object, /, **kwargs):
    """Invoke an Endpoint callback under restmcp's sync/async contract.

    The contract (identical for REST and MCP):
    - **async callback** -> awaited directly. Keep its I/O async; do not call
      blocking code inside it, or you will stall the event loop.
    - **sync callback** -> run in the default threadpool, so a blocking
      Repository/DataSource call (e.g. a synchronous DB driver) never blocks the
      loop. A plain `def callback` doing blocking I/O is therefore correct.
    """
    if inspect.iscoroutinefunction(callback):
        return await callback(**kwargs)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: callback(**kwargs))


def _coerce_param(name: str, value: object, schema: dict):
    """Validate/coerce one REST parameter against its mcp_definition schema.

    JSON body values arrive typed; query-string values (Task: GET support)
    arrive as str and are coerced to the declared type. Mirrors the MCP path,
    where pydantic enforces the same schema. Raises ValidationError (400) on
    mismatch. An explicit null is accepted when the schema declares a default
    (i.e. the parameter is optional).
    """
    expected = schema.get("type", "string")
    if value is None and "default" in schema:
        return None
    if expected == "string":
        if isinstance(value, str):
            return value
    elif expected == "integer":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
    elif expected == "number":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
    elif expected == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
            return value.lower() in ("true", "1")
    elif expected == "array":
        if isinstance(value, list):
            return value
    elif expected == "object":
        if isinstance(value, dict):
            return value
    raise ValidationError(
        f"Invalid value for parameter '{name}': expected {expected}"
    )


def _validate_mcp_definition(cls_name: str, mcp_def: object) -> None:
    if not isinstance(mcp_def, dict):
        raise TypeError(
            f"{cls_name}: mcp_definition must be a dict, got {type(mcp_def).__name__}"
        )
    for key in ("name", "description"):
        val = mcp_def.get(key)
        if not isinstance(val, str) or not val.strip():
            raise TypeError(
                f"{cls_name}: mcp_definition['{key}'] must be a non-empty string"
            )
    params = mcp_def.get("parameters")
    if params is not None:
        if not isinstance(params, dict):
            raise TypeError(
                f"{cls_name}: mcp_definition['parameters'] must be a dict"
            )
        props = params.get("properties")
        if props is not None and not isinstance(props, dict):
            raise TypeError(
                f"{cls_name}: mcp_definition['parameters']['properties'] must be a dict"
            )


class Endpoint(ABC):
    """HTTP + MCP endpoint. Subclasses auto-register on class definition when url,
    method, and callback are set; mcp_definition is inferred from the callback
    signature when not provided explicitly. REST parameters are accepted from
    the query string and/or the JSON body (body wins on conflicts) and are
    validated against mcp_definition before reaching the callback."""

    disabled: bool = False
    _registered: bool = False  # per-subclass; set after successful registration

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Endpoint"):
            raise TypeError(
                f"Endpoint subclasses must end with 'Endpoint' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Endpoint'."
            )

        if getattr(cls, "disabled", False):
            return

        _required = ("url", "method", "callback")
        present = [attr for attr in _required if vars(cls).get(attr)]
        if present and len(present) < len(_required):
            missing = ", ".join(a for a in _required if a not in present)
            raise TypeError(
                f"{cls.__name__}: incomplete endpoint definition — missing: {missing}. "
                f"Define url, method and callback together, or set disabled = True "
                f"on an intermediate base class."
            )
        if len(present) == len(_required):
            if "mcp_definition" not in vars(cls):
                from restmcp.schema import build_mcp_definition, has_returns_doc

                if not has_returns_doc(cls.callback):
                    raise TypeError(
                        f"{cls.__name__}: the callback docstring must document its "
                        f"return value in a 'Returns:' section when mcp_definition "
                        f"is inferred — that text is the only thing the MCP client "
                        f"sees about the output. Example:\n"
                        f'    """One-line summary.\n\n'
                        f"    Returns: what the tool returns.\n"
                        f'    """\n'
                        f"(or set mcp_definition explicitly to override inference)."
                    )
                cls.mcp_definition = build_mcp_definition(cls)
            _validate_mcp_definition(cls.__name__, vars(cls)["mcp_definition"])
            try:
                cls()
            except TypeError as e:
                raise TypeError(
                    f"{cls.__name__}: auto-registration failed. "
                    f"Endpoint subclasses must not define __init__ with parameters — "
                    f"use Service/Repository for dependencies. Original error: {e}"
                ) from e

    async def _callback(self, request: Request):
        try:
            try:
                body = await request.json()
            except Exception:
                body = None
            if body is None:
                body = {}
            if not isinstance(body, dict):
                raise ValidationError("Request body must be a JSON object")

            # Accept parameters from the query string too (GET endpoints have
            # no practical body); JSON body wins on conflicts. Query values
            # are strings — _coerce_param converts them to the declared type.
            data = dict(request.query_params)
            data.update(body)

            valid_params = self.mcp_definition.get("parameters", {}).get("properties", {})
            parameters = {}

            for key, value in data.items():
                if key not in valid_params:
                    raise ValidationError(f"Invalid parameter: {key}")
                parameters[key] = _coerce_param(key, value, valid_params[key])

            # A property without a "default" key is required (same convention
            # the MCP path uses when building the pydantic signature).
            missing = [
                name
                for name, schema in valid_params.items()
                if "default" not in schema and name not in parameters
            ]
            if missing:
                raise ValidationError(
                    f"Missing required parameter(s): {', '.join(sorted(missing))}"
                )

            result = await run_callback(self.callback, **parameters)

            return JSONResponse(jsonable_encoder({
                "tool": self.mcp_definition["name"],
                "result": result,
                "success": True,
            }))

        except RestMCPException as e:
            return JSONResponse(jsonable_encoder({
                "error": e.message,
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": e.__class__.__name__,
            }), status_code=e.status_code)

        except Exception:
            # Full traceback goes to the server log; the client gets a
            # generic message so internals never leak into responses.
            _logger.error(
                "Unhandled error in tool %r", self.mcp_definition["name"], exc_info=True
            )
            return JSONResponse(jsonable_encoder({
                "error": "Internal server error",
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": "InternalServerError",
            }), status_code=500)

    def __init__(self):
        from restmcp.server import Server
        from restmcp.rest import _auth_dependency

        cls = type(self)
        # Idempotency guard (issue #10): a second instantiation (manual call,
        # module reload) must not re-register the route. Checked via vars() so
        # a subclass never inherits its parent's "already registered" state.
        if vars(cls).get("_registered", False):
            return

        self.mcp_definition = getattr(self, "mcp_definition", None)
        if not self.mcp_definition:
            raise ValueError(f"{self.__class__.__name__}: mcp_definition is required")

        self.method = getattr(self, "method", None)
        if not self.method:
            raise ValueError(f"{self.__class__.__name__}: method is required")

        self.url = getattr(self, "url", None)
        if not self.url:
            raise ValueError(f"{self.__class__.__name__}: url is required")

        if not getattr(self, "callback", None):
            raise ValueError(f"{self.__class__.__name__}: callback is required")

        endpoint_self = self

        async def route_handler(request: Request):
            return await endpoint_self._callback(request)

        server = Server.get_instance()
        # Atomic registration (issue #10): in-memory append first (cheap,
        # can't half-fail), ASGI route last, rollback on failure — never a
        # route without a handler or a handler without a route.
        server.register_url_handler(self)
        try:
            server.app.add_api_route(
                self.url,
                route_handler,
                methods=[self.method],
                dependencies=[Depends(_auth_dependency)],
            )
        except Exception:
            server.unregister_url_handler(self)
            raise
        cls._registered = True
