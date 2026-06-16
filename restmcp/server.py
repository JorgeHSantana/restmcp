from typing import Any, Optional

from restmcp.rest import RestApp
from restmcp.mcp import McpApp


class Server:
    """Singleton that composes RestApp and McpApp. Entry point for starting the server and accessing registered endpoints."""

    _instance: Optional["Server"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._rest = RestApp()
        self._mcp = McpApp()
        self._initialized = True

    @property
    def app(self):
        return self._rest.app

    @property
    def url_handlers(self):
        return self._rest.url_handlers

    def register_url_handler(self, handler: Any):
        self._rest.register_handler(handler)

    def start(self, host: str = "0.0.0.0", port: int = 5000, reload: bool = False):
        import uvicorn
        uvicorn.run(self.app, host=host, port=port, reload=reload)

    def get_mcp(self):
        return self._mcp.build(self.url_handlers)

    def asgi_app(self, mcp_path: str = "/mcp-protocol", transport: str = "http"):
        """App ASGI único servindo REST (em `/`) + MCP (em `mcp_path`).

        Detém o lifespan do FastMCP no app pai (evita 'Task group is not
        initialized'). `transport`: 'http' (Streamable, fastmcp 3.x default),
        'streamable-http' (fastmcp 2.x alias) ou 'sse'.
        """
        from starlette.applications import Starlette
        from starlette.routing import Mount

        mcp_http = self.get_mcp().http_app(transport=transport)
        return Starlette(
            routes=[Mount(mcp_path, app=mcp_http), Mount("/", app=self.app)],
            lifespan=mcp_http.lifespan,
        )

    @classmethod
    def get_instance(cls) -> "Server":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls):
        cls._instance = None
