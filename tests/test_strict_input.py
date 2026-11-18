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
    # A query string has no types: true/false (any case) are the only spellings.
    assert rest.get("/api/flag-query?flag=true").json()["result"] == {"flag": True}
    assert rest.get("/api/flag-query?flag=false").json()["result"] == {"flag": False}
    assert rest.get("/api/flag-query").json()["result"] == {"flag": False}
    for bad in ("yes", "1", "0", "on", "t", SECRET):
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
    # an annotation that contradicts its own default is the author's type
    # error: it raises (the hand-written enum case only warns, see below)
    with pytest.raises(TypeError, match="BadDefaultEndpoint.*mode"):
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


def _register_scoped():
    class ScopedTypedEndpoint(Endpoint):
        required_scope = "write"
        mcp_definition = {"name": "scoped_typed", "description": "x",
                          "parameters": {"properties": {"n": {"type": "integer"}}}}
        url = "/api/scoped-typed"
        method = "POST"

        def callback(self, n):
            return {"n": n}


def _mcp_http_call(key, tool, arguments):
    app = Server.get_instance().asgi_app(mcp_path="/mcp-protocol")
    h = {**_H, "Authorization": f"Bearer {key}"}
    with TestClient(app) as c:
        r = c.post("/mcp-protocol/", json=_INIT, headers=h)
        assert r.status_code == 200, r.text
        sid = r.headers.get("mcp-session-id")
        h = {**h, **({"mcp-session-id": sid} if sid else {})}
        c.post("/mcp-protocol/", headers=h,
               json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = c.post("/mcp-protocol/", headers=h, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}})
    data = [l for l in r.text.splitlines() if l.startswith("data:")]
    return json.loads(data[-1][len("data:"):])["result"]


@pytest.mark.parametrize("arguments", [{"n": SECRET}, {}, {"n": 1, "bogus": 1}, {"n": 1}])
def test_mcp_scope_is_checked_before_arguments(monkeypatch, arguments):
    """Same order as REST: an under-scoped key gets forbidden_scope whatever
    the arguments (valid or not); the scoped key gets the validation result."""
    pytest.importorskip("fastmcp")
    monkeypatch.setenv("AUTH_API_KEY", "painel:sk_1:read, campo:sk_2:read+write")
    _register_scoped()
    result = _mcp_http_call("sk_1", "scoped_typed", arguments)
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "forbidden_scope"
    assert SECRET not in json.dumps(result)
    with TestClient(Server.get_instance().app) as c:
        r = c.post("/api/scoped-typed", json=arguments,
                   headers={"Authorization": "Bearer sk_1"})
    assert r.status_code == 403 and r.json()["code"] == "forbidden_scope"


def test_mcp_scoped_key_still_gets_validation_error(monkeypatch):
    pytest.importorskip("fastmcp")
    monkeypatch.setenv("AUTH_API_KEY", "painel:sk_1:read, campo:sk_2:read+write")
    _register_scoped()
    _assert_mcp_validation(_mcp_http_call("sk_2", "scoped_typed", {"n": SECRET}),
                           "scoped_typed", "n")
    ok = _mcp_http_call("sk_2", "scoped_typed", {"n": 3})
    assert not ok.get("isError") and ok["structuredContent"] == {"n": 3}


def test_mcp_without_auth_validates_as_before():
    # auth disabled (autouse fixture): no scope check, validation answers
    pytest.importorskip("fastmcp")
    import asyncio

    from fastmcp import Client

    _register_scoped()

    async def go(args):
        async with Client(Server.get_instance().get_mcp()) as c:
            return await c.call_tool("scoped_typed", args, raise_on_error=False)

    res = asyncio.run(go({"n": "x"}))
    assert res.is_error and res.structured_content["code"] == "validation_error"
    assert asyncio.run(go({"n": 2})).structured_content == {"n": 2}


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


# --- fix round 1: author declarations keep importing; client input is strict --

import warnings


@pytest.mark.parametrize("default,expected", [(0, False), (1, True), ("false", False),
                                              ("yes", True), ("on", True)])
def test_lax_boolean_defaults_still_register(rest, default, expected):
    # a bump from 0.7 must never stop an app from importing: boolean DEFAULTS
    # keep 0.7's lax rules; strictness is for what clients send
    from restmcp.schema import field_spec_for

    _, value = field_spec_for("flag", {"type": "boolean", "default": default})
    assert value is expected

    class LaxDefaultEndpoint(Endpoint):
        mcp_definition = {"name": "lax_default", "description": "x",
                          "parameters": {"properties": {
                              "flag": {"type": "boolean", "default": default}}}}
        url = "/api/lax-default"
        method = "POST"

        def callback(self, flag):
            return {"flag": flag}

    assert rest.post("/api/lax-default", json={}).json()["result"] == {"flag": expected}
    # ...but the client still has to send a JSON boolean
    _assert_rest_validation(rest.post("/api/lax-default", json={"flag": default}),
                            "lax_default", "flag")


def test_inferred_bool_default_zero_still_registers(rest):
    class ZeroDefaultEndpoint(Endpoint):
        url = "/api/zero-default"
        method = "POST"

        def callback(self, flag: bool = 0):  # type: ignore[assignment]
            """x.

            Returns: the flag.
            """
            return {"flag": flag}

    assert rest.post("/api/zero-default", json={}).json()["result"] == {"flag": False}


def test_boolean_default_that_0_7_rejected_still_raises():
    from restmcp.schema import field_spec_for

    with pytest.raises(TypeError, match="flag"):
        field_spec_for("flag", {"type": "boolean", "default": "banana"})


def _mcp_memory_call(tool, arguments):
    import asyncio

    from fastmcp import Client

    async def go():
        async with Client(Server.get_instance().get_mcp()) as c:
            return await c.call_tool(tool, arguments, raise_on_error=False)

    return asyncio.run(go())


def test_hand_written_enum_default_outside_set_warns_not_raises(rest):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        class LegacyEnumEndpoint(Endpoint):
            mcp_definition = {"name": "legacy_enum", "description": "x",
                              "parameters": {"properties": {
                                  "color": {"type": "string", "enum": ["red", "blue"],
                                            "default": "green"}}}}
            url = "/api/legacy-enum"
            method = "POST"

            def callback(self, color):
                return {"color": color}

    msgs = [str(w.message) for w in caught]
    assert any("legacy_enum" in m and "color" in m for m in msgs), msgs
    # default kept when omitted...
    assert rest.post("/api/legacy-enum", json={}).json()["result"] == {"color": "green"}
    assert _mcp_memory_call("legacy_enum", {}).structured_content == {"color": "green"}
    # ...but a client cannot send it, nor anything else outside the set
    _assert_rest_validation(rest.post("/api/legacy-enum", json={"color": "green"}),
                            "legacy_enum", "color")
    res = _mcp_memory_call("legacy_enum", {"color": "green"})
    assert res.is_error and res.structured_content["code"] == "validation_error"
    assert rest.post("/api/legacy-enum", json={"color": "blue"}).json()["result"] == \
        {"color": "blue"}


@pytest.mark.parametrize("spelling,expected", [("true", True), ("True", True),
                                               ("TRUE", True), ("false", False),
                                               ("False", False), ("FALSE", False)])
def test_query_bool_is_case_insensitive(rest, spelling, expected):
    r = rest.get(f"/api/flag-query?flag={spelling}")
    assert r.json()["result"] == {"flag": expected}


def test_unknown_parameter_name_is_truncated(rest, mcp):
    long_name = "x" * 200
    body = _assert_rest_validation(rest.post("/api/typed", json={"n": 1, long_name: 1}),
                                   "typed")
    assert "x" * 64 in body["error"]
    assert "x" * 65 not in body["error"]
    sc = _assert_mcp_validation(_call(mcp, "typed", {"n": 1, long_name: 1}), "typed")
    assert "x" * 65 not in sc["error"]


def test_build_fails_closed_without_arg_model():
    pytest.importorskip("fastmcp")
    from restmcp.mcp import McpApp

    class NoModel:
        mcp_definition = {"name": "no_model", "description": "x",
                          "parameters": {"properties": {}}}

        @staticmethod
        def callback():
            return {}

    with pytest.raises(TypeError, match="no_model"):
        McpApp().build([NoModel()])


@pytest.mark.parametrize("prop,sent,expected", [
    # typed enums hand the callback the declared type, as in 0.7
    ({"type": "integer", "enum": [1, 2]}, "2.0", 2),
    ({"type": "integer", "enum": [1, 2]}, 2.0, 2),
    ({"type": "number", "enum": [1, 2]}, 1, 1.0),
    ({"type": "number", "enum": [1, 2]}, "2", 2.0),
    ({"type": "string", "enum": ["1", "2"]}, "1", "1"),
    # untyped (mixed) enum: a string that is itself a member stays a string
    ({"enum": ["1", 2]}, "1", "1"),
    ({"enum": ["1", 2]}, "2", 2),
    ({"enum": ["auto", True]}, True, True),
])
def test_enum_input_keeps_declared_type(prop, sent, expected):
    from pydantic import TypeAdapter
    from restmcp.schema import python_type_for

    got = TypeAdapter(python_type_for(prop)).validate_python(sent)
    assert got == expected and type(got) is type(expected)


@pytest.mark.parametrize("prop,sent", [
    ({"type": "string", "enum": [1, 2]}, 1),     # 0.7: str, never an int
    ({"type": "integer", "enum": [1, 2]}, True),
    ({"type": "integer", "enum": [1, 2]}, "2.5"),
    ({"enum": ["auto", True]}, 1),
    ({"enum": ["auto", True]}, "true"),
    ({"enum": ["1", 2]}, True),
])
def test_enum_input_rejections(prop, sent):
    from pydantic import TypeAdapter, ValidationError as PVE
    from restmcp.schema import python_type_for

    with pytest.raises(PVE):
        TypeAdapter(python_type_for(prop)).validate_python(sent)


def _register_more():
    from typing import Union

    class MoreEndpoint(Endpoint):
        url = "/api/more"
        method = "GET"

        def callback(self, ratio: Literal[1.5, 2.5] = 1.5,
                     either: Union[Literal["a"], Literal["b"]] = "a",
                     mix: Literal[True, "auto"] = "auto"):
            """x.

            Returns: the values.
            """
            return {"ratio": ratio, "either": either, "mix": mix}


def test_float_union_and_mixed_literals(rest):
    _register_more()
    with TestClient(Server.get_instance().app) as c:
        props = {t["name"]: t for t in c.get("/mcp/tools").json()["tools"]}["more"][
            "parameters"]["properties"]
        assert props["ratio"] == {"type": "number", "enum": [1.5, 2.5], "default": 1.5}
        assert props["either"] == {"type": "string", "enum": ["a", "b"], "default": "a"}
        assert props["mix"] == {"enum": [True, "auto"], "default": "auto"}
        assert c.get("/api/more?ratio=2.5&either=b&mix=true").json()["result"] == \
            {"ratio": 2.5, "either": "b", "mix": True}
        assert c.get("/api/more?mix=TRUE").json()["result"]["mix"] is True
        assert c.get("/api/more?mix=auto").json()["result"]["mix"] == "auto"
        for bad in ("ratio=3.5", "either=c", "mix=1", "mix=yes"):
            r = c.get(f"/api/more?{bad}")
            assert r.status_code == 400 and r.json()["code"] == "validation_error", bad


# --- fix round 2 ---------------------------------------------------------------

from typing import Annotated, Union


def _tools_list_props(tool):
    import asyncio

    from fastmcp import Client

    async def go():
        async with Client(Server.get_instance().get_mcp()) as c:
            return {t.name: t for t in await c.list_tools()}

    t = asyncio.run(go())[tool]
    # MCP SDK v2 (fastmcp 4.x) renamed inputSchema -> input_schema
    schema = getattr(t, "input_schema", None) or t.inputSchema
    return schema["properties"]


def test_tools_list_keeps_description_on_literal_and_enum():
    pytest.importorskip("fastmcp")

    class DescribedEndpoint(Endpoint):
        url = "/api/described"
        method = "POST"

        def callback(self, mode: Annotated[Literal["a", "b"], "the mode"] = "a",
                     maybe: Annotated[Optional[Literal["x", "y"]], "maybe one"] = None,
                     req: Annotated[Literal[1, 2], "required level"] = 1):
            """x.

            Returns: the values.
            """
            return {}

    class HandDescribedEndpoint(Endpoint):
        mcp_definition = {"name": "hand_described", "description": "x",
                          "parameters": {"properties": {
                              "color": {"type": "string", "enum": ["red", "blue"],
                                        "description": "paint color", "default": "red"},
                              "mix": {"enum": ["auto", True], "description": "mixed"},
                              "tags": {"type": "array", "description": "tag list",
                                       "items": {"type": "string", "enum": ["p", "q"]},
                                       "default": None},
                          }}}
        url = "/api/hand-described"
        method = "POST"

        def callback(self, color, mix, tags=None):
            return {}

    props = _tools_list_props("described")
    assert props["mode"]["description"] == "the mode"
    assert props["mode"]["enum"] == ["a", "b"]
    assert props["mode"]["type"] == "string"
    assert props["mode"]["default"] == "a"
    assert props["maybe"]["description"] == "maybe one"
    assert props["maybe"]["default"] is None
    assert _find_enum(props["maybe"]) == [["x", "y"]]
    assert {"type": "string", "enum": ["x", "y"]} in props["maybe"]["anyOf"]
    assert props["req"]["description"] == "required level"
    assert props["req"]["type"] == "integer" and props["req"]["enum"] == [1, 2]

    hand = _tools_list_props("hand_described")
    assert hand["color"] == {"type": "string", "enum": ["red", "blue"],
                             "description": "paint color", "default": "red"} or (
        hand["color"]["description"] == "paint color"
        and hand["color"]["enum"] == ["red", "blue"]
        and hand["color"]["type"] == "string" and hand["color"]["default"] == "red")
    assert hand["mix"]["description"] == "mixed"
    assert hand["mix"]["enum"] == ["auto", True]
    assert hand["tags"]["description"] == "tag list"
    assert _find_enum(hand["tags"]) == [["p", "q"]]


def test_array_items_enum_default_outside_set_warns_not_raises(rest):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        class LegacyItemsEndpoint(Endpoint):
            mcp_definition = {"name": "legacy_items", "description": "x",
                              "parameters": {"properties": {
                                  "tags": {"type": "array",
                                           "items": {"type": "string", "enum": ["a", "b"]},
                                           "default": ["c"]}}}}
            url = "/api/legacy-items"
            method = "POST"

            def callback(self, tags):
                return {"tags": tags}

    msgs = [str(w.message) for w in caught]
    assert any("legacy_items" in m and "tags" in m for m in msgs), msgs
    assert rest.post("/api/legacy-items", json={}).json()["result"] == {"tags": ["c"]}
    _assert_rest_validation(rest.post("/api/legacy-items", json={"tags": ["c"]}),
                            "legacy_items", "tags")
    assert rest.post("/api/legacy-items", json={"tags": ["b"]}).json()["result"] == \
        {"tags": ["b"]}


def test_lax_bool_default_inside_bool_enum_does_not_warn():
    from restmcp.schema import field_spec_for

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _, value = field_spec_for("f", {"type": "boolean", "enum": [True, False],
                                        "default": "false"}, "t")
    assert value is False


@pytest.mark.parametrize("prop", [
    {"type": "string", "enum": [1, 2]},
    {"type": "integer", "enum": ["a", "b"]},
    {"type": "boolean", "enum": [1, 0]},
    {"type": "array", "items": {"type": "string", "enum": [1]}},
])
def test_typed_enum_without_matching_member_warns(prop):
    from restmcp.schema import field_spec_for

    with pytest.warns(UserWarning, match=r"tool_x.*p"):
        field_spec_for("p", prop, "tool_x")


@pytest.mark.parametrize("prop", [
    {"type": "string", "enum": ["a"]},
    {"type": "integer", "enum": [1, 2]},
    {"type": "number", "enum": [1, 2.5]},
    {"type": "boolean", "enum": [True]},
    {"enum": [1, "a"]},
])
def test_typed_enum_with_matching_member_is_silent(prop):
    from restmcp.schema import field_spec_for

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        field_spec_for("p", prop, "tool_x")


def test_literal_union_dedup_keeps_bool_and_int_apart():
    from restmcp.schema import schema_for_annotation

    assert schema_for_annotation(Union[Literal[1], Literal[True]]) == {"enum": [1, True]}
    assert schema_for_annotation(Union[Literal[1], Literal[1, 2]]) == \
        {"type": "integer", "enum": [1, 2]}


def test_untyped_enum_hands_the_matched_member():
    from pydantic import TypeAdapter
    from restmcp.schema import python_type_for

    ta = TypeAdapter(python_type_for({"enum": [1, 2]}))
    for sent in (1.0, 1, "1", "1.0"):
        got = ta.validate_python(sent)
        assert got == 1 and type(got) is int, sent


def test_principal_without_scopes_is_internal_error_not_crash(monkeypatch):
    """A custom auth layer that publishes a principal without "scopes": the
    middleware answers the generic internal-error envelope (as the wrapper did
    in 0.7) — no raw JSON-RPC error — and the callback does not run."""
    pytest.importorskip("fastmcp")
    from restmcp.auth import current_auth

    monkeypatch.setenv("AUTH_API_KEY", "painel:sk_1:read")
    ran = []

    class OddPrincipalEndpoint(Endpoint):
        required_scope = "write"
        mcp_definition = {"name": "odd_principal", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/odd-principal"
        method = "POST"

        def callback(self):
            ran.append(1)
            return {}

    token = current_auth.set({"name": "custom"})
    try:
        res = _mcp_memory_call("odd_principal", {})
    finally:
        current_auth.reset(token)
    assert res.is_error
    assert res.structured_content["error_type"] == "InternalServerError"
    assert res.structured_content["error"] == "Internal server error"
    assert ran == []
