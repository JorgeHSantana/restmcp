from typing import Any, Literal, Optional

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

    def asgi_app(
        self,
        mcp_path: str = "/mcp-protocol",
        transport: Literal["http", "streamable-http", "sse"] = "http",
        public_paths: tuple[str, ...] = ("/health", "/mcp/tools"),
    ) -> Any:  # returns a Starlette app; annotated as Any to avoid importing it
        """Return one ASGI app serving REST (at '/') and MCP (at `mcp_path`).

        Holds the FastMCP lifespan in the parent app, which prevents the
        'Task group is not initialized' error you get when mounting MCP onto the
        FastAPI app directly. The MCP endpoint is served exactly at `mcp_path`
        (clients connect there). `transport`: 'http' (Streamable HTTP, the
        fastmcp 3.x default), 'streamable-http' (fastmcp 2.x alias) or 'sse'.

        When AUTH_API_KEY is set, the whole app is wrapped in AuthMiddleware,
        protecting REST and the mounted MCP; `public_paths` stay open (the REST
        `/health` and `/mcp/tools` routes by default).

        Call this at most once per process: each call builds a fresh FastMCP
        instance via get_mcp().
        """
        import os
        from starlette.applications import Starlette
        from starlette.routing import Mount

        # path="/" so the MCP app serves at the mount root — i.e. exactly
        # `mcp_path` — instead of FastMCP's default "/mcp" subpath.
        mcp_http = self.get_mcp().http_app(path="/", transport=transport)
        app = Starlette(
            routes=[Mount(mcp_path, app=mcp_http), Mount("/", app=self.app)],
            lifespan=mcp_http.lifespan,
        )
        if os.getenv("AUTH_API_KEY"):
            from restmcp.auth import AuthMiddleware
            app = AuthMiddleware(app, public_paths=public_paths)
        return app

    @classmethod
    def get_instance(cls) -> "Server":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls):
        cls._instance = None
