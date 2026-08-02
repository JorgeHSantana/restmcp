import asyncio
import inspect
from abc import ABC

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from pydantic import ValidationError as PydanticValidationError

from restmcp.exceptions import RestMCPException, ValidationError
from restmcp.logging import Logger
from restmcp.schema import build_arg_model, check_property_name

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
        if isinstance(props, dict):
            for prop_name in props:
                check_property_name(cls_name, prop_name)


class Endpoint(ABC):
    """HTTP + MCP endpoint. Subclasses auto-register on class definition when url,
    method, and callback are set; mcp_definition is inferred from the callback
    signature when not provided explicitly. REST parameters are accepted from
    the query string and/or the JSON body (body wins on conflicts) and are
    validated against mcp_definition before reaching the callback."""

    disabled: bool = False
    # Which transports serve this endpoint. "rest" keeps the tool out of the MCP
    # server AND the /mcp/tools catalog (e.g. write endpoints an agent must not
    # even see); "mcp" registers no HTTP route (agent-only tools). Default
    # "both" — existing endpoints are untouched.
    expose: str = "both"
    _EXPOSE_VALUES = ("rest", "mcp", "both")
    _registered: bool = False  # per-subclass; set after successful registration

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Endpoint"):
            raise TypeError(
                f"Endpoint subclasses must end with 'Endpoint' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Endpoint'."
            )
        expose = vars(cls).get("expose", cls.expose)
        if expose not in cls._EXPOSE_VALUES:
            raise TypeError(
                f"{cls.__name__}: expose must be one of {list(cls._EXPOSE_VALUES)} "
                f"(got: {expose!r})."
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

            # Query filtered to known keys (body-strict, query-tolerant): unknown
            # query keys (tracking params etc.) are ignored, unknown body keys are
            # rejected by the model's extra='forbid'. Body wins on conflicts.
            known = self._arg_model.model_fields
            data = {k: v for k, v in request.query_params.items() if k in known}
            data.update(body)

            try:
                model = self._arg_model(**data)
            except PydanticValidationError as e:
                parts = []
                for err in e.errors():
                    loc = ".".join(str(p) for p in err["loc"]) or "body"
                    parts.append(f"{loc}: {err['msg']}")
                raise ValidationError("; ".join(parts))

            # dict(model): the already-validated values, without model_dump()'s
            # per-request recursive copy of every container.
            result = await run_callback(self.callback, **dict(model))

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

        # Definition errors must surface with the endpoint's name, and as
        # ValueError so __init_subclass__'s TypeError wrapper (which blames
        # __init__ parameters) never swallows them (review findings 3, 4).
        try:
            self._arg_model = build_arg_model(self.mcp_definition)
        except Exception as e:
            raise ValueError(f"{cls.__name__}: invalid mcp_definition — {e}") from e

        # Every declared property reaches the callback (defaults included,
        # matching the MCP transport), so the signature must accept them all —
        # checked here so the mismatch is a registration error, not a
        # per-request 500 (review finding 2).
        sig = inspect.signature(self.callback)
        if not any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        ):
            accepted = {
                p.name
                for p in sig.parameters.values()
                if p.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            }
            rejected = sorted(set(self._arg_model.model_fields) - accepted)
            if rejected:
                raise ValueError(
                    f"{cls.__name__}: callback does not accept declared "
                    f"parameter(s) {', '.join(rejected)} — every mcp_definition "
                    f"property is passed to the callback (defaults included); "
                    f"add the parameter(s) or **kwargs."
                )

        endpoint_self = self

        async def route_handler(request: Request):
            return await endpoint_self._callback(request)

        server = Server.get_instance()
        # Atomic registration (issue #10): in-memory append first (cheap,
        # can't half-fail), ASGI route last, rollback on failure — never a
        # route without a handler or a handler without a route. An "mcp"-only
        # endpoint registers the handler and skips the HTTP route entirely.
        server.register_url_handler(self)
        if self.expose != "mcp":
            try:
                server.app.add_api_route(
                    self.url,
                    route_handler,
                    methods=[self.method],
                    dependencies=[Depends(_auth_dependency)],
                    operation_id=self.mcp_definition["name"],
                    description=self.mcp_definition.get("description"),
                    openapi_extra=_openapi_params(self.mcp_definition, self.method),
                )
            except Exception:
                server.unregister_url_handler(self)
                raise
        cls._registered = True


_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


def _openapi_params(mcp_definition: dict, method: str) -> dict | None:
    """OpenAPI request metadata for a route, from the SAME source MCP publishes.

    The generic ``route_handler(request)`` gives FastAPI nothing to describe, so
    every operation used to come out empty and generated clients (e.g.
    openapi-typescript) had no request types at all. This derives
    ``requestBody``/``parameters`` straight from ``mcp_definition`` — not from
    the pydantic arg model — so the published schema is byte-for-byte the JSON
    Schema the author declared (or inference built), with no pydantic dialect
    quirks, and REST/MCP cannot drift.

    Conventions mirrored from validation: a property without a ``default`` key
    is required (`schema.field_spec_for`); unknown keys are rejected
    (extra='forbid'), hence ``additionalProperties: false``. Response schemas
    are part B of the issue (design pending) and stay out on purpose.
    """
    props = (mcp_definition.get("parameters") or {}).get("properties") or {}
    if not props:
        return None
    required = [n for n, p in props.items() if not (isinstance(p, dict) and "default" in p)]
    if method.upper() in _BODY_METHODS:
        schema: dict = {
            "type": "object",
            "properties": props,
            "additionalProperties": False,
        }
        if required:
            schema["required"] = required
        return {"requestBody": {
            "required": bool(required),
            "content": {"application/json": {"schema": schema}},
        }}
    return {"parameters": [
        {"name": name, "in": "query", "required": name in required, "schema": prop}
        for name, prop in props.items()
    ]}
