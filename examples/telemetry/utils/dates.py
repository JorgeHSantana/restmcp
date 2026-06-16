"""Helpers shared by endpoints.

Important framework detail: a parameter declared as
`{"type": "string", "format": "date-time"}` arrives in the callback as a
**string**, not a `datetime`. Coerce it explicitly.
"""

import datetime as dt


def coerce_reference_date(value) -> dt.datetime | None:
    """Accept None, a datetime, or an ISO 8601 string (incl. trailing 'Z')."""
    if value is None or isinstance(value, dt.datetime):
        return value
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
