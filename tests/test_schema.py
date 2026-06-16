from restmcp.schema import tool_name_from_class


class GetDeviceEndpoint:
    pass


class CheckBatteryEndpoint:
    pass


class HTTPProxyEndpoint:
    name = "custom_name"


def test_tool_name_strips_suffix_and_snake_cases():
    assert tool_name_from_class(GetDeviceEndpoint) == "get_device"
    assert tool_name_from_class(CheckBatteryEndpoint) == "check_battery"


def test_tool_name_prefers_explicit_name_attribute():
    assert tool_name_from_class(HTTPProxyEndpoint) == "custom_name"


import inspect
from restmcp.schema import schema_for_annotation


def test_schema_for_primitives():
    assert schema_for_annotation(str) == {"type": "string"}
    assert schema_for_annotation(int) == {"type": "integer"}
    assert schema_for_annotation(float) == {"type": "number"}
    assert schema_for_annotation(bool) == {"type": "boolean"}


def test_schema_for_list_with_item_type():
    assert schema_for_annotation(list[int]) == {
        "type": "array",
        "items": {"type": "integer"},
    }


def test_schema_for_bare_list_defaults_items_to_string():
    assert schema_for_annotation(list) == {"type": "array", "items": {"type": "string"}}


def test_schema_for_dict_is_object():
    assert schema_for_annotation(dict[str, int]) == {"type": "object"}


def test_schema_for_missing_annotation_defaults_to_string():
    assert schema_for_annotation(inspect.Parameter.empty) == {"type": "string"}
