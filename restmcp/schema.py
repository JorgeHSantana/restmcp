import re


def tool_name_from_class(cls) -> str:
    """MCP tool name for an Endpoint subclass.

    Uses an explicit ``name`` class attribute when set; otherwise strips the
    ``Endpoint`` suffix from the class name and converts CamelCase to snake_case
    (``GetDeviceEndpoint`` -> ``get_device``).
    """
    explicit = vars(cls).get("name")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    base = cls.__name__
    if base.endswith("Endpoint"):
        base = base[: -len("Endpoint")]
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", base)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.lower()
