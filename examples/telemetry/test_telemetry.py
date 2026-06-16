"""Tests for the example — also a tour of dependency injection.

Run from this folder:  python -m pytest
Every layer accepts an injected collaborator, so business logic is tested with a
fake DataSource and no server, no network, no real data.
"""

import datetime as dt

from restmcp import DataSource

from repositories.reading import ReadingRepository
from services.battery import BatteryHealthService


class FakeTelemetryDataSource(DataSource):
    """A two-device fleet: one healthy, one critical."""

    def known_device_ids(self):
        return [10, 11]

    def fetch_readings(self, device_id_list, since, until):
        rows = [
            {
                "device_id": 10, "device_name": "fake-healthy", "firmware": "9.9.9",
                "battery_level": 90.0, "signal_dbm": -70, "recorded_at": until,
            },
            {
                "device_id": 11, "device_name": "fake-critical", "firmware": "9.9.9",
                "battery_level": 5.0, "signal_dbm": -100, "recorded_at": until,
            },
        ]
        ids = device_id_list or self.known_device_ids()
        return [r for r in rows if r["device_id"] in ids]


def _service():
    repo = ReadingRepository(data_source=FakeTelemetryDataSource())
    return BatteryHealthService(readings=repo)


def test_battery_map_classifies_by_level():
    result = _service().battery_map(reference_date=dt.datetime(2026, 6, 1))
    assert result == {"healthy": [10], "critical": [11]}


def test_missing_device_reported_as_no_data():
    result = _service().battery_map(device_id_list=[10, 999])
    assert result["no_data"] == [999]


def test_entity_serialize_adds_status():
    reading = _service().latest_reading(10)
    data = reading.serialize()
    assert data["status"] == "healthy"
    # datetime is serialized to a string by serialize()/jsonable_encoder
    assert isinstance(data["recorded_at"], str)


def test_fleet_report_is_cached():
    svc = _service()
    first = svc.fleet_report()
    second = svc.fleet_report()
    # Same memoized object within the TTL.
    assert first is second
