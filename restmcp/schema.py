import inspect
import re
import types
import typing
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BeforeValidator, ConfigDict, create_model

_PRIMITIVES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _reject_bool(v):
    """Reject a bool where a number is expected.

    pydantic-lax would coerce True->1 / False->0; that is the one genuinely
    surprising coercion, so we forbid it. Applied to integer and number so REST
    and MCP agree and the behavior is predictable.
    """
    if isinstance(v, bool):
        raise ValueError("expected a number, got a boolean")
    return v


def python_type_for(prop: dict):
    """Map one mcp_definition property schema to a Python type annotation.

    integer -> Annotated[int,   BeforeValidator(_reject_bool)]
    number  -> Annotated[float, BeforeValidator(_reject_bool)]
    string  -> str
    boolean -> bool
    array   -> List[<item type via python_type_for>]   (default item: str)
    object  -> Dict[str, Any]
    unknown / missing type -> str

    Optionality is NOT applied here: the caller wraps Optional[...] when the
    property declares a default of None. This is the single source of truth for
    the JSON-schema-type -> Python-type mapping, shared by the REST model
    builder (build_arg_model) and the MCP signature builder (mcp.py).
    """
    t = prop.get("type")
    if t == "integer":
        return Annotated[int, BeforeValidator(_reject_bool)]
    if t == "number":
        return Annotated[float, BeforeValidator(_reject_bool)]
    if t == "boolean":
        return bool
    if t == "array":
        item = python_type_for(prop.get("items") or {"type": "string"})
        return List[item]
    if t == "object":
        return Dict[str, Any]
    return str


def build_arg_model(mcp_definition: dict):
    """Build a pydantic model for an endpoint's parameters from its mcp_definition.

    One field per property. A property without a "default" is required; one with
    a default uses it (wrapped Optional[...] when the default is None, so an
    explicit null is accepted). extra='forbid' makes an unknown key raise — the
    caller pre-filters the query string to known keys, so this enforces
    body-strict validation. This is the REST counterpart to the pydantic model
    fastmcp builds from the signature; both derive from python_type_for.
    """
    props = mcp_definition.get("parameters", {}).get("properties", {})
    fields = {}
    for name, prop in props.items():
        annotation = python_type_for(prop)
        if "default" in prop:
            default = prop["default"]
            if default is None:
                annotation = Optional[annotation]
            fields[name] = (annotation, default)
        else:
            fields[name] = (annotation, ...)
    return create_model(
        f"{mcp_definition['name']}_Args",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


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


def _unwrap_annotation(annotation) -> tuple:
    """Strip Annotated/Optional wrappers in any nesting order.

    ``Annotated[Optional[int], "d"]``, ``Optional[Annotated[int, "d"]]`` and
    deeper mixes all reduce to ``(int, "d")``. The first (outermost) string
    metadata found wins as the description.
    """
    description = None
    while True:
        base, desc = _unwrap_annotated(annotation)
        if description is None and desc is not None:
            description = desc
        base = _unwrap_optional(base)
        if base is annotation:
            return base, description
        annotation = base


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
        base, description = _unwrap_annotation(annotation)

        schema = schema_for_annotation(base)
        if description:
            schema["description"] = description
        if param.default is not inspect.Parameter.empty:
            schema["default"] = param.default

        properties[pname] = schema

    return {"properties": properties}


_RETURNS_RE = re.compile(r"^(returns?|retorn[oa])\s*:", re.IGNORECASE)


def _docstring(obj) -> str | None:
    """Full, dedented docstring of *obj* (or None if it has none)."""
    doc = inspect.getdoc(obj)
    if doc and doc.strip():
        return doc.strip()
    return None


def has_returns_doc(callback) -> bool:
    """True if *callback*'s docstring documents its return value.

    Looks for a ``Returns:`` section header (also accepts the Portuguese
    ``Retorna:``/``Retorno:``) on any line of the docstring. The MCP client only
    ever sees the tool description, so an inferred tool must spell out what it
    returns there — this is what enforces that.
    """
    doc = inspect.getdoc(callback)
    if not doc:
        return False
    return any(_RETURNS_RE.match(line.strip()) for line in doc.splitlines())


def build_mcp_definition(cls) -> dict:
    """Infer the full ``mcp_definition`` dict for an Endpoint subclass.

    name        -> tool_name_from_class(cls)
    description -> the full callback docstring (which must include a ``Returns:``
                   section), then the class docstring, then the tool name
    parameters  -> build_parameters(callback)
    """
    callback = getattr(cls, "callback", None)
    name = tool_name_from_class(cls)
    description = _docstring(callback) or _docstring(cls) or name
    return {
        "name": name,
        "description": description,
        "parameters": build_parameters(callback) if callback else {"properties": {}},
    }
