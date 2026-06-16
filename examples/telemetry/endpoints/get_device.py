"""Single-device lookup — shows automatic datetime serialization + exceptions."""

from restmcp import Endpoint

from services.battery import BatteryHealthService


class GetDeviceEndpoint(Endpoint):
    mcp_definition = {
        "name": "get_device",
        "description": "Latest telemetry reading for one device.",
        "parameters": {
            "properties": {
                "device_id": {"type": "integer", "description": "Device id (1-5)"},
            },
        },
    }
    url = "/api/get-device"
    method = "POST"

    def callback(self, device_id: int) -> dict:
        # Returning the Entity directly: `recorded_at` (a datetime) is serialized
        # to ISO 8601 by the framework, and `serialize()` adds the `status` field.
        reading = BatteryHealthService().latest_reading(device_id)
        return reading.serialize()
