from typing import Any, Dict, TypedDict


class McpProperty(TypedDict, total=False):
    type: str
    description: str
    default: Any
    items: Dict[str, Any]


class McpParameters(TypedDict, total=False):
    properties: Dict[str, McpProperty]


class _McpDefinitionBase(TypedDict):
    name: str
    description: str


class McpDefinition(_McpDefinitionBase, total=False):
    parameters: McpParameters
    returns: Dict[str, Any]
