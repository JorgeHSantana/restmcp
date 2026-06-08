import asyncio
import inspect
from abc import ABC

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from pythia.exceptions import PythiaException, ValidationError


class Endpoint(ABC):
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
            cls()

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

            return JSONResponse({
                "tool": self.mcp_definition["name"],
                "result": result,
                "success": True,
            })

        except PythiaException as e:
            return JSONResponse({
                "error": e.message,
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": e.__class__.__name__,
            }, status_code=e.status_code)

        except Exception as e:
            return JSONResponse({
                "error": str(e),
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": "InternalServerError",
            }, status_code=500)

    def __init__(self):
        from pythia.server import Server, _auth_dependency

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
