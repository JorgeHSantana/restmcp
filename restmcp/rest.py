import datetime as dt
import os
from typing import Any, List

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware


def _package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("restmcp")
    except PackageNotFoundError:
        return "0.0.0"


def _validate_api_key(raw_key: str) -> bool:
    from restmcp.auth import _valid_token
    return _valid_token(raw_key)


def serves_mcp(handler) -> bool:
    """Single source of the expose filter: is this handler part of the MCP
    surface? Used by both the /mcp/tools catalog and Server.mcp_handlers so
    the two can never disagree."""
    return getattr(handler, "expose", "both") != "rest"


def _auth_dependency(request: Request):
    if not os.getenv("AUTH_API_KEY"):
        return
    auth_header = request.headers.get("Authorization")
    api_key = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else None
    if not api_key or not _validate_api_key(api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


class RestApp:
    """FastAPI application with CORS, auth dependency, and default routes (/health, /mcp/tools)."""

    def __init__(self):
        self.app = FastAPI()
        cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.url_handlers: List[Any] = []
        self._setup_default_routes()

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
                    # the catalog advertises the MCP surface (serves_mcp —
                    # the same predicate Server.mcp_handlers uses)
                    for h in self.url_handlers
                    if serves_mcp(h)
                ],
                "server": "restmcp",
                "version": _package_version(),
            }

        @self.app.get("/health")
        def health_check():
            return {
                "status": "healthy",
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }

    def register_handler(self, handler: Any):
        self.url_handlers.append(handler)

    def unregister_handler(self, handler: Any):
        if handler in self.url_handlers:
            self.url_handlers.remove(handler)
