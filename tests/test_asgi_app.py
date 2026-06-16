from starlette.testclient import TestClient
from restmcp import Server, Endpoint


def test_asgi_app_serve_rest_e_mcp(monkeypatch):
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
        r = c.post("/mcp-protocol/mcp", json=init,
                   headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 200                            # MCP handshake (lifespan OK)
