from starlette.testclient import TestClient
from restmcp import Server, Endpoint


def test_asgi_app_serves_rest_and_mcp(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class PingEndpoint(Endpoint):
        mcp_definition = {"name": "ping", "description": "pong",
                          "parameters": {"properties": {}}}
        url = "/mcp/tools/ping"
        method = "POST"

        def callback(self):
            return {"pong": True}

    app = server.asgi_app(mcp_path="/mcp-protocol")
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "1"}}}
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200            # REST
        assert c.post("/mcp/tools/ping", json={}).json()["result"] == {"pong": True}
        r = c.post("/mcp-protocol/", json=init,
                   headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 200                            # MCP handshake (lifespan OK)


def test_get_mcp_memoized_and_asgi_app_idempotent(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class PongEndpoint(Endpoint):
        mcp_definition = {"name": "pong", "description": "ping",
                          "parameters": {"properties": {}}}
        url = "/mcp/tools/pong"
        method = "POST"

        def callback(self):
            return {"ping": True}

    # get_mcp() builds once and reuses the same FastMCP instance.
    assert server.get_mcp() is server.get_mcp()
    # asgi_app() can be called more than once without raising.
    assert server.asgi_app() is not None
    assert server.asgi_app() is not None
