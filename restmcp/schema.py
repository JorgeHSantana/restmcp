import inspect
import re
import types
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


def _unwrap_annotated(annotation):
    """Return (base_type, description_or_None) for an annotation.

    ``Annotated[int, "Device id"]`` -> ``(int, "Device id")``. The first string
    metadata entry is used as the parameter description.
    """
    if hasattr(annotation, "__metadata__"):
        base = annotation.__origin__
        description = next(
            (m for m in annotation.__metadata__ if isinstance(m, str)), None
        )
        return base, description
    return annotation, None


def _unwrap_optional(annotation):
    """Reduce ``Optional[X]`` / ``X | None`` to ``X``; otherwise return as-is."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is getattr(types, "UnionType", ()):
        non_none = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def build_parameters(callback) -> dict:
    """Build the MCP ``parameters`` dict from a callback's signature.

    Each parameter (excluding ``self`` and ``*args``/``**kwargs``) becomes one
    property. A parameter with no default is required (no ``"default"`` key);
    one with a default carries it under ``"default"``. ``Annotated`` string
    metadata becomes the property ``"description"``.
    """
    sig = inspect.signature(callback)
    try:
        hints = typing.get_type_hints(callback, include_extras=True)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue

        annotation = hints.get(pname, param.annotation)
        base, description = _unwrap_annotated(annotation)
        base = _unwrap_optional(base)

        schema = schema_for_annotation(base)
        if description:
            schema["description"] = description
        if param.default is not inspect.Parameter.empty:
            schema["default"] = param.default

        properties[pname] = schema

    return {"properties": properties}


def _first_doc_line(obj) -> str | None:
    doc = inspect.getdoc(obj)
    if doc and doc.strip():
        return doc.strip().splitlines()[0].strip()
    return None


def build_mcp_definition(cls) -> dict:
    """Infer the full ``mcp_definition`` dict for an Endpoint subclass.

    name        -> tool_name_from_class(cls)
    description -> first line of the callback docstring, then the class
                   docstring, then the tool name
    parameters  -> build_parameters(callback)
    """
    callback = getattr(cls, "callback", None)
    name = tool_name_from_class(cls)
    description = _first_doc_line(callback) or _first_doc_line(cls) or name
    return {
        "name": name,
        "description": description,
        "parameters": build_parameters(callback) if callback else {"properties": {}},
    }
