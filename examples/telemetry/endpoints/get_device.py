"""Single-device lookup — shows inferred schema + automatic serialization."""

from typing import Annotated

from restmcp import Endpoint

from services.battery import BatteryHealthService


class GetDeviceEndpoint(Endpoint):
    url = "/api/get-device"
    method = "POST"

    def callback(self, device_id: Annotated[int, "Device id (1-5)"]) -> dict:
        """Latest telemetry reading for one device."""
        # Returning the Entity directly: `recorded_at` (a datetime) is serialized
        # to ISO 8601 by the framework, and `serialize()` adds the `status` field.
        reading = BatteryHealthService().latest_reading(device_id)
        return reading.serialize()
