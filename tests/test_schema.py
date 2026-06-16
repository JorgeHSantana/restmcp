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


from typing import Annotated, Optional
from restmcp.schema import build_parameters


def test_build_parameters_reads_types_descriptions_and_defaults():
    def callback(
        self,
        device_id: Annotated[int, "Device id (1-5)"],
        tags: list[str] = None,
        limit: int = 10,
    ) -> dict:
        ...

    params = build_parameters(callback)
    assert params == {
        "properties": {
            "device_id": {"type": "integer", "description": "Device id (1-5)"},
            "tags": {"type": "array", "items": {"type": "string"}, "default": None},
            "limit": {"type": "integer", "default": 10},
        }
    }


def test_build_parameters_skips_self_and_varargs():
    def callback(self, *args, **kwargs):
        ...

    assert build_parameters(callback) == {"properties": {}}


def test_build_parameters_unwraps_optional():
    def callback(self, when: Optional[str] = None) -> dict:
        ...

    props = build_parameters(callback)["properties"]
    assert props["when"] == {"type": "string", "default": None}
