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
        purged = getattr(self, "_purged", set())
        return [r for r in rows if r["device_id"] in ids and r["device_id"] not in purged]

    def purge_readings(self, device_id):
        purged = self._purged = getattr(self, "_purged", set())
        if device_id in purged or device_id not in self.known_device_ids():
            return 0
        count = len(self.fetch_readings([device_id], None, dt.datetime.now()))
        purged.add(device_id)
        return count


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


def test_purge_discards_and_reports_count():
    """purge_readings drains a device once; unknown devices are NotFoundError.

    (The transport-level behavior of the endpoint — expose="rest" hiding the
    tool from MCP, and the published response schema — is covered by the
    library's own test suite; here we stay at the service layer, like the
    rest of this file.)
    """
    import pytest
    from restmcp.exceptions import NotFoundError

    svc = _service()
    first = svc.purge_readings(10)
    assert first > 0
    assert svc.purge_readings(10) == 0          # nothing left to drop
    with pytest.raises(NotFoundError):
        svc.purge_readings(99)


# ---- 0.6.0: success_code e raw_response, pelas camadas de serviço ----------


def test_recalibration_devolve_ticket_aceito():
    svc = _service()
    job = svc.schedule_recalibration([10, 11])
    assert job["status"] == "accepted"
    assert job["devices"] == [10, 11]
    assert job["job_id"]


def test_recalibration_de_device_desconhecido_e_not_found():
    import pytest
    from restmcp.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        _service().schedule_recalibration([99])


def test_export_csv_e_texto_ordenado_por_data():
    csv = _service().export_csv(10)
    linhas = csv.strip().split("\n")
    assert linhas[0] == "device_id,status,recorded_at"
    assert all(linha.startswith("10,") for linha in linhas[1:])
    assert len(linhas) > 1


def test_export_de_device_desconhecido_e_not_found():
    import pytest
    from restmcp.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        _service().export_csv(99)
