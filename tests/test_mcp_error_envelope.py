"""MCP errors carry the same envelope as REST.

A ``RestMCPException`` raised by a callback becomes ``isError: true`` with the
shared envelope (``tool, error, success, error_type, code``) as
``structuredContent`` — agents branch on ``code`` instead of parsing text.
Anything else is an internal error: its text must not reach the client over
MCP, exactly as REST hides it behind "Internal server error".
"""
import json

import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.exceptions import NotFoundError, RestMCPException

_H = {"Accept": "application/json, text/event-stream"}
_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}}


def _register():
    class SessionGoneEndpoint(Endpoint):
        mcp_definition = {"name": "session_gone", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/session-gone"
        method = "GET"

        def callback(self):
            raise RestMCPException("sem sessão", 503, code="session_expired")

    class MissingEndpoint(Endpoint):
        mcp_definition = {"name": "missing", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/missing"
        method = "GET"

        async def callback(self):
            raise NotFoundError("linha não encontrada")

    class BoomEndpoint(Endpoint):
        mcp_definition = {"name": "boom", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/boom"
        method = "GET"

        def callback(self):
            raise RuntimeError("segredo interno")

    class FineEndpoint(Endpoint):
        mcp_definition = {"name": "fine", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/fine"
        method = "GET"

        def callback(self):
            return {"value": 42}


def _rpc(c, h, method, params, rid=2):
    r = c.post("/mcp-protocol/", headers=h, json={
        "jsonrpc": "2.0", "id": rid, "method": method, "params": params})
    assert r.status_code == 200
    data = [l for l in r.text.splitlines() if l.startswith("data:")]
    payload = json.loads(data[-1][len("data:"):]) if data else r.json()
    assert "error" not in payload, payload
    return payload["result"]


@pytest.fixture
def mcp(monkeypatch):
    pytest.importorskip("fastmcp")
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    _register()
    app = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        r = c.post("/mcp-protocol/", json=_INIT, headers=_H)
        assert r.status_code == 200
        sid = r.headers.get("mcp-session-id")
        h = {**_H, **({"mcp-session-id": sid} if sid else {})}
        c.post("/mcp-protocol/", headers=h,
               json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        yield lambda method, params: _rpc(c, h, method, params)


def _call(mcp, name):
    return mcp("tools/call", {"name": name, "arguments": {}})


def test_restmcp_exception_is_structured_error(mcp):
    result = _call(mcp, "session_gone")
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "tool": "session_gone", "error": "sem sessão", "success": False,
        "error_type": "RestMCPException", "code": "session_expired",
    }
    assert "sem sessão" in result["content"][0]["text"]


def test_not_found_has_null_code(mcp):
    result = _call(mcp, "missing")
    assert result["isError"] is True
    assert result["structuredContent"]["error_type"] == "NotFoundError"
    assert result["structuredContent"]["code"] is None


def test_unexpected_exception_stays_generic(mcp):
    result = _call(mcp, "boom")
    assert result["isError"] is True
    assert "segredo interno" not in result["content"][0]["text"]
    sc = result.get("structuredContent") or {}
    assert sc.get("code") is None
    assert "segredo interno" not in json.dumps(sc)


def test_success_unchanged(mcp):
    tools = mcp("tools/list", {})["tools"]
    assert {t["name"] for t in tools} >= {"session_gone", "missing", "boom", "fine"}
    # Errors leave as ToolResult; that must not give the tool an invalid
    # outputSchema (today none is derived: __signature__ has no return type).
    fine = next(t for t in tools if t["name"] == "fine")
    assert fine.get("outputSchema") is None or fine["outputSchema"]["type"] == "object"
    result = _call(mcp, "fine")
    assert not result.get("isError")
    assert result["structuredContent"] == {"value": 42}
