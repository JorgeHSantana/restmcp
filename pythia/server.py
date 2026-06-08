import datetime as dt
import os
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware


def _validate_api_key(raw_key: str) -> bool:
    env_keys = os.getenv("AUTH_API_KEY", "")
    return bool(raw_key) and raw_key in [k.strip() for k in env_keys.split(",") if k.strip()]


def _auth_dependency(request: Request):
    if not os.getenv("AUTH_API_KEY"):
        return
    auth_header = request.headers.get("Authorization")
    api_key = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else None
    if not api_key or not _validate_api_key(api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


class Server:
    _instance: Optional["Server"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.url_handlers: List = []
        self._setup_default_routes()
        self._initialized = True

    def _setup_default_routes(self):
        @self.app.get("/mcp/tools")
        def list_tools():
            return {
                "tools": [
                    {
                        "name": h.mcp_definition["name"],
                        "description": h.mcp_definition["description"],
                        "parameters": h.mcp_definition["parameters"],
                        "returns": h.mcp_definition.get("returns", {}),
                    }
                    for h in self.url_handlers
                ],
                "server": "pythia",
                "version": "0.1.0",
            }

        @self.app.get("/health")
        def health_check():
            return {
                "status": "healthy",
                "timestamp": dt.datetime.utcnow().isoformat(),
            }

    def register_url_handler(self, handler: Any):
        self.url_handlers.append(handler)

    def start(self, host: str = "0.0.0.0", port: int = 5000, debug: bool = True):
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)

    def get_mcp(self):
        from fastmcp import FastMCP

        mcp = FastMCP("pythia")
        for handler in self.url_handlers:
            self._register_fastmcp_tool(mcp, handler)
        return mcp

    def _register_fastmcp_tool(self, mcp: Any, handler: Any):
        from pydantic import Field, create_model
        from typing import List, Optional
        import inspect

        def_dict = handler.mcp_definition
        name = def_dict["name"]
        description = def_dict["description"]
        properties = def_dict.get("parameters", {}).get("properties", {})

        pydantic_fields = {}
        for prop_name, prop_data in properties.items():
            ptype = prop_data.get("type")
            py_type = str
            if ptype == "integer":
                py_type = int
            elif ptype == "boolean":
                py_type = bool
            elif ptype == "array":
                item_type = int if prop_data.get("items", {}).get("type") == "integer" else str
                py_type = List[item_type]

            default_val = prop_data.get("default", ...)
            if default_val is None:
                py_type = Optional[py_type]

            pydantic_fields[prop_name] = (
                py_type,
                Field(default=default_val, description=prop_data.get("description", "")),
            )

        ModelClass = create_model(f"{name}_args", **pydantic_fields)

        def tool_wrapper(args: ModelClass) -> dict:
            return handler.callback(**args.model_dump())

        tool_wrapper.__name__ = name
        tool_wrapper.__doc__ = description
        sig = inspect.signature(tool_wrapper)
        new_param = inspect.Parameter(
            "args", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ModelClass
        )
        tool_wrapper.__signature__ = sig.replace(parameters=(new_param,))
        mcp.add_tool(tool_wrapper)

    @classmethod
    def get_instance(cls) -> "Server":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls):
        cls._instance = None
