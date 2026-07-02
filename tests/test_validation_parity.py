import asyncio

import pytest
from starlette.testclient import TestClient

from restmcp.endpoint import Endpoint
from restmcp.server import Server

# Full payloads sent identically to both transports.
# (payload, should_be_accepted)
CASES = [
    # integer (required): lax coercion + anti-bool guard
    ({"n": 5}, True),
    ({"n": "5"}, True),
    ({"n": 5.0}, True),
    ({"n": "5.0"}, True),
    ({"n": True}, False),
    ({"n": "abc"}, False),
    ({"n": 5.3}, False),
    # string: lax str does NOT coerce numbers/bools
    ({"n": 1, "s": "hi"}, True),
    ({"n": 1, "s": 123}, False),
    ({"n": 1, "s": True}, False),
    # number: numeric strings ok, bool rejected
    ({"n": 1, "x": 1.5}, True),
    ({"n": 1, "x": "1.5"}, True),
    ({"n": 1, "x": True}, False),
    # boolean: pydantic-lax inputs accepted, junk rejected
    ({"n": 1, "f": True}, True),
    ({"n": 1, "f": 1}, True),
    ({"n": 1, "f": "on"}, True),
    ({"n": 1, "f": "nope"}, False),
    ({"n": 1, "f": 2}, False),
    # boolean with non-None default: explicit null rejected
    ({"n": 1, "f": None}, False),
    # array[int]: item coercion + anti-bool on items; default None accepts null
    ({"n": 1, "ids": [1, "2"]}, True),
    ({"n": 1, "ids": [1, True]}, False),
    ({"n": 1, "ids": "1"}, False),
    ({"n": 1, "ids": None}, True),
    # object
    ({"n": 1, "o": {"a": 1}}, True),
    ({"n": 1, "o": "not-a-dict"}, False),
    # unknown key / missing required
    ({"n": 1, "bogus": 1}, False),
    ({}, False),
]


def _make_endpoint():
    class ParityEndpoint(Endpoint):
        mcp_definition = {
            "name": "parity_tool",
            "description": "parity",
            "parameters": {"properties": {
                "n": {"type": "integer"},
                "s": {"type": "string", "default": "x"},
                "x": {"type": "number", "default": 0.5},
                "f": {"type": "boolean", "default": False},
                "ids": {"type": "array", "items": {"type": "integer"},
                        "default": None},
                "o": {"type": "object", "default": None},
            }},
        }
        url = "/api/parity"
        method = "POST"

        def callback(self, n, s="x", x=0.5, f=False, ids=None, o=None):
            return {"n": n, "s": s, "x": x, "f": f, "ids": ids, "o": o}


def _rest_result(client, payload):
    r = client.post("/api/parity", json=payload)
    ok = r.status_code == 200 and r.json().get("success") is True
    return ok, (r.json().get("result") if ok else None)


def _mcp_result(mcp, payload):
    from fastmcp import Client

    async def _call():
        async with Client(mcp) as c:
            try:
                res = await c.call_tool("parity_tool", payload)
                return True, res.data
            except Exception:
                return False, None

    return asyncio.run(_call())


@pytest.mark.parametrize("payload,accepted", CASES)
def test_rest_and_mcp_agree(payload, accepted):
    _make_endpoint()
    server = Server.get_instance()
    client = TestClient(server.app)
    mcp = server.get_mcp()

    rest_ok, _ = _rest_result(client, payload)
    mcp_ok, _ = _mcp_result(mcp, payload)

    assert rest_ok == accepted, f"REST disagreed for {payload!r}: accepted={rest_ok}"
    assert mcp_ok == accepted, f"MCP disagreed for {payload!r}: accepted={mcp_ok}"
    assert rest_ok == mcp_ok, f"REST/MCP diverged for {payload!r}"


def test_default_injection_is_identical_on_both_transports():
    # Omitted optionals must reach the callback with the SAME injected
    # defaults on REST and MCP (finding 2 pinned as parity behavior).
    _make_endpoint()
    server = Server.get_instance()
    client = TestClient(server.app)
    mcp = server.get_mcp()

    rest_ok, rest_result = _rest_result(client, {"n": 1})
    mcp_ok, mcp_result = _mcp_result(mcp, {"n": 1})

    assert rest_ok and mcp_ok
    expected = {"n": 1, "s": "x", "x": 0.5, "f": False, "ids": None, "o": None}
    assert rest_result == expected
    assert mcp_result == expected
