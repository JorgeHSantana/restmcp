from typing import Any, Dict, List, Optional


_JSON_TO_PYTHON = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
}


class McpApp:
    """Builds a FastMCP instance from registered url_handlers, mapping mcp_definition to typed pydantic tool wrappers."""

    # TODO(decouple-mcp): this class and Server.asgi_app() are the only points
    # touching fastmcp. To fully decouple, introduce a restmcp-owned protocol
    # (e.g. McpBackend with build()/http_app()/lifespan) and make FastMCP one
    # implementation, so a FastMCP major bump can't break callers. See the
    # tracking issue for the full plan and trade-offs.
    def build(self, url_handlers: List[Any]):
        from fastmcp import FastMCP

        mcp = FastMCP("pythia")
        for handler in url_handlers:
            self._register_tool(mcp, handler)
        return mcp

    def _register_tool(self, mcp: Any, handler: Any):
        from pydantic import Field, create_model
        import inspect

        def_dict = handler.mcp_definition
        name = def_dict["name"]
        description = def_dict["description"]
        properties = def_dict.get("parameters", {}).get("properties", {})

        pydantic_fields = {}
        for prop_name, prop_data in properties.items():
            ptype = prop_data.get("type")
            if ptype == "array":
                item_ptype = prop_data.get("items", {}).get("type", "string")
                item_type = _JSON_TO_PYTHON.get(item_ptype, str)
                py_type = List[item_type]
            elif ptype == "object":
                py_type = Dict[str, Any]
            else:
                py_type = _JSON_TO_PYTHON.get(ptype, str)

            default_val = prop_data.get("default", ...)
            if default_val is None:
                py_type = Optional[py_type]

            pydantic_fields[prop_name] = (
                py_type,
                Field(default=default_val, description=prop_data.get("description", "")),
            )

        ModelClass = create_model(f"{name}_args", **pydantic_fields)

        from restmcp.endpoint import run_callback

        async def tool_wrapper(args: ModelClass) -> dict:
            # Same sync/async contract as the REST path: async callbacks are
            # awaited, sync callbacks run in a threadpool. (A plain sync wrapper
            # would return an un-awaited coroutine for async callbacks.)
            return await run_callback(handler.callback, **args.model_dump())

        tool_wrapper.__name__ = name
        tool_wrapper.__doc__ = description
        sig = inspect.signature(tool_wrapper)
        new_param = inspect.Parameter(
            "args", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ModelClass
        )
        tool_wrapper.__signature__ = sig.replace(parameters=(new_param,))
        mcp.add_tool(tool_wrapper)
