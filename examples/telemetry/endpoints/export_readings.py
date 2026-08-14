"""File-download endpoint — shows `raw_response = True` (0.6.0, issue #18).

A CSV download does not fit the ``{tool, result, success}`` envelope: the body
is the file. ``raw_response = True`` opens the FastAPI escape hatch — the
callback returns a Starlette ``Response`` and it passes through VERBATIM
(status, headers, body). The three locks, all exercised by this example:

1. ``expose = "rest"`` is REQUIRED — a raw response has no MCP representation,
   so the tool must not exist on that side. Flip ``expose`` to ``"both"`` and
   the class fails at import time, on purpose.
2. The hatch is opt-in. Remove ``raw_response = True`` and keep the callback:
   the Response return becomes a programming error (500 + pointed log), never
   a silent passthrough.
3. Success only: the unknown-device path below raises ``NotFoundError`` and
   the client gets the STANDARD 404 error envelope — error handling stays
   uniform even on raw endpoints.

Layering note: the Service returns a CSV *string* (it knows nothing about
HTTP); building the download — media type, content-disposition, status — is
this file's job. Transport lives at the edge.
"""

from starlette.responses import PlainTextResponse

from restmcp import Endpoint

from services.battery import BatteryHealthService


class ExportReadingsEndpoint(Endpoint):
    expose = "rest"          # trava 1: sem lado MCP, senão o import explode
    raw_response = True      # trava 2: a escotilha é declarada, nunca inferida
    mcp_definition = {
        "name": "export_readings",
        "description": "Download one device's readings as a CSV file.",
        "parameters": {"properties": {
            "device_id": {"type": "integer", "description": "Device id (1-5)"},
        }},
    }
    url = "/api/export-readings"
    method = "GET"

    def callback(self, device_id):
        csv = BatteryHealthService().export_csv(device_id)   # trava 3: 404 -> envelope
        return PlainTextResponse(
            csv,
            media_type="text/csv",
            headers={"content-disposition":
                     f'attachment; filename="device-{device_id}-readings.csv"'},
        )
