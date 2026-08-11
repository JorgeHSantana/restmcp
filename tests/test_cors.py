"""Issue #11 — CORS: absent must deny (safe default), empty must not silently
block with [""], and both cases must say so in the log."""
from starlette.testclient import TestClient

from restmcp import Server


def _preflight(server, origin="https://front.example"):
    with TestClient(server.app) as c:
        return c.options("/health", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        })


def test_absent_denies_cross_origin(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    r = _preflight(Server.get_instance())
    assert "access-control-allow-origin" not in r.headers


def test_explicit_star_allows_any_origin(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    r = _preflight(Server.get_instance())
    assert r.headers["access-control-allow-origin"] == "*"


def test_empty_and_separator_only_deny_without_blank_entry(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " , ,")
    r = _preflight(Server.get_instance())
    assert "access-control-allow-origin" not in r.headers


def test_listed_origin_allows_and_strips_blanks(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://front.example, ")
    r = _preflight(Server.get_instance(), origin="https://front.example")
    assert r.headers["access-control-allow-origin"] == "https://front.example"


def test_preflight_passes_through_auth(monkeypatch):
    """Issue #17 — preflight CORS com AUTH_API_KEY ligada.

    O navegador NUNCA manda Authorization no preflight (spec do CORS), então um
    AuthMiddleware que intercepta o OPTIONS devolve 401 antes de o
    CORSMiddleware responder — e o front fica bloqueado MESMO com token válido.
    O preflight (OPTIONS + Access-Control-Request-Method) precisa atravessar a
    auth; a requisição real continua exigindo o Bearer.
    """
    monkeypatch.setenv("CORS_ORIGINS", "https://front.example")
    monkeypatch.setenv("AUTH_API_KEY", "sk_test_1")
    server = Server.get_instance()
    # asgi_app() é o stack de produção — é lá que o AuthMiddleware embrulha tudo.
    with TestClient(server.asgi_app()) as c:
        pre = c.options("/api/anything", headers={
            "Origin": "https://front.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        })
        assert pre.status_code == 200
        assert pre.headers["access-control-allow-origin"] == "https://front.example"
        # a requisição real SEM token continua barrada — o furo é só do preflight
        real = c.get("/api/anything", headers={"Origin": "https://front.example"})
        assert real.status_code == 401
        # e um OPTIONS que NÃO é preflight (sem Access-Control-Request-Method)
        # não ganha passe livre
        fake = c.options("/api/anything")
        assert fake.status_code == 401
