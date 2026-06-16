"""Battery triage — shows inferred array + optional params with defaults."""

from typing import Annotated, Optional

from restmcp import Endpoint, ValidationError

from services.battery import BatteryHealthService
from utils.dates import coerce_reference_date


class CheckBatteryEndpoint(Endpoint):
    url = "/api/check-battery"
    method = "POST"

    def callback(
        self,
        device_id_list: Annotated[Optional[list[int]], "Devices to inspect; omit for the whole fleet"] = None,
        reference_date: Annotated[Optional[str], "Window end (ISO 8601); defaults to now"] = None,
        days_window: Annotated[int, "How many days back to look"] = 7,
    ) -> dict:
        """Group devices by battery status within a time window."""
        if days_window <= 0:
            raise ValidationError("days_window must be positive")
        # reference_date arrives as a string — coerce it before use.
        ref = coerce_reference_date(reference_date)
        return BatteryHealthService().battery_map(
            device_id_list=device_id_list,
            reference_date=ref,
            days_window=days_window,
        )
