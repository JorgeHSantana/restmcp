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
