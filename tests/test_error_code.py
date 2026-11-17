"""Machine-readable ``code`` in the error envelope (0.7.0).

Every error response — callback exception, internal failure, the framework's
own 401 (middleware and dependency) and 403 (scope) — uses ONE envelope,
``{tool, error, success, error_type, code}``. ``code`` is always present and
``null`` when the exception does not define one, so clients can branch on it
without parsing the human-readable message.
"""
from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.exceptions import NotFoundError, RestMCPException


def _failing_endpoint(exc: Exception):
    class FalhaEndpoint(Endpoint):
        mcp_definition = {"name": "falha", "description": "levanta",
                          "parameters": {"properties": {}}}
        url = "/api/falha"
        method = "POST"

        def callback(self):
            raise exc


def test_rest_envelope_carries_code(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _failing_endpoint(RestMCPException("sem sessão", 503, code="session_expired"))
    with TestClient(Server.get_instance().app) as c:
        r = c.post("/api/falha", json={})
    assert r.status_code == 503
    assert r.json() == {"tool": "falha", "error": "sem sessão", "success": False,
                        "error_type": "RestMCPException", "code": "session_expired"}


def test_rest_envelope_code_is_null_when_unset(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _failing_endpoint(NotFoundError("x"))
    with TestClient(Server.get_instance().app) as c:
        r = c.post("/api/falha", json={})
    assert r.status_code == 404
    assert r.json()["error_type"] == "NotFoundError"
    assert "code" in r.json() and r.json()["code"] is None


def test_internal_error_envelope_has_null_code(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _failing_endpoint(RuntimeError("segredo interno"))
    with TestClient(Server.get_instance().app) as c:
        r = c.post("/api/falha", json={})
    assert r.status_code == 500
    assert r.json()["error"] == "Internal server error"
    assert "code" in r.json() and r.json()["code"] is None


def test_openapi_error_schema_declares_code(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _failing_endpoint(NotFoundError("x"))
    schema = Server.get_instance().app.openapi()
    op = schema["paths"]["/api/falha"]["post"]
    err = op["responses"]["default"]["content"]["application/json"]["schema"]
    assert err["properties"]["code"] == {"type": ["string", "null"]}
    assert "code" in err["required"]
    # tool is null when the error precedes the endpoint (401, app handler)
    assert err["properties"]["tool"] == {"type": ["string", "null"]}
    assert "tool" in err["required"]


# --- the framework's own 401/403 use the same envelope ---

_KEYS = "painel:sk_1:read, campo:sk_2:read+write"
_UNAUTHORIZED = {"tool": None, "error": "Unauthorized", "success": False,
                 "error_type": "UnauthorizedError", "code": "invalid_api_key"}


def _scoped_endpoints():
    class LerCoisaEndpoint(Endpoint):
        mcp_definition = {"name": "ler_coisa", "description": "lê",
                          "parameters": {"properties": {}}}
        url = "/api/ler_coisa"
        method = "GET"

        def callback(self):
            return {"ok": True}

    class GravarCoisaEndpoint(Endpoint):
        required_scope = "write"
        mcp_definition = {"name": "gravar_coisa", "description": "grava",
                          "parameters": {"properties": {}}}
        url = "/api/gravar_coisa"
        method = "POST"

        def callback(self):
            return {"ok": True}


def test_middleware_401_uses_error_envelope(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", _KEYS)
    _scoped_endpoints()
    with TestClient(Server.get_instance().asgi_app()) as c:
        r = c.get("/api/ler_coisa")
    assert r.status_code == 401
    assert r.json() == _UNAUTHORIZED


def test_dependency_401_uses_same_envelope(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", _KEYS)
    _scoped_endpoints()
    # server.app has no AuthMiddleware: the route dependency answers the 401
    with TestClient(Server.get_instance().app) as c:
        r = c.get("/api/ler_coisa", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401
        assert r.json() == _UNAUTHORIZED
        # no Authorization header at all
        r = c.get("/api/ler_coisa")
        assert r.status_code == 401
        assert r.json() == _UNAUTHORIZED
        # non-ASCII token: rejected the same way, never a 500
        r = c.get("/api/ler_coisa",
                  headers={"Authorization": "Bearer tökén".encode("utf-8")})
        assert r.status_code == 401
        assert r.json() == _UNAUTHORIZED


def test_scope_403_has_forbidden_scope_code(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", _KEYS)
    _scoped_endpoints()
    with TestClient(Server.get_instance().app) as c:
        r = c.post("/api/gravar_coisa", json={},
                   headers={"Authorization": "Bearer sk_1"})
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden_scope"
    assert r.json()["error_type"] == "ForbiddenError"
    assert r.json()["tool"] == "gravar_coisa"


def test_public_paths_still_open(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", _KEYS)
    with TestClient(Server.get_instance().asgi_app()) as c:
        assert c.get("/health").status_code == 200


def test_app_handler_renders_restmcp_exception_outside_callback(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    app = Server.get_instance().app

    @app.get("/plain")
    def plain_route():
        raise RestMCPException("manutenção", 503, code="maintenance")

    with TestClient(app) as c:
        r = c.get("/plain")
    assert r.status_code == 503
    assert r.json() == {"tool": None, "error": "manutenção", "success": False,
                        "error_type": "RestMCPException", "code": "maintenance"}


# --- subclasses written for 0.6.x (no super().__init__) keep working --------
# 0.6.1 read only ``message`` and ``status_code`` (REST) and nothing at all over
# MCP (fastmcp rendered the exception). The envelope now also reads ``code``;
# a subclass that never called RestMCPException.__init__ must not turn into a
# bare 500 because of it.

class LegacyTeapot(RestMCPException):
    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message
        self.status_code = 418


class LegacyBare(RestMCPException):
    """Sets nothing restmcp-specific: 0.6.1 served it over MCP unchanged."""

    def __init__(self, message):
        Exception.__init__(self, message)


def _mcp_result(tool):
    import json

    app = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")
    h = {"Accept": "application/json, text/event-stream"}
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "1"}}}
    with TestClient(app) as c:
        r = c.post("/mcp-protocol/", json=init, headers=h)
        h = {**h, "mcp-session-id": r.headers["mcp-session-id"]}
        c.post("/mcp-protocol/", headers=h,
               json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = c.post("/mcp-protocol/", headers=h, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool, "arguments": {}}})
    data = [l for l in r.text.splitlines() if l.startswith("data:")]
    return json.loads(data[-1][len("data:"):])["result"]


def test_legacy_subclass_without_super_init_over_rest(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _failing_endpoint(LegacyTeapot("teapot"))
    with TestClient(Server.get_instance().app) as c:
        r = c.post("/api/falha", json={})
    assert r.status_code == 418
    assert r.json() == {"tool": "falha", "error": "teapot", "success": False,
                        "error_type": "LegacyTeapot", "code": None}


def test_legacy_subclass_without_super_init_over_mcp(monkeypatch):
    import pytest

    pytest.importorskip("fastmcp")
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _failing_endpoint(LegacyTeapot("teapot"))
    result = _mcp_result("falha")
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "tool": "falha", "error": "teapot", "success": False,
        "error_type": "LegacyTeapot", "code": None}


def test_bare_subclass_over_mcp_and_rest(monkeypatch):
    """Neither message, status_code nor code set: the text falls back to
    str(exc), the status to 500 — still the envelope, never a bare 500."""
    import pytest

    pytest.importorskip("fastmcp")
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _failing_endpoint(LegacyBare("sem detalhes"))
    expected = {"tool": "falha", "error": "sem detalhes", "success": False,
                "error_type": "LegacyBare", "code": None}
    result = _mcp_result("falha")
    assert result["isError"] is True
    assert result["structuredContent"] == expected
    with TestClient(Server.get_instance().app) as c:
        r = c.post("/api/falha", json={})
    assert r.status_code == 500
    assert r.json() == expected
