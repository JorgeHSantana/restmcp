import asyncio
import inspect
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from restmcp.mcp import McpApp, _JSON_TO_PYTHON


# --- helpers ---

def _mock_fastmcp():
    mock_instance = MagicMock()
    mock_module = MagicMock()
    mock_module.FastMCP = MagicMock(return_value=mock_instance)
    return mock_module, mock_instance


def _build(handlers):
    mock_module, mock_mcp = _mock_fastmcp()
    with patch.dict(sys.modules, {"fastmcp": mock_module}):
        result = McpApp().build(handlers)
    return result, mock_mcp


def _make_handler(properties=None, callback=None, name="tool", description="desc"):
    handler = MagicMock()
    handler.mcp_definition = {
        "name": name,
        "description": description,
        "parameters": {"properties": properties or {}},
    }
    handler.callback = callback or (lambda: {})
    return handler


def _func(handler):
    """The flat tool function McpApp builds for one handler."""
    return McpApp()._build_tool_function(handler)


def _params(fn):
    return inspect.signature(fn).parameters


def _base_type(annotation):
    """Unwrap Annotated[T, Field(...)] -> T; otherwise return annotation."""
    if hasattr(annotation, "__metadata__"):
        return annotation.__origin__
    return annotation


# --- type mapping dict ---

def test_json_type_map_string():
    assert _JSON_TO_PYTHON["string"] is str

def test_json_type_map_integer():
    assert _JSON_TO_PYTHON["integer"] is int

def test_json_type_map_number():
    assert _JSON_TO_PYTHON["number"] is float

def test_json_type_map_boolean():
    assert _JSON_TO_PYTHON["boolean"] is bool

def test_json_type_map_object():
    assert _JSON_TO_PYTHON["object"] is dict


# --- build() ---

def test_build_returns_fastmcp_instance():
    mock_module, mock_mcp = _mock_fastmcp()
    with patch.dict(sys.modules, {"fastmcp": mock_module}):
        result = McpApp().build([])
    assert result is mock_mcp


def test_build_registers_one_tool_per_handler():
    handlers = [_make_handler(name="a"), _make_handler(name="b")]
    _, mock_mcp = _build(handlers)
    assert mock_mcp.add_tool.call_count == 2


def test_build_no_handlers_registers_nothing():
    _, mock_mcp = _build([])
    mock_mcp.add_tool.assert_not_called()


# --- flat signature (the args-nesting fix) ---

def test_tool_function_has_flat_signature():
    handler = _make_handler(properties={
        "device_id": {"type": "integer", "description": "Device id"},
        "tags": {"type": "array", "items": {"type": "string"}, "default": None},
    })
    params = list(_params(_func(handler)))
    assert params == ["device_id", "tags"]
    assert "args" not in params


def test_tool_function_routes_call_to_callback():
    def cb(device_id, tags=None):
        return {"device_id": device_id, "tags": tags}

    handler = _make_handler(
        properties={
            "device_id": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}, "default": None},
        },
        callback=cb,
    )
    fn = _func(handler)
    result = asyncio.run(fn(device_id=7, tags=["a"]))
    assert result == {"device_id": 7, "tags": ["a"]}


def test_tool_function_awaits_async_callback():
    received = {}

    async def cb(x):
        received["x"] = x
        return {"async": True}

    handler = _make_handler(properties={"x": {"type": "string"}}, callback=cb)
    fn = _func(handler)
    result = asyncio.run(fn(x="hi"))
    assert result == {"async": True}
    assert received == {"x": "hi"}


def test_tool_function_name_and_doc():
    fn = _func(_make_handler(name="my_tool", description="does things"))
    assert fn.__name__ == "my_tool"
    assert fn.__doc__ == "does things"


# --- per-parameter type mapping (via the flat signature annotations) ---

def test_string_field():
    p = _params(_func(_make_handler(properties={"s": {"type": "string"}})))
    assert _base_type(p["s"].annotation) is str


def test_integer_field():
    p = _params(_func(_make_handler(properties={"n": {"type": "integer"}})))
    assert _base_type(p["n"].annotation) is int


def test_number_field():
    p = _params(_func(_make_handler(properties={"f": {"type": "number"}})))
    assert _base_type(p["f"].annotation) is float


def test_boolean_field():
    p = _params(_func(_make_handler(properties={"b": {"type": "boolean"}})))
    assert _base_type(p["b"].annotation) is bool


def test_object_field():
    p = _params(_func(_make_handler(properties={"obj": {"type": "object"}})))
    assert _base_type(p["obj"].annotation) == Dict[str, Any]


def test_array_of_strings_field():
    p = _params(_func(_make_handler(
        properties={"tags": {"type": "array", "items": {"type": "string"}}}
    )))
    assert _base_type(p["tags"].annotation) == List[str]


def test_array_of_integers_field():
    p = _params(_func(_make_handler(
        properties={"ids": {"type": "array", "items": {"type": "integer"}}}
    )))
    assert _base_type(p["ids"].annotation) == List[int]


def test_unknown_type_falls_back_to_str():
    p = _params(_func(_make_handler(properties={"x": {"type": "null"}})))
    assert _base_type(p["x"].annotation) is str


def test_optional_field_when_default_is_none():
    p = _params(_func(_make_handler(
        properties={"x": {"type": "string", "default": None}}
    )))
    assert p["x"].default is None
    assert _base_type(p["x"].annotation) == Optional[str]


def test_description_carried_via_annotated():
    p = _params(_func(_make_handler(
        properties={"x": {"type": "string", "description": "the x value"}}
    )))
    annotation = p["x"].annotation
    assert hasattr(annotation, "__metadata__")
    field_info = annotation.__metadata__[0]
    assert field_info.description == "the x value"
