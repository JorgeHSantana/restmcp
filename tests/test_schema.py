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
