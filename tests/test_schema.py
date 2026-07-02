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


def test_build_parameters_unwraps_pep604_union():
    def callback(self, count: int | None = None) -> dict:
        ...

    props = build_parameters(callback)["properties"]
    assert props["count"] == {"type": "integer", "default": None}


from restmcp.schema import build_mcp_definition


def test_build_mcp_definition_uses_docstring_and_signature():
    class GetWidgetEndpoint:
        def callback(self, widget_id: Annotated[int, "Widget id"]) -> dict:
            """Return one widget by id."""
            ...

    definition = build_mcp_definition(GetWidgetEndpoint)
    assert definition == {
        "name": "get_widget",
        "description": "Return one widget by id.",
        "parameters": {
            "properties": {
                "widget_id": {"type": "integer", "description": "Widget id"},
            }
        },
    }


def test_build_mcp_definition_description_falls_back_to_name():
    class PingEndpoint:
        def callback(self) -> dict:
            ...

    definition = build_mcp_definition(PingEndpoint)
    assert definition["name"] == "ping"
    assert definition["description"] == "ping"
    assert definition["parameters"] == {"properties": {}}


def test_optional_wrapping_annotated_keeps_type_and_description():
    from typing import Annotated, Optional

    from restmcp.schema import build_parameters

    def cb(self, a: Optional[Annotated[int, "device id"]] = None):
        pass

    props = build_parameters(cb)["properties"]
    assert props["a"]["type"] == "integer"
    assert props["a"]["description"] == "device id"
    assert props["a"]["default"] is None


def test_annotated_wrapping_optional_still_works():
    from typing import Annotated, Optional

    from restmcp.schema import build_parameters

    def cb(self, a: Annotated[Optional[int], "device id"] = None):
        pass

    props = build_parameters(cb)["properties"]
    assert props["a"]["type"] == "integer"
    assert props["a"]["description"] == "device id"


def test_python_type_for_primitives():
    from typing import Annotated, get_origin, get_args
    from restmcp.schema import python_type_for

    assert python_type_for({"type": "string"}) is str
    assert python_type_for({"type": "boolean"}) is bool
    # integer/number carry the anti-bool BeforeValidator, so they are Annotated
    int_ann = python_type_for({"type": "integer"})
    assert get_args(int_ann)[0] is int
    num_ann = python_type_for({"type": "number"})
    assert get_args(num_ann)[0] is float


def test_python_type_for_array_and_object():
    from typing import List, Dict, Any, get_origin, get_args
    from restmcp.schema import python_type_for

    arr = python_type_for({"type": "array", "items": {"type": "string"}})
    assert get_origin(arr) is list
    assert get_args(arr)[0] is str

    obj = python_type_for({"type": "object"})
    assert get_origin(obj) is dict


def test_python_type_for_unknown_defaults_to_string():
    from restmcp.schema import python_type_for
    assert python_type_for({}) is str
    assert python_type_for({"type": "banana"}) is str


def test_reject_bool_guard():
    import pytest
    from restmcp.schema import _reject_bool
    assert _reject_bool(5) == 5
    assert _reject_bool("5") == "5"
    with pytest.raises(ValueError):
        _reject_bool(True)


def _sample_def():
    return {
        "name": "typed",
        "description": "x",
        "parameters": {"properties": {
            "n": {"type": "integer"},
            "flag": {"type": "boolean", "default": False},
            "ids": {"type": "array", "items": {"type": "integer"}, "default": None},
        }},
    }


def test_build_arg_model_required_and_defaults():
    from restmcp.schema import build_arg_model
    M = build_arg_model(_sample_def())
    m = M(n=5)
    assert m.model_dump() == {"n": 5, "flag": False, "ids": None}


def test_build_arg_model_coerces_and_guards():
    import pytest
    from pydantic import ValidationError
    from restmcp.schema import build_arg_model
    M = build_arg_model(_sample_def())

    assert M(n="5").n == 5          # numeric string coerced
    assert M(n=5.0).n == 5          # integral float coerced
    with pytest.raises(ValidationError):
        M(n=True)                   # anti-bool guard
    with pytest.raises(ValidationError):
        M(n="abc")                  # non-numeric string
    with pytest.raises(ValidationError):
        M()                         # missing required n


def test_build_arg_model_forbids_extra_keys():
    import pytest
    from pydantic import ValidationError
    from restmcp.schema import build_arg_model
    M = build_arg_model(_sample_def())
    with pytest.raises(ValidationError):
        M(n=5, bogus=1)


def test_build_arg_model_array_item_coercion_and_guard():
    import pytest
    from pydantic import ValidationError
    from restmcp.schema import build_arg_model
    M = build_arg_model(_sample_def())
    assert M(n=1, ids=[1, "2"]).ids == [1, 2]     # items coerced
    with pytest.raises(ValidationError):
        M(n=1, ids=[1, True])                     # anti-bool on items
    assert M(n=1, ids=None).ids is None           # explicit null ok (default None)


# --- field_spec_for / registration-time hardening ---

def test_field_spec_for_required_and_optional():
    from restmcp.schema import field_spec_for, python_type_for
    ann, default = field_spec_for("n", {"type": "integer"})
    assert default is ...
    ann_opt, default_opt = field_spec_for("ids", {"type": "array", "default": None})
    assert default_opt is None
    assert type(None) in ann_opt.__args__          # Optional-wrapped


def test_field_spec_for_coerces_default_at_registration():
    from restmcp.schema import field_spec_for
    _, default = field_spec_for("n", {"type": "integer", "default": "10"})
    assert default == 10 and isinstance(default, int)


def test_field_spec_for_rejects_bad_default():
    import pytest
    from restmcp.schema import field_spec_for
    with pytest.raises(TypeError, match="default"):
        field_spec_for("n", {"type": "integer", "default": "abc"})
    with pytest.raises(TypeError, match="default"):
        field_spec_for("n", {"type": "integer", "default": True})   # anti-bool


def test_check_property_name():
    import pytest
    from restmcp.schema import check_property_name
    check_property_name("t", "device_id")                # ok, no raise
    for bad in ("_id", "model_dump", "model_config", "not valid", "class-y"):
        with pytest.raises(TypeError, match="parameter name"):
            check_property_name("t", bad)


def test_build_arg_model_tolerates_none_parameters():
    from restmcp.schema import build_arg_model
    M = build_arg_model({"name": "t", "description": "x", "parameters": None})
    assert M.model_fields == {}
    M2 = build_arg_model(
        {"name": "t2", "description": "x", "parameters": {"properties": None}}
    )
    assert M2.model_fields == {}


def test_build_arg_model_rejects_underscore_and_reserved_names():
    import pytest
    from restmcp.schema import build_arg_model

    def _def(pname):
        return {"name": "t", "description": "x",
                "parameters": {"properties": {pname: {"type": "integer"}}}}

    with pytest.raises(TypeError, match="_id"):
        build_arg_model(_def("_id"))
    with pytest.raises(TypeError, match="model_dump"):
        build_arg_model(_def("model_dump"))
    with pytest.raises(TypeError, match="model_config"):
        build_arg_model(_def("model_config"))


def test_build_arg_model_default_coerced_matches_sent_value():
    # Same logical value must reach the callback with the same type whether
    # the client sent it or omitted it (review finding 5).
    from restmcp.schema import build_arg_model
    M = build_arg_model({"name": "t", "description": "x",
                         "parameters": {"properties":
                             {"n": {"type": "integer", "default": "10"}}}})
    assert M().n == 10
    assert M(n="10").n == 10
