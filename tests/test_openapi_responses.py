"""Response schemas in /openapi.json (ReconcilIA issue #52, part B).

Design: ``mcp_definition["returns"]`` — the slot the /mcp/tools catalog already
publishes — is the JSON Schema of the callback's return value. Every REST
response travels in the ``{tool, result, success}`` envelope, so that is what
OpenAPI documents: the envelope, with ``result`` typed by ``returns`` when
declared and open otherwise. Errors always use the error envelope and are
documented once as the ``default`` response.

A rename of a response field on the server becomes a typegen diff on the
client — the exact failure mode part B exists to catch.
"""
import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server


def _openapi(server):
    with TestClient(server.app) as c:
        return c.get("/openapi.json").json()


def test_declared_returns_types_the_result(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class BootstrapEndpoint(Endpoint):
        mcp_definition = {
            "name": "bootstrap",
            "description": "Estado inicial da UI.",
            "parameters": {"properties": {}},
            "returns": {
                "type": "object",
                "properties": {
                    "tenant": {"type": "object"},
                    "counters": {"type": "object"},
                },
                "required": ["tenant"],
            },
        }
        url = "/api/bootstrap"
        method = "GET"

        def callback(self):
            return {"tenant": {}, "counters": {}}

    op = _openapi(server)["paths"]["/api/bootstrap"]["get"]
    schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["required"] == ["tool", "result", "success"]
    assert schema["properties"]["tool"] == {"type": "string"}
    assert schema["properties"]["success"] == {"type": "boolean"}
    result = schema["properties"]["result"]
    assert result["properties"]["tenant"] == {"type": "object"}
    assert result["required"] == ["tenant"]


def test_without_returns_envelope_still_documented(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class LooseEndpoint(Endpoint):
        mcp_definition = {"name": "loose", "description": "sem returns",
                          "parameters": {"properties": {}}}
        url = "/api/loose"
        method = "GET"

        def callback(self):
            return {"anything": True}

    op = _openapi(server)["paths"]["/api/loose"]["get"]
    schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    # the envelope is typed even when the result is not
    assert schema["required"] == ["tool", "result", "success"]
    assert schema["properties"]["result"] == {}


def test_error_envelope_documented_as_default(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()

    class FailyEndpoint(Endpoint):
        mcp_definition = {"name": "faily", "description": "erros",
                          "parameters": {"properties": {}}}
        url = "/api/faily"
        method = "POST"

        def callback(self):
            return {}

    op = _openapi(server)["paths"]["/api/faily"]["post"]
    err = op["responses"]["default"]["content"]["application/json"]["schema"]
    assert set(err["properties"]) == {"tool", "error", "success", "error_type"}
    assert err["required"] == ["tool", "error", "success", "error_type"]


def test_invalid_returns_fails_at_definition(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    Server.get_instance()

    with pytest.raises((TypeError, ValueError), match="returns"):
        class BadReturnsEndpoint(Endpoint):
            mcp_definition = {"name": "bad_returns", "description": "x",
                              "parameters": {"properties": {}},
                              "returns": "um texto"}
            url = "/api/bad_returns"
            method = "POST"

            def callback(self):
                return {}
