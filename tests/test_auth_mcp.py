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


def test_mcp_requires_token_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "sk_test")
    server = Server.get_instance()
    _ping_endpoint()

    app = server.asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200                           # public

        r = c.post("/mcp-protocol/", json=_MCP_INIT,
                   headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 401                                          # MCP without token

        r = c.post("/mcp-protocol/", json=_MCP_INIT,
                   headers={"Accept": "application/json, text/event-stream",
                            "Authorization": "Bearer sk_test"})
        assert r.status_code == 200                                          # with token OK


def test_no_auth_key_does_not_require_token(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()
    _ping_endpoint()

    app = server.asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        r = c.post("/mcp-protocol/", json=_MCP_INIT,
                   headers={"Accept": "application/json, text/event-stream"})
        assert r.status_code == 200                                          # no key = open


def test_rest_without_token_blocked_when_auth_enabled(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "sk_test")
    server = Server.get_instance()
    _ping_endpoint()

    app = server.asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        r = c.post("/mcp/tools/ping", json={})
        assert r.status_code == 401                                          # REST protected

        r = c.post("/mcp/tools/ping", json={},
                   headers={"Authorization": "Bearer sk_test"})
        assert r.status_code == 200                                          # with token OK


# --- non-ASCII tokens must be rejected, not crash (hmac.compare_digest on str
# raises TypeError for non-ASCII; we compare UTF-8 bytes instead) ---

def test_valid_token_non_ascii_returns_false(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "secret123")
    from restmcp.auth import _valid_token
    assert _valid_token("café") is False


def test_auth_dependency_non_ascii_token_is_401(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from starlette.requests import Request
    from restmcp.rest import _auth_dependency

    monkeypatch.setenv("AUTH_API_KEY", "secret123")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/x",
        "query_string": b"",
        # latin-1 header value: reaches the dependency as a non-ASCII str
        "headers": [(b"authorization", "Bearer caf\xe9".encode("latin-1"))],
    }
    with pytest.raises(HTTPException) as exc:
        _auth_dependency(Request(scope))
    assert exc.value.status_code == 401
