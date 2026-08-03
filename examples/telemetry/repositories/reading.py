"""Data-access layer.

A Repository owns exactly one DataSource and turns raw rows into Entities.
The `data_source` class attribute is the production default; tests inject a fake
via `ReadingRepository(data_source=FakeDataSource())` (see test_example.py).
`Repository.__init__` deep-copies the class attribute, so instances never share
state.
"""

import datetime as dt

from restmcp import Repository

from datasources.telemetry import TelemetryDataSource
from entities.reading import DeviceReadingEntity


class ReadingRepository(Repository):
    data_source = TelemetryDataSource()

    def get(
        self,
        device_id_list: list[int] | None = None,
        since: dt.datetime | None = None,
        until: dt.datetime | None = None,
    ) -> list[DeviceReadingEntity]:
        until = until or dt.datetime.now()
        since = since or (until - dt.timedelta(days=7))
        rows = self.data_source.fetch_readings(device_id_list, since=since, until=until)
        return [DeviceReadingEntity(**row) for row in rows]

    def known_device_ids(self) -> list[int]:
        return self.data_source.known_device_ids()

    def purge_readings(self, device_id: int) -> int:
        return self.data_source.purge_readings(device_id)
