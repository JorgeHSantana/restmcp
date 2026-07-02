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
        self._mcp_instance = None
        self._initialized = True

    @property
    def app(self):
        return self._rest.app

    @property
    def url_handlers(self):
        return self._rest.url_handlers

    def register_url_handler(self, handler: Any):
        self._rest.register_handler(handler)

    def unregister_url_handler(self, handler: Any):
        self._rest.unregister_handler(handler)

    def start(self, host: str = "0.0.0.0", port: int = 5000, reload: bool = False):
        if reload:
            raise ValueError(
                "reload=True has no effect when passing an app object to uvicorn "
                "(it requires an import string). Run uvicorn directly instead: "
                "`uvicorn main:app --reload`."
            )
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)

    def get_mcp(self):
        """Return the underlying FastMCP instance (built once, then memoized).

        This is the raw FastMCP object — an escape hatch for advanced use. The
        coupling to FastMCP leaks through here on purpose for now.

        TODO(decouple-mcp): hide FastMCP behind a restmcp-owned protocol so a
        FastMCP major bump (3.x -> 4.x) cannot break callers. The whole
        dependency is already contained in mcp.py + asgi_app(); the remaining
        leak is this return type and asgi_app's reliance on `http_app`/
        `.lifespan`. See issue (full MCP decoupling).
        """
        if self._mcp_instance is None:
            self._mcp_instance = self._mcp.build(self.url_handlers)
        return self._mcp_instance

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

        Idempotent: get_mcp() memoizes the FastMCP instance, so calling this
        more than once reuses the same underlying MCP server.
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
