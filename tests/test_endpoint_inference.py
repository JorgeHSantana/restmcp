from typing import Annotated

from restmcp import Endpoint, Server


def test_endpoint_without_mcp_definition_infers_it():
    class GetThingEndpoint(Endpoint):
        url = "/api/get-thing"
        method = "POST"

        def callback(self, thing_id: Annotated[int, "Thing id"]) -> dict:
            """Return a thing."""
            return {"thing_id": thing_id}

    handler = Server.get_instance().url_handlers[-1]
    assert handler.mcp_definition["name"] == "get_thing"
    assert handler.mcp_definition["description"] == "Return a thing."
    assert handler.mcp_definition["parameters"]["properties"]["thing_id"] == {
        "type": "integer",
        "description": "Thing id",
    }


def test_explicit_mcp_definition_is_used_verbatim():
    class LegacyEndpoint(Endpoint):
        mcp_definition = {
            "name": "legacy_tool",
            "description": "Hand-written.",
            "parameters": {"properties": {"x": {"type": "string"}}},
        }
        url = "/api/legacy"
        method = "POST"

        def callback(self, x: str) -> dict:
            return {"x": x}

    handler = Server.get_instance().url_handlers[-1]
    assert handler.mcp_definition["name"] == "legacy_tool"
    assert handler.mcp_definition["description"] == "Hand-written."
