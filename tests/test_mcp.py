import sys
from typing import Dict, List
from unittest.mock import MagicMock, patch

from pythia.mcp import McpApp, _JSON_TO_PYTHON


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


def _get_model(mock_mcp):
    tool_wrapper = mock_mcp.add_tool.call_args[0][0]
    return tool_wrapper.__signature__.parameters["args"].annotation, tool_wrapper


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


# --- build ---

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


# --- tool wrapper ---

def test_tool_wrapper_calls_callback_with_args():
    received = {}

    def my_callback(x, n):
        received["x"] = x
        received["n"] = n
        return {"ok": True}

    handler = _make_handler(
        properties={"x": {"type": "string"}, "n": {"type": "integer"}},
        callback=my_callback,
    )
    _, mock_mcp = _build([handler])
    ModelClass, tool_wrapper = _get_model(mock_mcp)

    result = tool_wrapper(ModelClass(x="hello", n=7))
    assert result == {"ok": True}
    assert received == {"x": "hello", "n": 7}


def test_tool_wrapper_name_and_doc():
    handler = _make_handler(name="my_tool", description="does things")
    _, mock_mcp = _build([handler])
    _, tool_wrapper = _get_model(mock_mcp)
    assert tool_wrapper.__name__ == "my_tool"
    assert tool_wrapper.__doc__ == "does things"


# --- field types ---

def test_string_field():
    _, mock_mcp = _build([_make_handler(properties={"s": {"type": "string"}})])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["s"].annotation is str


def test_integer_field():
    _, mock_mcp = _build([_make_handler(properties={"n": {"type": "integer"}})])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["n"].annotation is int


def test_number_field():
    _, mock_mcp = _build([_make_handler(properties={"f": {"type": "number"}})])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["f"].annotation is float


def test_boolean_field():
    _, mock_mcp = _build([_make_handler(properties={"b": {"type": "boolean"}})])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["b"].annotation is bool


def test_object_field():
    from typing import Any
    _, mock_mcp = _build([_make_handler(properties={"obj": {"type": "object"}})])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["obj"].annotation == Dict[str, Any]


def test_array_of_strings_field():
    _, mock_mcp = _build([_make_handler(
        properties={"tags": {"type": "array", "items": {"type": "string"}}}
    )])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["tags"].annotation == List[str]


def test_array_of_integers_field():
    _, mock_mcp = _build([_make_handler(
        properties={"ids": {"type": "array", "items": {"type": "integer"}}}
    )])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["ids"].annotation == List[int]


def test_unknown_type_falls_back_to_str():
    _, mock_mcp = _build([_make_handler(properties={"x": {"type": "null"}})])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["x"].annotation is str


def test_optional_field_when_default_is_none():
    _, mock_mcp = _build([_make_handler(
        properties={"x": {"type": "string", "default": None}}
    )])
    ModelClass, _ = _get_model(mock_mcp)
    assert ModelClass.model_fields["x"].is_required() is False
