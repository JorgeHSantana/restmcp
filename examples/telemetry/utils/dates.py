"""Helpers shared by endpoints.

Important framework detail: restmcp maps every string parameter to `str` and
never parses dates — there is no `date-time` format handling. An ISO 8601
timestamp therefore arrives in the callback as a plain string; coerce it
explicitly.
"""

import datetime as dt


def coerce_reference_date(value) -> dt.datetime | None:
    """Accept None, a datetime, or an ISO 8601 string (incl. trailing 'Z')."""
    if value is None or isinstance(value, dt.datetime):
        return value
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
