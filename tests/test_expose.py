"""Per-endpoint transport exposure: ``expose = "rest" | "mcp" | "both"``.

Motivation (ReconcilIA §6.5): write endpoints must not exist for the MCP
credential — with ``expose = "rest"`` the tool is absent from the catalog and
from the MCP server, structurally, instead of relying on middleware alone.
The inverse ("mcp") serves agent-only tools with no public REST surface.
Default is "both": zero change for existing endpoints.
"""
import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server


def _catalog(server):
    with TestClient(server.app) as c:
        return {t["name"] for t in c.get("/mcp/tools").json()["tools"]}


def test_rest_only_has_route_but_no_tool(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class WriteOnlyEndpoint(Endpoint):
        expose = "rest"
        mcp_definition = {"name": "write_only", "description": "escrita",
                          "parameters": {"properties": {}}}
        url = "/api/write_only"
        method = "POST"

        def callback(self):
            return {"ok": True}

    with TestClient(server.app) as c:
        assert c.post("/api/write_only", json={}).json()["result"] == {"ok": True}
    assert "write_only" not in _catalog(server)
    # and the MCP server itself must not receive the handler
    assert all(
        h.mcp_definition["name"] != "write_only" for h in server.mcp_handlers
    )


def test_mcp_only_has_tool_but_no_route(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class AgentOnlyEndpoint(Endpoint):
        expose = "mcp"
        mcp_definition = {"name": "agent_only", "description": "só agente",
                          "parameters": {"properties": {}}}
        url = "/api/agent_only"
        method = "POST"

        def callback(self):
            return {"ok": True}

    with TestClient(server.app) as c:
        assert c.post("/api/agent_only", json={}).status_code == 404
    assert "agent_only" in _catalog(server)
    assert any(
        h.mcp_definition["name"] == "agent_only" for h in server.mcp_handlers
    )


def test_default_is_both(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class RegularEndpoint(Endpoint):
        mcp_definition = {"name": "regular", "description": "padrão",
                          "parameters": {"properties": {}}}
        url = "/api/regular"
        method = "POST"

        def callback(self):
            return {"ok": True}

    with TestClient(server.app) as c:
        assert c.post("/api/regular", json={}).status_code == 200
    assert "regular" in _catalog(server)


def test_invalid_expose_fails_at_definition(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    Server.get_instance()

    with pytest.raises(TypeError, match="expose"):
        class TypoEndpoint(Endpoint):
            expose = "rest-only"      # typo: not a valid value
            mcp_definition = {"name": "typo", "description": "x",
                              "parameters": {"properties": {}}}
            url = "/api/typo"
            method = "POST"

            def callback(self):
                return {}
