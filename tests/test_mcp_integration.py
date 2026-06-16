import asyncio

import pytest

from restmcp.mcp import McpApp


class _Handler:
    mcp_definition = {
        "name": "get_device",
        "description": "Latest reading for one device.",
        "parameters": {
            "properties": {
                "device_id": {"type": "integer", "description": "Device id"},
                "tags": {"type": "array", "items": {"type": "string"}, "default": None},
            }
        },
    }

    @staticmethod
    def callback(device_id, tags=None):
        return {"device_id": device_id, "tags": tags}


def test_real_fastmcp_registers_flat_tool_and_exposes_schema():
    """Build against the real FastMCP and confirm the tool schema is flat.

    Guards the regression where a function carrying types only on __signature__
    (not __annotations__) fails FastMCP/pydantic introspection.
    """
    pytest.importorskip("fastmcp")

    mcp = McpApp().build([_Handler()])

    # FastMCP 3.x: get_tool(name) is async and returns a Tool whose input
    # JSON schema is on .parameters.
    tool = asyncio.run(mcp.get_tool("get_device"))
    schema = tool.parameters  # JSON schema for the tool input

    props = schema.get("properties", {})
    assert "args" not in props, "params must be flat, not nested under 'args'"
    assert set(props) == {"device_id", "tags"}
    # description carried through
    assert props["device_id"].get("description") == "Device id"
    # required vs optional: device_id required, tags optional (default None)
    assert "device_id" in schema.get("required", [])
    assert "tags" not in schema.get("required", [])
