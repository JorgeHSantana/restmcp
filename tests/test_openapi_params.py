"""Param schemas must reach /openapi.json (ReconcilIA issue #52, part A).

The MCP side already publishes each tool's ``parameters`` JSONSchema; the REST
side registered a bare handler, so every operation came out empty and generated
clients (openapi-typescript & friends) had no types to work with. These tests
pin the contract: what MCP publishes, OpenAPI publishes too — same source
(``mcp_definition``), no drift possible.

Response schemas are a separate design problem (part B) and are intentionally
NOT covered here.
"""
from starlette.testclient import TestClient

from restmcp import Endpoint, Server


def _openapi(server):
    with TestClient(server.app) as c:
        return c.get("/openapi.json").json()


def test_post_publishes_request_body_schema(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class DecideEndpoint(Endpoint):
        mcp_definition = {
            "name": "decide",
            "description": "Aplica uma ação a um item.",
            "parameters": {"properties": {
                "item_id": {"type": "string", "description": "Id do item"},
                "reason": {"type": "string", "default": "manual"},
            }},
        }
        url = "/api/decide"
        method = "POST"

        def callback(self, item_id, reason="manual"):
            return {"ok": True}

    op = _openapi(server)["paths"]["/api/decide"]["post"]
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert schema["properties"]["item_id"] == {
        "type": "string", "description": "Id do item",
    }
    assert schema["properties"]["reason"]["type"] == "string"
    # required = property without a default, exactly like validation treats it
    assert schema["required"] == ["item_id"]
    # extra keys are rejected at runtime (extra='forbid'); the schema says so
    assert schema["additionalProperties"] is False
    assert op["requestBody"]["required"] is True
    assert op["operationId"] == "decide"
    assert op["description"] == "Aplica uma ação a um item."


def test_get_publishes_query_parameters(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class PartitionEndpoint(Endpoint):
        mcp_definition = {
            "name": "get_partition",
            "description": "Itens de uma partição.",
            "parameters": {"properties": {
                "key": {"type": "string"},
                "page": {"type": "integer", "default": 1},
            }},
        }
        url = "/api/partition"
        method = "GET"

        def callback(self, key, page=1):
            return {"items": []}

    op = _openapi(server)["paths"]["/api/partition"]["get"]
    params = {p["name"]: p for p in op["parameters"]}
    assert params["key"]["in"] == "query"
    assert params["key"]["required"] is True
    assert params["key"]["schema"] == {"type": "string"}
    assert params["page"]["required"] is False
    assert params["page"]["schema"]["type"] == "integer"


def test_endpoint_without_params_stays_clean(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class NoopEndpoint(Endpoint):
        mcp_definition = {"name": "noop", "description": "sem params",
                          "parameters": {"properties": {}}}
        url = "/api/noop"
        method = "POST"

        def callback(self):
            return {}

    op = _openapi(server)["paths"]["/api/noop"]["post"]
    assert "requestBody" not in op
    assert not op.get("parameters")


def test_inferred_definition_also_publishes(monkeypatch):
    """Endpoints in the signature-inferred style (the ReconcilIA ones) get the
    same treatment: inference builds mcp_definition, OpenAPI publishes it."""
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class LegacyStyleEndpoint(Endpoint):
        name = "legacy_style"
        url = "/api/legacy"
        method = "POST"

        def callback(self, item_id: str, note: str = "n/a"):
            """Faz algo.

            Returns: um dict vazio.
            """
            return {}

    op = _openapi(server)["paths"]["/api/legacy"]["post"]
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert "item_id" in schema["properties"]
    assert schema["required"] == ["item_id"]
