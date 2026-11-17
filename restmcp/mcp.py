import inspect
from typing import Annotated, Any, List

from pydantic import Field

from restmcp.logging import Logger
from restmcp.schema import field_spec_for

_logger = Logger("restmcp.mcp")


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
        # endpoint imports stay local: endpoint -> server -> mcp is a real
        # cycle at module level.
        from restmcp.auth import current_auth
        from restmcp.endpoint import (
            error_envelope,
            internal_error_envelope,
            run_callback,
        )
        from restmcp.exceptions import RestMCPException

        ToolResult, TextContent = _tool_result_types()
        passthrough = _fastmcp_passthrough_errors()

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

        def error_result(envelope: dict):
            return ToolResult(
                content=[TextContent(type="text", text=envelope["error"])],
                structured_content=envelope,
                is_error=True,
            )

        async def tool_wrapper(**kwargs):
            try:
                # Same authorization as REST: AuthMiddleware set current_auth
                # in this request task; required_scope is checked before the
                # callback runs (no-op when auth is disabled).
                handler._enforce_scope(current_auth.get())
                # Same sync/async contract as REST: async callbacks are awaited,
                # sync callbacks run in a threadpool (see run_callback).
                return await run_callback(handler.callback, **kwargs)
            except RestMCPException as e:
                return error_result(error_envelope(e, name))
            except passthrough:
                # fastmcp's / the MCP SDK's own exceptions (ToolError raised on
                # purpose, protocol errors) keep fastmcp's handling untouched.
                raise
            except Exception:
                # Same as REST: traceback to the log, generic text to the
                # client. fastmcp would otherwise echo str(e) (its
                # mask_error_details defaults to False).
                _logger.error("Unhandled error in tool %r", name, exc_info=True)
                return error_result(internal_error_envelope(name))

        tool_wrapper.__name__ = name
        tool_wrapper.__doc__ = description
        tool_wrapper.__signature__ = inspect.Signature(parameters)
        # Errors leave as a ToolResult, which fastmcp passes through verbatim;
        # the annotation stays `dict` and __signature__ carries no return type,
        # so no outputSchema is derived and error envelopes cannot violate one.
        tool_wrapper.__annotations__ = {**annotations, "return": dict}
        return tool_wrapper


def _tool_result_types():
    """(ToolResult, TextContent) across fastmcp majors: 4.x exports ToolResult
    from fastmcp.tools; 2.x keeps it in fastmcp.tools.tool."""
    try:
        from fastmcp.tools import ToolResult
    except ImportError:
        from fastmcp.tools.tool import ToolResult
    from mcp.types import TextContent

    return ToolResult, TextContent


def _fastmcp_passthrough_errors() -> tuple:
    """Exception types the tool wrapper re-raises untouched: fastmcp's
    FastMCPError (covers ToolError) and the MCP SDK's MCPError. Imported
    defensively — the SDK named it McpError before, and a class missing from
    an older install must not break importing restmcp."""
    types = []
    try:
        from fastmcp.exceptions import FastMCPError

        types.append(FastMCPError)
    except ImportError:
        pass
    try:
        from mcp.shared import exceptions as _sdk
    except ImportError:
        _sdk = None
    for attr in ("MCPError", "McpError"):
        cls = getattr(_sdk, attr, None)
        if isinstance(cls, type) and issubclass(cls, BaseException) and cls not in types:
            types.append(cls)
    return tuple(types)
