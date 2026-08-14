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

    def purge_readings(self, device_id: int) -> int:
        """Discard one device's readings; NotFoundError for unknown devices."""
        if device_id not in self.readings.known_device_ids():
            raise NotFoundError(f"Unknown device {device_id}")
        return self.readings.purge_readings(device_id)

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

    def export_csv(self, device_id: int) -> str:
        """One device's readings as CSV text (0.6.0 example: raw download).

        The Service returns a STRING — it knows nothing about HTTP. Turning it
        into a file download (headers, content-disposition, status) is the
        endpoint's job: transport lives at the edge, like everywhere else here.
        """
        if device_id not in self.readings.known_device_ids():
            raise NotFoundError(f"Unknown device {device_id}")
        rows = ["device_id,status,recorded_at"]
        for r in sorted(self.readings.get(device_id_list=[device_id]),
                        key=lambda r: r.recorded_at):
            rows.append(f"{r.device_id},{r.status},{r.recorded_at.isoformat()}")
        return "\n".join(rows) + "\n"

    def schedule_recalibration(self, device_id_list: list[int] | None = None) -> dict:
        """Accept a recalibration job and return its ticket (0.6.0 example: 202).

        Simulates the accept-then-work pattern: the job is REGISTERED now (the
        202 response carries its id) and would be processed out of band. What
        matters for the example is the semantics: the response says "accepted",
        never "done".
        """
        devices = device_id_list or self.readings.known_device_ids()
        desconhecidos = [d for d in devices if d not in self.readings.known_device_ids()]
        if desconhecidos:
            raise NotFoundError(f"Unknown devices: {desconhecidos}")
        job_id = f"recal-{len(devices)}-{min(devices)}{max(devices)}"
        return {"job_id": job_id, "devices": sorted(devices), "status": "accepted"}

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
