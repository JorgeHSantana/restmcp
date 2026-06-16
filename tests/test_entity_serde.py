import datetime as dt
import json
from restmcp import Entity


class SampleEntity(Entity):
    id: int
    when: dt.datetime | None = None


def test_serialize_json_safe():
    s = SampleEntity(id=1, when=dt.datetime(2026, 6, 14, 10, 0)).serialize()
    assert s == {"id": 1, "when": "2026-06-14T10:00:00"}
    json.dumps(s)  # does not raise


def test_deserialize():
    e = SampleEntity.deserialize({"id": 2, "when": None})
    assert isinstance(e, SampleEntity)
    assert e.id == 2 and e.when is None
