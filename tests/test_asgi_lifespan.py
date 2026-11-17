"""`asgi_app(lifespan=...)` — the application's startup/shutdown hook.

Apps need somewhere to open and close resources (HTTP clients, pools) around
the server's life. The parent Starlette already holds the FastMCP lifespan
(without it the session manager never starts and MCP fails with "Task group
is not initialized"), so the app's lifespan is chained to it: FastMCP enters
first and exits last; the app's lifespan runs inside it.
"""
import contextlib
import json

import anyio
import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server

pytest.importorskip("fastmcp")

_H = {"Accept": "application/json, text/event-stream"}
_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}}


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)


def _register():
    class PingEndpoint(Endpoint):
        mcp_definition = {"name": "ping", "description": "pong",
                          "parameters": {"properties": {}}}
        url = "/mcp/tools/ping"
        method = "POST"

        def callback(self):
            return {"pong": True}


def _mcp_ping(c):
    """Handshake + a real tools/call: proves the FastMCP session manager runs."""
    r = c.post("/mcp-protocol/", json=_INIT, headers=_H)
    assert r.status_code == 200
    sid = r.headers.get("mcp-session-id")
    h = {**_H, **({"mcp-session-id": sid} if sid else {})}
    c.post("/mcp-protocol/", headers=h,
           json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    r = c.post("/mcp-protocol/", headers=h, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "ping", "arguments": {}}})
    assert r.status_code == 200
    data = [l for l in r.text.splitlines() if l.startswith("data:")]
    payload = json.loads(data[-1][len("data:"):]) if data else r.json()
    return payload["result"]["structuredContent"]


def _recording_lifespan(events):
    @contextlib.asynccontextmanager
    async def lifespan(app):
        events.append("start")
        try:
            yield
        finally:
            events.append("stop")
    return lifespan


def _wrap_fastmcp_lifespan(monkeypatch, server, events, fail_on_exit=False):
    """Record (and optionally break) the FastMCP side of the combined lifespan."""
    mcp = server.get_mcp()
    original = mcp.http_app

    def http_app(*args, **kwargs):
        mcp_http = original(*args, **kwargs)
        inner = mcp_http.router.lifespan_context

        @contextlib.asynccontextmanager
        async def wrapped(app):
            async with inner(app):
                events.append("mcp-start")
                yield
                events.append("mcp-stop")
            if fail_on_exit:
                raise RuntimeError("fastmcp shutdown failed")

        mcp_http.router.lifespan_context = wrapped
        return mcp_http

    monkeypatch.setattr(mcp, "http_app", http_app)


def test_app_lifespan_runs_around_requests():
    _register()
    events = []
    app = Server.get_instance().asgi_app(lifespan=_recording_lifespan(events))
    with TestClient(app) as c:
        assert events == ["start"]
        assert c.get("/health").status_code == 200
        assert _mcp_ping(c) == {"pong": True}   # session manager still started
    assert events == ["start", "stop"]


def test_without_lifespan_behaves_as_before():
    _register()
    app = Server.get_instance().asgi_app()
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.post("/mcp/tools/ping", json={}).json()["result"] == {"pong": True}
        assert _mcp_ping(c) == {"pong": True}


def test_without_lifespan_uses_the_fastmcp_lifespan_unchanged(monkeypatch):
    server = Server.get_instance()
    seen = {}
    original = server.get_mcp().http_app

    def http_app(*args, **kwargs):
        seen["mcp_http"] = original(*args, **kwargs)
        return seen["mcp_http"]

    monkeypatch.setattr(server.get_mcp(), "http_app", http_app)
    app = server.asgi_app()
    assert app.router.lifespan_context is seen["mcp_http"].lifespan


def test_startup_failure_propagates():
    _register()
    handled = []

    @contextlib.asynccontextmanager
    async def lifespan(app):
        raise RuntimeError("sem chave")
        yield

    server = Server.get_instance()

    class SpyEndpoint(Endpoint):
        mcp_definition = {"name": "spy", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/mcp/tools/spy"
        method = "POST"

        def callback(self):
            handled.append(True)
            return {}

    app = server.asgi_app(lifespan=lifespan)
    client = TestClient(app)
    with pytest.raises(RuntimeError, match="sem chave"):
        client.__enter__()
    assert handled == []


def test_startup_failure_still_closes_fastmcp(monkeypatch):
    server = Server.get_instance()
    events = []
    _wrap_fastmcp_lifespan(monkeypatch, server, events)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        events.append("app-start")
        raise RuntimeError("sem chave")
        yield

    with pytest.raises(RuntimeError, match="sem chave"):
        TestClient(server.asgi_app(lifespan=lifespan)).__enter__()
    # FastMCP entered first and shuts down cleanly (no orphan task group); the
    # app's error is still the one raised, not wrapped in an ExceptionGroup.
    assert events == ["mcp-start", "app-start", "mcp-stop"]


def test_order_fastmcp_outside_app_inside(monkeypatch):
    server = Server.get_instance()
    events = []
    _wrap_fastmcp_lifespan(monkeypatch, server, events)
    with TestClient(server.asgi_app(lifespan=_recording_lifespan(events))):
        assert events == ["mcp-start", "start"]
    assert events == ["mcp-start", "start", "stop", "mcp-stop"]


def test_app_shutdown_runs_even_if_fastmcp_shutdown_raises(monkeypatch):
    server = Server.get_instance()
    events = []
    _wrap_fastmcp_lifespan(monkeypatch, server, events, fail_on_exit=True)
    with pytest.raises(RuntimeError, match="fastmcp shutdown failed"):
        with TestClient(server.asgi_app(lifespan=_recording_lifespan(events))):
            pass
    assert events == ["mcp-start", "start", "stop", "mcp-stop"]


def test_error_thrown_at_yield_reaches_app_and_propagates_bare():
    """An exception thrown into the combined lifespan at `yield` is seen by the
    app's lifespan, its shutdown runs, and the original exception propagates —
    not wrapped in the ExceptionGroup of FastMCP's task group."""
    seen = []

    @contextlib.asynccontextmanager
    async def lifespan(app):
        seen.append("start")
        try:
            yield
        except BaseException as exc:
            seen.append(exc)
            raise
        finally:
            seen.append("stop")

    app = Server.get_instance().asgi_app(lifespan=lifespan)
    boom = ZeroDivisionError("boom")

    async def run():
        async with app.router.lifespan_context(app):
            raise boom

    with pytest.raises(ZeroDivisionError) as info:
        anyio.run(run)
    assert info.value is boom
    assert seen == ["start", boom, "stop"]


def test_app_shutdown_error_propagates_bare_and_fastmcp_still_stops(monkeypatch):
    server = Server.get_instance()
    events = []
    _wrap_fastmcp_lifespan(monkeypatch, server, events)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        events.append("start")
        yield
        events.append("stop")
        raise RuntimeError("close failed")

    with pytest.raises(RuntimeError, match="close failed"):
        with TestClient(server.asgi_app(lifespan=lifespan)):
            pass
    assert events == ["mcp-start", "start", "stop", "mcp-stop"]


def test_double_fault_keeps_fastmcp_error_and_notes_the_app_error(monkeypatch):
    server = Server.get_instance()
    events = []
    _wrap_fastmcp_lifespan(monkeypatch, server, events, fail_on_exit=True)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        raise RuntimeError("close failed")

    with pytest.raises(RuntimeError, match="fastmcp shutdown failed") as info:
        with TestClient(server.asgi_app(lifespan=lifespan)):
            pass
    notes = getattr(info.value, "__notes__", [])
    assert any("app lifespan also failed" in n and "close failed" in n
               for n in notes)
    assert events == ["mcp-start", "mcp-stop"]


def test_lifespan_receives_the_parent_app():
    received = []

    @contextlib.asynccontextmanager
    async def lifespan(app):
        app.state.ready = True
        received.append(app)
        yield

    app = Server.get_instance().asgi_app(lifespan=lifespan)
    with TestClient(app):
        pass
    assert received == [app]
    assert app.state.ready is True
