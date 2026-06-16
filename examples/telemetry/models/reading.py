"""Domain entity.

`Entity` is a Pydantic model with a name-suffix rule (`*Entity`) enforced at
import time. Because the framework serializes callback return values with
`jsonable_encoder`, you can return an Entity (or a `datetime`) straight from a
callback and get correct JSON — `recorded_at` below becomes an ISO 8601 string
automatically, no manual `.isoformat()` anywhere.
"""

import datetime as dt
from typing import Literal

from restmcp import Entity

BatteryStatus = Literal["healthy", "degraded", "critical"]


class DeviceReadingEntity(Entity):
    device_id: int
    device_name: str
    firmware: str
    battery_level: float
    signal_dbm: int
    recorded_at: dt.datetime

    @property
    def status(self) -> BatteryStatus:
        if self.battery_level >= 60:
            return "healthy"
        if self.battery_level >= 20:
            return "degraded"
        return "critical"

    def serialize(self) -> dict:
        """Override the default serde to expose the derived `status` field.

        The framework calls `jsonable_encoder` on whatever a callback returns,
        so overriding `serialize()` is optional — do it only when the JSON shape
        should differ from the model's fields (here: adding `status`).
        """
        data = self.model_dump(mode="json")
        data["status"] = self.status
        return data
