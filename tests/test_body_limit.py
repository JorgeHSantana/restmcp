"""Issue #12 — request bodies get a configurable ceiling and a proper 413.

Before: request.json() buffered any size in memory, no 413, no log — and the
framework owns the read path, so apps had nowhere to put a ceiling.
Default 1 MiB via MAX_BODY_BYTES; per-endpoint override via max_body_bytes.
"""
from starlette.testclient import TestClient

from restmcp import Endpoint, Server


def _register(server, **attrs):
    cls = type("SinkEndpoint", (Endpoint,), {
        "mcp_definition": {"name": "sink", "description": "recebe",
                           "parameters": {"properties": {
                               "data": {"type": "string", "default": ""}}}},
        "url": "/api/sink",
        "method": "POST",
        "callback": lambda self, data="": {"size": len(data)},
        **attrs,
    })
    return cls


def test_body_over_default_limit_is_413(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    monkeypatch.setenv("MAX_BODY_BYTES", "1024")
    server = Server.get_instance()
    _register(server)
    with TestClient(server.app) as c:
        big = '{"data": "' + "x" * 2048 + '"}'
        r = c.post("/api/sink", content=big.encode(),
                   headers={"content-type": "application/json"})
        assert r.status_code == 413
        assert r.json()["success"] is False


def test_body_under_limit_passes(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    monkeypatch.setenv("MAX_BODY_BYTES", "1024")
    server = Server.get_instance()
    _register(server)
    with TestClient(server.app) as c:
        r = c.post("/api/sink", json={"data": "ok"})
        assert r.json()["result"] == {"size": 2}


def test_per_endpoint_override_beats_global(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    monkeypatch.setenv("MAX_BODY_BYTES", "1024")
    server = Server.get_instance()
    _register(server, max_body_bytes=4096)
    with TestClient(server.app) as c:
        payload = '{"data": "' + "x" * 2048 + '"}'
        r = c.post("/api/sink", content=payload.encode(),
                   headers={"content-type": "application/json"})
        assert r.status_code == 200
