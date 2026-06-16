"""Fleet rollup — shows the cached_method memoization in action."""

from restmcp import Endpoint

from services.battery import BatteryHealthService

# Module-level instance so the cache on `fleet_report` survives across requests
# (a fresh Service per call would defeat the per-instance cache).
_service = BatteryHealthService()


class FleetReportEndpoint(Endpoint):
    mcp_definition = {
        "name": "fleet_report",
        "description": "Fleet-wide battery rollup (cached for 30s).",
        "parameters": {
            "properties": {
                "device_id_list": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Subset of devices; omit for the whole fleet",
                    "default": None,
                },
            },
        },
    }
    url = "/api/fleet-report"
    method = "POST"

    def callback(self, device_id_list=None) -> dict:
        # Call this twice within 30s: the server logs "computing" only once.
        return _service.fleet_report(device_id_list=device_id_list)
