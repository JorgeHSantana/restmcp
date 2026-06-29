from typing import Annotated

import pytest

from restmcp import Endpoint, Server


def test_endpoint_without_mcp_definition_infers_it():
    class GetThingEndpoint(Endpoint):
        url = "/api/get-thing"
        method = "POST"

        def callback(self, thing_id: Annotated[int, "Thing id"]) -> dict:
            """Return a thing.

            Returns: the thing payload.
            """
            return {"thing_id": thing_id}

    handler = Server.get_instance().url_handlers[-1]
    assert handler.mcp_definition["name"] == "get_thing"
    assert handler.mcp_definition["description"] == (
        "Return a thing.\n\nReturns: the thing payload."
    )
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


def test_inferred_endpoint_without_returns_section_raises():
    with pytest.raises(TypeError, match="Returns:"):
        class NoReturnsEndpoint(Endpoint):
            url = "/api/no-returns"
            method = "POST"

            def callback(self, thing_id: Annotated[int, "Thing id"]) -> dict:
                """Missing the Returns section."""
                return {"thing_id": thing_id}


def test_explicit_mcp_definition_skips_returns_requirement():
    # Hand-written definitions are exempt: no docstring Returns needed.
    class ManualEndpoint(Endpoint):
        mcp_definition = {
            "name": "manual_tool",
            "description": "Hand-written, no Returns docstring.",
            "parameters": {"properties": {}},
        }
        url = "/api/manual"
        method = "POST"

        def callback(self) -> dict:
            return {}

    handler = Server.get_instance().url_handlers[-1]
    assert handler.mcp_definition["name"] == "manual_tool"
