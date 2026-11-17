"""``required_scope`` must hold on ``tools/call`` too, not just REST.

Until 0.7.0 only ``Endpoint._callback`` (REST) called ``_enforce_scope``: a
``read`` key could run a ``write`` tool by going through MCP instead. These
tests drive a real ``tools/call`` through ``asgi_app()``, sync and async
callbacks alike, and pin that the REST 403 is unchanged.
"""
import json

import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server

_KEYS = "painel:sk_1:read, campo:sk_2:read+write"
_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}}

calls = {"n": 0}


@pytest.fixture(autouse=True)
def _reset_calls():
    calls["n"] = 0


def _register(sync: bool):
    class ReadOnlyEndpoint(Endpoint):
        mcp_definition = {"name": "read_only", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/read-only"
        method = "GET"

        def callback(self):
            return {"ok": True}

    if sync:
        class DangerousEndpoint(Endpoint):
            mcp_definition = {"name": "dangerous", "description": "x",
                              "parameters": {"properties": {}}}
            url = "/api/dangerous"
            method = "POST"
            required_scope = "write"

            def callback(self):
                calls["n"] += 1
                return {"done": True}
    else:
        class DangerousEndpoint(Endpoint):
            mcp_definition = {"name": "dangerous", "description": "x",
                              "parameters": {"properties": {}}}
            url = "/api/dangerous"
            method = "POST"
            required_scope = "write"

            async def callback(self):
                calls["n"] += 1
                return {"done": True}


def _session(c, token):
    h = {"Accept": "application/json, text/event-stream"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = c.post("/mcp-protocol/", json=_INIT, headers=h)
    assert r.status_code == 200
    sid = r.headers.get("mcp-session-id")
    h = {**h, **({"mcp-session-id": sid} if sid else {})}
    c.post("/mcp-protocol/", headers=h,
           json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return h


def _call_tool(c, headers, name):
    r = c.post("/mcp-protocol/", headers=headers, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": name, "arguments": {}}})
    assert r.status_code == 200
    data = [l for l in r.text.splitlines() if l.startswith("data:")]
    payload = json.loads(data[-1][len("data:"):]) if data else r.json()
    return payload["result"]


def _app(monkeypatch, sync, keys=_KEYS):
    pytest.importorskip("fastmcp")
    if keys is None:
        monkeypatch.delenv("AUTH_API_KEY", raising=False)
    else:
        monkeypatch.setenv("AUTH_API_KEY", keys)
    _register(sync)
    return Server.get_instance().asgi_app(mcp_path="/mcp-protocol")


@pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
def test_read_key_cannot_call_write_tool_over_mcp(monkeypatch, sync):
    with TestClient(_app(monkeypatch, sync)) as c:
        result = _call_tool(c, _session(c, "sk_1"), "dangerous")
    assert result["isError"] is True
    sc = result["structuredContent"]
    assert sc["code"] == "forbidden_scope"
    assert sc["error_type"] == "ForbiddenError"
    assert sc["tool"] == "dangerous"
    assert calls["n"] == 0


@pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
def test_write_key_calls_write_tool_over_mcp(monkeypatch, sync):
    with TestClient(_app(monkeypatch, sync)) as c:
        result = _call_tool(c, _session(c, "sk_2"), "dangerous")
    assert not result.get("isError")
    assert result["structuredContent"] == {"done": True}
    assert calls["n"] == 1


@pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
def test_read_key_calls_read_tool_over_mcp(monkeypatch, sync):
    with TestClient(_app(monkeypatch, sync)) as c:
        result = _call_tool(c, _session(c, "sk_1"), "read_only")
    assert not result.get("isError")
    assert result["structuredContent"] == {"ok": True}


@pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
def test_no_auth_env_means_no_scope_check_over_mcp(monkeypatch, sync):
    with TestClient(_app(monkeypatch, sync, keys=None)) as c:
        result = _call_tool(c, _session(c, None), "dangerous")
    assert not result.get("isError")
    assert calls["n"] == 1


@pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
def test_rest_scope_unchanged(monkeypatch, sync):
    with TestClient(_app(monkeypatch, sync)) as c:
        r = c.post("/api/dangerous", json={},
                   headers={"Authorization": "Bearer sk_1"})
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden_scope"
    assert calls["n"] == 0


# --- the principal is per REQUEST, not per MCP session ---------------------
# AuthMiddleware authenticates every HTTP request; a session id minted by one
# key must not lend that key's scopes to calls made with another.

def _with_key(headers, token):
    # A real session must exist, or these tests would pass in a stateless mode
    # without ever reusing one key's session with another key.
    assert "mcp-session-id" in headers
    return {**headers, "Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
def test_session_opened_by_write_key_does_not_lend_scope(monkeypatch, sync):
    with TestClient(_app(monkeypatch, sync)) as c:
        h = _session(c, "sk_2")
        result = _call_tool(c, _with_key(h, "sk_1"), "dangerous")
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "forbidden_scope"
    assert calls["n"] == 0


@pytest.mark.parametrize("sync", [True, False], ids=["sync", "async"])
def test_session_opened_by_read_key_does_not_cap_scope(monkeypatch, sync):
    with TestClient(_app(monkeypatch, sync)) as c:
        h = _session(c, "sk_1")
        result = _call_tool(c, _with_key(h, "sk_2"), "dangerous")
    assert not result.get("isError")
    assert calls["n"] == 1


# --- fail closed: auth enabled but no principal in the context -------------

def test_auth_enabled_without_principal_is_forbidden_in_memory(monkeypatch):
    """No HTTP layer (fastmcp in-memory transport): AuthMiddleware never ran,
    so current_auth is unset. With AUTH_API_KEY configured the scoped tool
    must refuse, not run."""
    fastmcp = pytest.importorskip("fastmcp")
    import asyncio

    from restmcp.auth import current_auth

    monkeypatch.setenv("AUTH_API_KEY", _KEYS)
    _register(sync=True)
    server = Server.get_instance().get_mcp()

    # Record the principal the scope check actually sees: a principal leaked
    # into the context (e.g. by an earlier test) must not make this pass.
    seen = []
    original = Endpoint._enforce_scope

    def spy(self, principal):
        seen.append(principal)
        return original(self, principal)

    monkeypatch.setattr(Endpoint, "_enforce_scope", spy)

    async def go():
        assert current_auth.get() is None
        async with fastmcp.Client(server) as client:
            return await client.call_tool("dangerous", {}, raise_on_error=False)

    result = asyncio.run(go())
    assert seen == [None]
    assert result.is_error is True
    assert result.structured_content["code"] == "forbidden_scope"
    assert calls["n"] == 0


# --- the per-request principal wins over a contextvar set elsewhere --------
# On fastmcp 3.x (mcp 1.x) the session's server loop runs in a task spawned by
# the request that OPENED the session, so current_auth there is that request's
# principal. The scope check must read the principal of the HTTP request making
# the tools/call, and fail closed when that request carries none.

def test_http_request_without_principal_is_forbidden_despite_contextvar(monkeypatch):
    """A tools/call whose HTTP request carries no principal (no
    scope["state"]["auth"]) is refused even when current_auth holds a write
    principal: the contextvar is only trusted when there is no HTTP request."""
    pytest.importorskip("fastmcp")
    from restmcp.auth import current_auth

    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _register(sync=True)
    inner = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")  # no AuthMiddleware
    monkeypatch.setenv("AUTH_API_KEY", _KEYS)
    write = {"name": "campo", "scopes": frozenset({"read", "write"})}

    async def app(scope, receive, send):
        if scope["type"] == "http":
            current_auth.set(write)
        await inner(scope, receive, send)

    with TestClient(app) as c:
        h = _session(c, None)
        result = _call_tool(c, h, "dangerous")
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "forbidden_scope"
    assert calls["n"] == 0


def test_in_memory_uses_current_auth(monkeypatch):
    """No HTTP request (in-memory transport): current_auth is the source."""
    fastmcp = pytest.importorskip("fastmcp")
    import asyncio

    from restmcp.auth import current_auth

    monkeypatch.setenv("AUTH_API_KEY", _KEYS)
    _register(sync=True)
    server = Server.get_instance().get_mcp()

    async def go():
        current_auth.set({"name": "campo", "scopes": frozenset({"read", "write"})})
        async with fastmcp.Client(server) as client:
            return await client.call_tool("dangerous", {}, raise_on_error=False)

    result = asyncio.run(go())
    assert not result.is_error
    assert calls["n"] == 1
