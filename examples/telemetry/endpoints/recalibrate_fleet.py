"""Async-accept endpoint — shows `success_code = 202` (0.6.0, issue #18).

Recalibrating a fleet takes minutes; the endpoint ACCEPTS the job and answers
before it is done. The HTTP status is the only part of the response that tells
a client "this is a ticket, not a result" — a 200 here would invite treating
the ``job_id`` as the finished outcome.

What the single declaration buys (one source, two consumers):

- the success envelope goes out with **202 Accepted**;
- ``/openapi.json`` documents the operation under ``"202"`` — generated
  clients see the real code, and a frozen-contract CI cannot drift from the
  server, because there is nothing to keep in sync by hand.

Errors are untouched: an unknown device still raises ``NotFoundError`` → 404
with the standard error envelope. ``success_code`` speaks only for success.
"""

from restmcp import Endpoint

from services.battery import BatteryHealthService


class RecalibrateFleetEndpoint(Endpoint):
    success_code = 202       # aceito ≠ pronto — e o OpenAPI diz o mesmo
    mcp_definition = {
        "name": "recalibrate_fleet",
        "description": "Accept a fleet recalibration job; poll for the outcome.",
        "parameters": {"properties": {
            "device_id_list": {
                "type": "array", "items": {"type": "integer"},
                "description": "Devices to recalibrate; empty = whole fleet.",
                "default": None,
            },
        }},
        "returns": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "devices": {"type": "array", "items": {"type": "integer"}},
                "status": {"type": "string", "description": 'Always "accepted"'},
            },
            "required": ["job_id", "devices", "status"],
        },
    }
    url = "/api/recalibrate-fleet"
    method = "POST"

    def callback(self, device_id_list=None):
        return BatteryHealthService().schedule_recalibration(device_id_list)
