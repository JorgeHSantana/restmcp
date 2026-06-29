"""Fleet rollup — shows inference alongside cached_method memoization."""

from typing import Annotated, Optional

from restmcp import Endpoint

from services.battery import BatteryHealthService

# Module-level instance so the cache on `fleet_report` survives across requests
# (a fresh Service per call would defeat the per-instance cache).
_service = BatteryHealthService()


class FleetReportEndpoint(Endpoint):
    url = "/api/fleet-report"
    method = "POST"

    def callback(
        self,
        device_id_list: Annotated[Optional[list[int]], "Subset of devices; omit for the whole fleet"] = None,
    ) -> dict:
        """Fleet-wide battery rollup (cached for 30s).

        Returns: aggregate battery stats for the selected devices —
        device_count, avg_battery_pct, and a min/max range.
        """
        # Call this twice within 30s: the server logs "computing" only once.
        return _service.fleet_report(device_id_list=device_id_list)
