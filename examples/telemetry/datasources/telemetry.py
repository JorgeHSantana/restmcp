"""In-memory DataSource.

A real DataSource wraps an external system (Postgres, a REST API, a file).
This one fabricates deterministic telemetry so the example runs with zero
infrastructure — `python main.py` just works. Swap this class for a real one
and nothing above it (Repository/Service/Endpoint) has to change.
"""

import datetime as dt
import random

from restmcp import DataSource

# A small, fixed fleet. device_id -> static attributes.
_FLEET = {
    1: {"device_name": "north-gate-sensor", "firmware": "2.4.1"},
    2: {"device_name": "pump-station-a", "firmware": "2.4.1"},
    3: {"device_name": "weather-mast-3", "firmware": "2.3.9"},
    4: {"device_name": "silo-level-7", "firmware": "2.4.0"},
    5: {"device_name": "perimeter-cam-2", "firmware": "2.2.0"},
}


def _reading_for(device_id: int, day: dt.date) -> dict:
    """Deterministic pseudo-reading: same (device, day) always yields the same row."""
    rng = random.Random(f"{device_id}-{day.isoformat()}")
    base = {1: 88, 2: 35, 3: 12, 4: 65, 5: 5}.get(device_id, 50)
    # battery drifts a little day to day, clamped to [0, 100]
    level = max(0.0, min(100.0, base + rng.uniform(-8, 4)))
    meta = _FLEET[device_id]
    return {
        "device_id": device_id,
        "device_name": meta["device_name"],
        "firmware": meta["firmware"],
        "battery_level": round(level, 1),
        "signal_dbm": rng.randint(-110, -60),
        "recorded_at": dt.datetime.combine(day, dt.time(hour=rng.randint(0, 23))),
    }


class TelemetryDataSource(DataSource):
    """Pretends to be a telemetry database. Returns raw dicts, never Entities."""

    def known_device_ids(self) -> list[int]:
        return sorted(_FLEET)

    def fetch_readings(
        self,
        device_id_list: list[int] | None,
        since: dt.datetime,
        until: dt.datetime,
    ) -> list[dict]:
        """Every reading for the given devices within [since, until]."""
        ids = device_id_list or self.known_device_ids()
        rows: list[dict] = []
        day = since.date()
        while day <= until.date():
            for device_id in ids:
                if device_id not in _FLEET:
                    continue  # unknown device -> simply no rows
                row = _reading_for(device_id, day)
                if since <= row["recorded_at"] <= until:
                    rows.append(row)
            day += dt.timedelta(days=1)
        return rows
