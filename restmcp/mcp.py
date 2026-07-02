import inspect
from typing import Annotated, Any, List

from pydantic import Field

from restmcp.schema import field_spec_for


class McpApp:
    """Builds a FastMCP instance from registered url_handlers, mapping mcp_definition to typed pydantic tool wrappers."""

    # TODO(decouple-mcp): this class and Server.asgi_app() are the only points
    # touching fastmcp. To fully decouple, introduce a restmcp-owned protocol
    # (e.g. McpBackend with build()/http_app()/lifespan) and make FastMCP one
    # implementation, so a FastMCP major bump can't break callers. See the
    # tracking issue for the full plan and trade-offs.
    def build(self, url_handlers: List[Any]):
        from fastmcp import FastMCP

        mcp = FastMCP("restmcp")
        for handler in url_handlers:
            self._register_tool(mcp, handler)
        return mcp

    def _register_tool(self, mcp: Any, handler: Any):
        mcp.add_tool(self._build_tool_function(handler))

    def _build_tool_function(self, handler: Any):
        # run_callback stays a local import: endpoint -> server -> mcp is a
        # real cycle at module level.
        from restmcp.endpoint import run_callback

        def_dict = handler.mcp_definition
        name = def_dict["name"]
        description = def_dict["description"]
        properties = (def_dict.get("parameters") or {}).get("properties") or {}

        parameters = []
        annotations = {}
        for prop_name, prop_data in properties.items():
            py_type, default_val = field_spec_for(prop_name, prop_data)

            prop_desc = prop_data.get("description")
            annotation = (
                Annotated[py_type, Field(description=prop_desc)] if prop_desc else py_type
            )
            annotations[prop_name] = annotation

            if default_val is ...:
                parameters.append(
                    inspect.Parameter(
                        prop_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=annotation,
                    )
                )
            else:
                parameters.append(
                    inspect.Parameter(
                        prop_name,
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=annotation,
                        default=default_val,
                    )
                )

        async def tool_wrapper(**kwargs) -> dict:
            # Same sync/async contract as REST: async callbacks are awaited,
            # sync callbacks run in a threadpool (see run_callback).
            return await run_callback(handler.callback, **kwargs)

        tool_wrapper.__name__ = name
        tool_wrapper.__doc__ = description
        tool_wrapper.__signature__ = inspect.Signature(parameters)
        tool_wrapper.__annotations__ = {**annotations, "return": dict}
        return tool_wrapper
