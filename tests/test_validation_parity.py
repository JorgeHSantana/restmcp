import asyncio

import pytest
from starlette.testclient import TestClient

from restmcp.endpoint import Endpoint
from restmcp.server import Server

# (input value for `n`, should_be_accepted)
CASES = [
    (5, True),
    ("5", True),
    (5.0, True),
    ("5.0", True),
    (True, False),      # anti-bool guard
    ("abc", False),     # non-numeric
    (5.3, False),       # non-integral float
]


def _make_endpoint():
    class ParityEndpoint(Endpoint):
        mcp_definition = {
            "name": "parity_tool",
            "description": "parity",
            "parameters": {"properties": {"n": {"type": "integer"}}},
        }
        url = "/api/parity"
        method = "POST"

        def callback(self, n: int):
            return {"n": n}


def _rest_accepts(client, value) -> bool:
    r = client.post("/api/parity", json={"n": value})
    return r.status_code == 200 and r.json()["success"] is True


def _mcp_accepts(mcp, value) -> bool:
    from fastmcp import Client

    async def _call():
        async with Client(mcp) as c:
            try:
                await c.call_tool("parity_tool", {"n": value})
                return True
            except Exception:
                return False

    return asyncio.run(_call())


@pytest.mark.parametrize("value,accepted", CASES)
def test_rest_and_mcp_agree(value, accepted):
    _make_endpoint()
    server = Server.get_instance()
    client = TestClient(server.app)
    mcp = server.get_mcp()

    rest = _rest_accepts(client, value)
    mcp_ok = _mcp_accepts(mcp, value)

    assert rest == accepted, f"REST disagreed for {value!r}: got accepted={rest}"
    assert mcp_ok == accepted, f"MCP disagreed for {value!r}: got accepted={mcp_ok}"
    assert rest == mcp_ok, f"REST/MCP diverged for {value!r}: rest={rest} mcp={mcp_ok}"
