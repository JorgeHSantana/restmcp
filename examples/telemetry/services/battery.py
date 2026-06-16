"""Business logic.

A Service orchestrates one or more Repositories. Repository class attributes are
auto-discovered and isolated per instance, so tests can inject mocks:
`BatteryHealthService(readings=FakeRepository())`.

`fleet_report` is wrapped in `cached_method`: the first call computes, repeated
calls within the TTL return the memoized value. The cache key is built from the
arguments (via `repr`), so it works even though `device_id_list` is an unhashable
`list`.
"""

import datetime as dt

from restmcp import Service, cached_method, NotFoundError

from repositories.reading import ReadingRepository


class BatteryHealthService(Service):
    readings = ReadingRepository()

    def latest_reading(self, device_id: int):
        """Most recent reading for one device, or NotFoundError if unknown/silent."""
        items = self.readings.get(device_id_list=[device_id])
        if not items:
            raise NotFoundError(f"No telemetry for device {device_id}")
        return max(items, key=lambda r: r.recorded_at)

    def battery_map(
        self,
        device_id_list: list[int] | None = None,
        reference_date: dt.datetime | None = None,
        days_window: int = 7,
    ) -> dict:
        """status -> [device_id], using each device's latest reading in the window."""
        until = reference_date or dt.datetime.now()
        since = until - dt.timedelta(days=days_window)
        items = self.readings.get(device_id_list=device_id_list, since=since, until=until)

        latest: dict[int, object] = {}
        for r in items:
            cur = latest.get(r.device_id)
            if cur is None or r.recorded_at > cur.recorded_at:
                latest[r.device_id] = r

        result: dict[str, list[int]] = {}
        for device_id, reading in latest.items():
            result.setdefault(reading.status, []).append(device_id)

        requested = device_id_list or self.readings.known_device_ids()
        missing = [d for d in requested if d not in latest]
        if missing:
            result["no_data"] = missing
        return {k: sorted(v) for k, v in result.items()}

    @cached_method(ttl=30)
    def fleet_report(self, device_id_list: list[int] | None = None) -> dict:
        """Expensive fleet-wide rollup, memoized for 30s.

        Prints when it actually recomputes so you can watch the cache work:
        hit the endpoint twice within 30s and the second call is silent.
        """
        print("[fleet_report] computing (cache miss)...")
        mapping = self.battery_map(device_id_list=device_id_list)
        return {
            "generated_at": dt.datetime.now(),
            "by_status": mapping,
            "total_devices": sum(len(v) for v in mapping.values()),
        }
