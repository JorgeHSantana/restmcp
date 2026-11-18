"""Input strictness (0.8.0): strict booleans, ``Literal`` -> ``enum`` and the
``validation_error`` code.

Every argument the framework rejects — wrong type, missing required, unknown
parameter, value outside an enum, a non-boolean where a boolean is declared —
answers with the shared error envelope and ``code: "validation_error"``: HTTP
400 on REST, ``isError`` with the envelope as ``structuredContent`` on MCP.
The message names the parameter, never the rejected value (it may be a secret).
"""
import json
from typing import Literal, Optional

import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.exceptions import ValidationError

SECRET = "s3cr3t-t0ken-value"

_H = {"Accept": "application/json, text/event-stream"}
_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"}}}


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)


def _register():
    class FlagsEndpoint(Endpoint):
        url = "/api/flags"
        method = "POST"

        def callback(self, required: bool, optional: Optional[bool] = None,
                     defaulted: bool = False):
            """Echo the flags.

            Returns: the three flags as received.
            """
            return {"required": required, "optional": optional,
                    "defaulted": defaulted}

    class FlagQueryEndpoint(Endpoint):
        url = "/api/flag-query"
        method = "GET"

        def callback(self, flag: bool = False):
            """Echo the flag.

            Returns: the flag as received.
            """
            return {"flag": flag}

    class ChooseEndpoint(Endpoint):
        url = "/api/choose"
        method = "POST"

        def callback(self, mode: Literal["a", "b"],
                     maybe: Optional[Literal["x", "y"]] = None,
                     picked: Literal["x", "y"] = "x",
                     tags: Optional[list[Literal["p", "q"]]] = None,
                     level: Literal[1, 2] = 1):
            """Echo the choices.

            Returns: the choices as received.
            """
            return {"mode": mode, "maybe": maybe, "picked": picked,
                    "tags": tags, "level": level}

    class ChooseQueryEndpoint(Endpoint):
        url = "/api/choose-query"
        method = "GET"

        def callback(self, mode: Literal["a", "b"] = "a", level: Literal[1, 2] = 1):
            """Echo the choices.

            Returns: the choices as received.
            """
            return {"mode": mode, "level": level}

    class HandEnumEndpoint(Endpoint):
        mcp_definition = {"name": "hand_enum", "description": "x",
                          "parameters": {"properties": {
                              "color": {"type": "string", "enum": ["red", "blue"]},
                          }}}
        url = "/api/hand-enum"
        method = "POST"

        def callback(self, color):
            return {"color": color}

    class TypedEndpoint(Endpoint):
        mcp_definition = {"name": "typed", "description": "x",
                          "parameters": {"properties": {
                              "n": {"type": "integer"},
                              "token": {"type": "string", "default": None},
                          }}}
        url = "/api/typed"
        method = "POST"

        def callback(self, n, token=None):
            return {"n": n}

    class DomainEndpoint(Endpoint):
        mcp_definition = {"name": "domain", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/domain"
        method = "POST"

        def callback(self):
            raise ValidationError("regra de negócio")


@pytest.fixture
def rest():
    _register()
    with TestClient(Server.get_instance().app) as c:
        yield c


@pytest.fixture
def mcp():
    pytest.importorskip("fastmcp")
    _register()
    app = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")
    with TestClient(app) as c:
        r = c.post("/mcp-protocol/", json=_INIT, headers=_H)
        assert r.status_code == 200
        sid = r.headers.get("mcp-session-id")
        h = {**_H, **({"mcp-session-id": sid} if sid else {})}
        c.post("/mcp-protocol/", headers=h,
               json={"jsonrpc": "2.0", "method": "notifications/initialized"})

        def rpc(method, params):
            r = c.post("/mcp-protocol/", headers=h, json={
                "jsonrpc": "2.0", "id": 2, "method": method, "params": params})
            assert r.status_code == 200
            data = [l for l in r.text.splitlines() if l.startswith("data:")]
            payload = json.loads(data[-1][len("data:"):]) if data else r.json()
            assert "error" not in payload, payload
            return payload["result"]

        yield rpc


def _call(rpc, tool, arguments):
    return rpc("tools/call", {"name": tool, "arguments": arguments})


def _assert_rest_validation(r, tool, *params):
    assert r.status_code == 400, r.text
    body = r.json()
    assert set(body) == {"tool", "error", "success", "error_type", "code"}
    assert body["tool"] == tool
    assert body["success"] is False
    assert body["error_type"] == "ValidationError"
    assert body["code"] == "validation_error"
    for p in params:
        assert p in body["error"]
    assert SECRET not in r.text
    return body


def _assert_mcp_validation(result, tool, *params):
    assert result["isError"] is True, result
    sc = result["structuredContent"]
    assert sc["tool"] == tool
    assert sc["success"] is False
    assert sc["error_type"] == "ValidationError"
    assert sc["code"] == "validation_error"
    assert result["content"][0]["text"] == sc["error"]
    for p in params:
        assert p in sc["error"]
    assert SECRET not in json.dumps(result)
    return sc


# --- 1. strict booleans ------------------------------------------------------

LENIENT = ["yes", "true", "false", 1, 0, "on", "off", "1", SECRET]


@pytest.mark.parametrize("value", LENIENT)
@pytest.mark.parametrize("param", ["required", "optional", "defaulted"])
def test_rest_bool_rejects_non_boolean(rest, param, value):
    payload = {"required": True, param: value}
    r = rest.post("/api/flags", json=payload)
    _assert_rest_validation(r, "flags", param)


@pytest.mark.parametrize("value", LENIENT)
@pytest.mark.parametrize("param", ["required", "optional", "defaulted"])
def test_mcp_bool_rejects_non_boolean(mcp, param, value):
    result = _call(mcp, "flags", {"required": True, param: value})
    _assert_mcp_validation(result, "flags", param)


def test_bool_accepts_json_booleans_and_defaults(rest, mcp):
    cases = [
        ({"required": True}, {"required": True, "optional": None, "defaulted": False}),
        ({"required": False, "optional": True, "defaulted": True},
         {"required": False, "optional": True, "defaulted": True}),
        ({"required": True, "optional": False}, {"required": True, "optional": False,
                                                 "defaulted": False}),
        ({"required": True, "optional": None}, {"required": True, "optional": None,
                                                "defaulted": False}),
    ]
    for payload, expected in cases:
        r = rest.post("/api/flags", json=payload)
        assert r.status_code == 200, r.text
        assert r.json()["result"] == expected
        result = _call(mcp, "flags", payload)
        assert not result.get("isError"), result
        assert result["structuredContent"] == expected


def test_bool_query_string_takes_only_true_and_false(rest):
    # A query string has no types: the JSON literals are the only spellings.
    assert rest.get("/api/flag-query?flag=true").json()["result"] == {"flag": True}
    assert rest.get("/api/flag-query?flag=false").json()["result"] == {"flag": False}
    assert rest.get("/api/flag-query").json()["result"] == {"flag": False}
    for bad in ("yes", "1", "0", "on", "True", SECRET):
        _assert_rest_validation(rest.get(f"/api/flag-query?flag={bad}"),
                                "flag_query", "flag")


def test_bool_in_body_is_not_parsed_like_query(rest):
    # body "true" (a string) is still rejected: only the query string is untyped
    r = rest.post("/api/flags", json={"required": "true"})
    _assert_rest_validation(r, "flags", "required")


def test_integers_still_reject_booleans(rest, mcp):
    _assert_rest_validation(rest.post("/api/typed", json={"n": True}), "typed", "n")
    _assert_mcp_validation(_call(mcp, "typed", {"n": False}), "typed", "n")


def test_bool_schema_is_boolean(mcp):
    tools = {t["name"]: t for t in mcp("tools/list", {})["tools"]}
    props = tools["flags"]["inputSchema"]["properties"]
    assert props["required"]["type"] == "boolean"
    assert props["defaulted"] == {"type": "boolean", "default": False} or \
        props["defaulted"]["type"] == "boolean"


# --- 2. Literal -> enum --------------------------------------------------------

def test_literal_becomes_enum_in_mcp_definition(rest):
    catalog = {t["name"]: t for t in rest.get("/mcp/tools").json()["tools"]}
    props = catalog["choose"]["parameters"]["properties"]
    assert props["mode"] == {"type": "string", "enum": ["a", "b"]}
    assert props["maybe"] == {"type": "string", "enum": ["x", "y"], "default": None}
    assert props["picked"] == {"type": "string", "enum": ["x", "y"], "default": "x"}
    assert props["tags"] == {"type": "array",
                             "items": {"type": "string", "enum": ["p", "q"]},
                             "default": None}
    assert props["level"] == {"type": "integer", "enum": [1, 2], "default": 1}


def test_literal_enum_in_openapi(rest):
    op = rest.get("/openapi.json").json()["paths"]["/api/choose"]["post"]
    props = op["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert props["mode"]["enum"] == ["a", "b"]
    assert props["tags"]["items"]["enum"] == ["p", "q"]
    params = rest.get("/openapi.json").json()["paths"]["/api/choose-query"]["get"]["parameters"]
    assert {p["name"]: p["schema"]["enum"] for p in params} == {"mode": ["a", "b"],
                                                                "level": [1, 2]}


def _find_enum(schema):
    """Every enum list anywhere inside a JSON-Schema fragment."""
    found = []
    if isinstance(schema, dict):
        if "enum" in schema:
            found.append(schema["enum"])
        for v in schema.values():
            found += _find_enum(v)
    elif isinstance(schema, list):
        for v in schema:
            found += _find_enum(v)
    return found


def test_literal_enum_in_mcp_tools_list(mcp):
    tools = {t["name"]: t for t in mcp("tools/list", {})["tools"]}
    props = tools["choose"]["inputSchema"]["properties"]
    assert props["mode"]["enum"] == ["a", "b"]
    assert _find_enum(props["maybe"]) == [["x", "y"]]
    assert _find_enum(props["picked"]) == [["x", "y"]]
    assert _find_enum(props["tags"]) == [["p", "q"]]
    assert _find_enum(props["level"]) == [[1, 2]]
    assert tools["choose"]["inputSchema"]["required"] == ["mode"]
    assert tools["hand_enum"]["inputSchema"]["properties"]["color"]["enum"] == ["red", "blue"]


@pytest.mark.parametrize("payload,param", [
    ({"mode": SECRET}, "mode"),
    ({"mode": "a", "maybe": SECRET}, "maybe"),
    ({"mode": "a", "picked": "z"}, "picked"),
    ({"mode": "a", "tags": ["p", SECRET]}, "tags"),
    ({"mode": "a", "level": 3}, "level"),
    ({"mode": "a", "level": True}, "level"),
    ({"mode": "a", "level": "x"}, "level"),
])
def test_value_outside_enum_rejected(rest, mcp, payload, param):
    _assert_rest_validation(rest.post("/api/choose", json=payload), "choose", param)
    _assert_mcp_validation(_call(mcp, "choose", payload), "choose", param)


def test_values_inside_enum_accepted(rest, mcp):
    payload = {"mode": "b", "maybe": "y", "picked": "y", "tags": ["q", "p"], "level": 2}
    r = rest.post("/api/choose", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["result"] == payload
    result = _call(mcp, "choose", payload)
    assert not result.get("isError"), result
    assert result["structuredContent"] == payload
    # omitted -> defaults
    expected = {"mode": "a", "maybe": None, "picked": "x", "tags": None, "level": 1}
    assert rest.post("/api/choose", json={"mode": "a"}).json()["result"] == expected
    assert _call(mcp, "choose", {"mode": "a"})["structuredContent"] == expected


def test_enum_from_query_string(rest):
    r = rest.get("/api/choose-query?mode=b&level=2")
    assert r.json()["result"] == {"mode": "b", "level": 2}
    _assert_rest_validation(rest.get("/api/choose-query?mode=c"), "choose_query", "mode")
    _assert_rest_validation(rest.get("/api/choose-query?level=3"), "choose_query", "level")


def test_hand_written_enum_is_enforced(rest, mcp):
    assert rest.post("/api/hand-enum", json={"color": "red"}).json()["result"] == \
        {"color": "red"}
    _assert_rest_validation(rest.post("/api/hand-enum", json={"color": "green"}),
                            "hand_enum", "color")
    _assert_mcp_validation(_call(mcp, "hand_enum", {"color": "green"}),
                           "hand_enum", "color")


def test_literal_default_outside_enum_fails_at_registration():
    with pytest.raises(ValueError, match="mode"):
        class BadDefaultEndpoint(Endpoint):
            url = "/api/bad-default"
            method = "POST"

            def callback(self, mode: Literal["a", "b"] = "c"):
                """x.

                Returns: nothing.
                """


# --- 3. code "validation_error" ------------------------------------------------

@pytest.mark.parametrize("payload,param", [
    ({"n": SECRET}, "n"),                    # wrong type
    ({}, "n"),                               # missing required
    ({"n": 1, "bogus": SECRET}, "bogus"),    # unknown parameter
    ({"n": 1, "token": 12345}, "token"),     # wrong type on an optional
])
def test_validation_error_code_rest_and_mcp(rest, mcp, payload, param):
    body = _assert_rest_validation(rest.post("/api/typed", json=payload), "typed", param)
    sc = _assert_mcp_validation(_call(mcp, "typed", payload), "typed", param)
    # one formatter, one message, on both transports
    assert body == sc


def test_body_not_json_has_validation_error_code(rest):
    r = rest.post("/api/typed", content=b"{not json " + SECRET.encode(),
                  headers={"content-type": "application/json"})
    _assert_rest_validation(r, "typed")
    r = rest.post("/api/typed", json=[1, 2])
    _assert_rest_validation(r, "typed")


def test_domain_validation_error_keeps_its_own_code(rest, mcp):
    # a ValidationError raised by the callback is the author's, not the
    # framework's: code stays whatever the author set (None here)
    r = rest.post("/api/domain", json={})
    assert r.status_code == 400
    assert r.json()["code"] is None
    result = _call(mcp, "domain", {})
    assert result["isError"] is True
    assert result["structuredContent"]["code"] is None


def test_mcp_validation_runs_before_scope(monkeypatch):
    """Ordering is unchanged: a scoped tool called with bad arguments by a key
    without the scope still answers validation_error (validation first)."""
    pytest.importorskip("fastmcp")
    monkeypatch.setenv("AUTH_API_KEY", "painel:sk_1:read")

    class ScopedTypedEndpoint(Endpoint):
        required_scope = "write"
        mcp_definition = {"name": "scoped_typed", "description": "x",
                          "parameters": {"properties": {"n": {"type": "integer"}}}}
        url = "/api/scoped-typed"
        method = "POST"

        def callback(self, n):
            return {"n": n}

    from fastmcp import Client

    import asyncio

    async def go():
        async with Client(Server.get_instance().get_mcp()) as c:
            return await c.call_tool("scoped_typed", {"n": "x"}, raise_on_error=False)

    res = asyncio.run(go())
    assert res.is_error
    assert res.structured_content["code"] == "validation_error"


def test_enum_members_keep_their_json_type():
    # pydantic matches Literal members by equality (1 == True); the enum must
    # not let a boolean through as 1, nor a number through as True.
    from pydantic import TypeAdapter, ValidationError as PVE
    from restmcp.schema import python_type_for

    ints = TypeAdapter(python_type_for({"type": "integer", "enum": [1, 2]}))
    assert ints.validate_python(2) == 2
    assert ints.validate_python("2") == 2
    for bad in (True, 3, "x"):
        with pytest.raises(PVE):
            ints.validate_python(bad)

    bools = TypeAdapter(python_type_for({"type": "boolean", "enum": [True]}))
    assert bools.validate_python(True) is True
    for bad in (1, "true", False):
        with pytest.raises(PVE):
            bools.validate_python(bad)


def test_unsupported_enum_is_published_not_enforced():
    # floats/objects cannot be a typing.Literal: the property keeps its plain
    # type (the pre-0.8.0 behaviour for every enum)
    from restmcp.schema import python_type_for

    assert python_type_for({"type": "string", "enum": [{"a": 1}]}) is str
    from typing import get_args
    assert get_args(python_type_for({"type": "number", "enum": [0.5, 1.5]}))[0] is float
