import datetime as dt
from starlette.testclient import TestClient
from restmcp import Server, Endpoint


def _client():
    server = Server.get_instance()

    class DateTimeResponseEndpoint(Endpoint):
        mcp_definition = {"name": "datetime_tool", "description": "retorna data",
                          "parameters": {"properties": {}}}
        url = "/mcp/tools/datetime_tool"
        method = "POST"

        def callback(self):
            return {"when": dt.datetime(2026, 6, 14, 10, 0, 0)}

    return TestClient(server.app)


def test_datetime_no_result_serializa_iso():
    resp = _client().post("/mcp/tools/datetime_tool", json={})
    assert resp.status_code == 200
    assert resp.json()["result"]["when"] == "2026-06-14T10:00:00"
    assert resp.json()["success"] is True
