from typing import Any, Optional

from pythia.rest import RestApp
from pythia.mcp import McpApp


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

    @classmethod
    def get_instance(cls) -> "Server":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls):
        cls._instance = None
