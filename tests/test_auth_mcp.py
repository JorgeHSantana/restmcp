from starlette.testclient import TestClient
from restmcp import Server, Endpoint


def _ping_endpoint():
    class PingEndpoint(Endpoint):
        mcp_definition = {"name": "ping", "description": "pong",
                          "parameters": {"properties": {}}}
        url = "/mcp/tools/ping"
        method = "POST"

        def callback(self):
            return {"pong": True}
    return PingEndpoint


_MCP_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "t", "version": "1"}}}


def test_mcp_exige_token_quando_auth_ligada(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "sk_test")
    server = Server.get_instance()
    _ping_endpoint()

    app = server.asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200                           # público

        r = c.post("/mcp-protocol/", json=_MCP_INIT,
                   headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 401                                          # MCP sem token

        r = c.post("/mcp-protocol/", json=_MCP_INIT,
                   headers={"Accept": "application/json, text/event-stream",
                            "Authorization": "Bearer sk_test"})
        assert r.status_code == 200                                          # com token OK


def test_sem_auth_key_nao_exige_token(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()
    _ping_endpoint()

    app = server.asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        r = c.post("/mcp-protocol/", json=_MCP_INIT,
                   headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 200                                          # sem key = livre


def test_rest_sem_token_bloqueado_quando_auth_ligada(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "sk_test")
    server = Server.get_instance()
    _ping_endpoint()

    app = server.asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        r = c.post("/mcp/tools/ping", json={})
        assert r.status_code == 401                                          # REST protegido

        r = c.post("/mcp/tools/ping", json={},
                   headers={"Authorization": "Bearer sk_test"})
        assert r.status_code == 200                                          # com token OK
