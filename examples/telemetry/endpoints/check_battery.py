"""Battery triage — shows array params, a date-time param, and defaults."""

from restmcp import Endpoint, ValidationError

from services.battery import BatteryHealthService
from utils.dates import coerce_reference_date


class CheckBatteryEndpoint(Endpoint):
    mcp_definition = {
        "name": "check_battery",
        "description": "Group devices by battery status within a time window.",
        "parameters": {
            "properties": {
                "device_id_list": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Devices to inspect; omit for the whole fleet",
                    "default": None,
                },
                "reference_date": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Window end (ISO 8601); defaults to now",
                    "default": None,
                },
                "days_window": {
                    "type": "integer",
                    "description": "How many days back to look",
                    "default": 7,
                },
            },
        },
    }
    url = "/api/check-battery"
    method = "POST"

    def callback(self, device_id_list=None, reference_date=None, days_window=7) -> dict:
        if days_window <= 0:
            raise ValidationError("days_window must be positive")
        # reference_date arrives as a string — coerce it before use.
        ref = coerce_reference_date(reference_date)
        return BatteryHealthService().battery_map(
            device_id_list=device_id_list,
            reference_date=ref,
            days_window=days_window,
        )
