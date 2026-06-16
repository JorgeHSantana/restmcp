import asyncio
import inspect
from abc import ABC

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from restmcp.exceptions import PythiaException, ValidationError


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
    """HTTP + MCP endpoint. Subclasses auto-register on class definition when url, method, mcp_definition, and callback are all set."""

    disabled: bool = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Endpoint"):
            raise TypeError(
                f"Endpoint subclasses must end with 'Endpoint' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Endpoint'."
            )

        if getattr(cls, "disabled", False):
            return

        _required = ("url", "method", "mcp_definition", "callback")
        if all(vars(cls).get(attr) for attr in _required):
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
                data = await request.json()
            except Exception:
                data = {}
            data = data or {}

            valid_params = self.mcp_definition.get("parameters", {}).get("properties", {})
            parameters = {}

            for key, value in data.items():
                if key not in valid_params:
                    raise ValidationError(f"Invalid parameter: {key}")
                parameters[key] = value

            if inspect.iscoroutinefunction(self.callback):
                result = await self.callback(**parameters)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, lambda: self.callback(**parameters)
                )

            return JSONResponse(jsonable_encoder({
                "tool": self.mcp_definition["name"],
                "result": result,
                "success": True,
            }))

        except PythiaException as e:
            return JSONResponse(jsonable_encoder({
                "error": e.message,
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": e.__class__.__name__,
            }), status_code=e.status_code)

        except Exception as e:
            return JSONResponse(jsonable_encoder({
                "error": str(e),
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": "InternalServerError",
            }), status_code=500)

    def __init__(self):
        from restmcp.server import Server
        from restmcp.rest import _auth_dependency

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
        server.app.add_api_route(
            self.url,
            route_handler,
            methods=[self.method],
            dependencies=[Depends(_auth_dependency)],
        )
        server.register_url_handler(self)
