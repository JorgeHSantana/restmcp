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
