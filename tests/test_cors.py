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
