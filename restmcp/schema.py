import inspect
import re
import typing
from typing import Any

_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean"}


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


def schema_for_annotation(annotation) -> dict:
    """JSON-Schema fragment for one Python annotation.

    Unknown / missing annotations fall back to ``{"type": "string"}`` — the same
    permissive default the hand-written definitions relied on.
    """
    if annotation is inspect.Parameter.empty or annotation is None:
        return {"type": "string"}

    origin = typing.get_origin(annotation)
    if origin in (list, typing.List) or annotation is list:
        args = typing.get_args(annotation)
        item = schema_for_annotation(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item}
    if origin in (dict, typing.Dict) or annotation is dict:
        return {"type": "object"}

    if annotation in _PRIMITIVES:
        return {"type": _PRIMITIVES[annotation]}
    return {"type": "string"}
