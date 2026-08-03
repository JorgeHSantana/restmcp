"""Destructive endpoint — shows `expose = "rest"` and a declared `returns` schema.

Two 0.3.0/0.4.0 features on purpose in one place:

- ``expose = "rest"``: purging telemetry is not something an agent should ever
  do on its own, so the tool does not exist on the MCP side — it is absent from
  the ``/mcp/tools`` catalog and from the MCP server itself. Only the HTTP
  route (a human-driven client) can reach it.
- ``mcp_definition`` with ``returns``: the JSON Schema of the return value is
  published in ``/openapi.json`` (the 200 documents the ``{tool, result,
  success}`` envelope with ``result`` typed by it), so generated clients get a
  full response type. Explicit definition also skips docstring inference.
"""

from restmcp import Endpoint

from services.battery import BatteryHealthService


class PurgeReadingsEndpoint(Endpoint):
    expose = "rest"          # humans only: invisible to MCP agents
    mcp_definition = {
        "name": "purge_readings",
        "description": "Discard the in-memory readings of one device.",
        "parameters": {"properties": {
            "device_id": {"type": "integer", "description": "Device id (1-5)"},
        }},
        "returns": {
            "type": "object",
            "properties": {
                "device_id": {"type": "integer"},
                "purged": {"type": "integer",
                           "description": "How many readings were discarded"},
            },
            "required": ["device_id", "purged"],
        },
    }
    url = "/api/purge-readings"
    method = "POST"

    def callback(self, device_id):
        purged = BatteryHealthService().purge_readings(device_id)
        return {"device_id": device_id, "purged": purged}
