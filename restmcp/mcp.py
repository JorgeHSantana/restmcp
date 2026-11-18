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
        mcp.add_middleware(_argument_validation_middleware(
            {h.mcp_definition["name"]: h for h in url_handlers}))
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

        async def tool_wrapper(**kwargs):
            # The principal of THIS tools/call (see _call_principal), published
            # in current_auth for the duration of the call so callbacks reading
            # it see the calling key, then restored.
            token = None
            try:
                principal = _call_principal(current_auth)
                token = current_auth.set(principal)
                # Same authorization as REST: required_scope is checked before
                # the callback runs (no-op when auth is disabled).
                handler._enforce_scope(principal)
                # Same sync/async contract as REST: async callbacks are awaited,
                # sync callbacks run in a threadpool (see run_callback).
                return await run_callback(handler.callback, **kwargs)
            except RestMCPException as e:
                return _error_result(error_envelope(e, name))
            except passthrough:
                # fastmcp's / the MCP SDK's own exceptions (ToolError raised on
                # purpose, protocol errors) keep fastmcp's handling untouched.
                raise
            except Exception:
                # Same as REST: traceback to the log, generic text to the
                # client. fastmcp would otherwise echo str(e) (its
                # mask_error_details defaults to False).
                _logger.error("Unhandled error in tool %r", name, exc_info=True)
                return _error_result(internal_error_envelope(name))
            finally:
                if token is not None:
                    current_auth.reset(token)

        tool_wrapper.__name__ = name
        tool_wrapper.__doc__ = description
        tool_wrapper.__signature__ = inspect.Signature(parameters)
        # Errors leave as a ToolResult, which fastmcp passes through verbatim;
        # the annotation stays `dict` and __signature__ carries no return type,
        # so no outputSchema is derived and error envelopes cannot violate one.
        tool_wrapper.__annotations__ = {**annotations, "return": dict}
        return tool_wrapper


def _call_principal(current_auth: Any) -> dict | None:
    """Principal of the request making this tools/call.

    Over HTTP it is the one AuthMiddleware published in the scope of that HTTP
    request (``scope["state"]["auth"]``), read through fastmcp's per-request
    ``get_http_request()``. The ``current_auth`` contextvar is NOT trusted
    there: on fastmcp 3.x (mcp 1.x) the session's server loop runs in a task
    spawned by the request that OPENED the session, so the contextvar holds
    that request's principal — a key reusing another key's ``mcp-session-id``
    would borrow its scopes. An HTTP request without a principal yields
    ``None`` (fail closed: a scoped tool is refused), whatever the contextvar
    says.

    Without an HTTP request (in-memory transport) ``current_auth`` is the only
    source; unset means ``None``, which also fails closed.
    """
    try:
        from fastmcp.server.dependencies import get_http_request

        request = get_http_request()
    except RuntimeError:  # no active HTTP request
        return current_auth.get()
    state = request.scope.get("state") or {}
    return state.get("auth")


def _error_result(envelope: dict):
    """An MCP ``isError`` result carrying the shared error envelope as
    ``structuredContent`` (and its message as the text content)."""
    ToolResult, TextContent = _tool_result_types()
    return ToolResult(
        content=[TextContent(type="text", text=envelope["error"])],
        structured_content=envelope,
        is_error=True,
    )


def _argument_validation_middleware(handlers: dict):
    """fastmcp middleware that validates tools/call arguments the restmcp way.

    fastmcp validates arguments against the wrapper's signature BEFORE the
    wrapper runs, and on failure answers ``isError`` with pydantic's raw text:
    no envelope, no ``code``, and the rejected value echoed back
    (``input_value='...'``). This middleware runs first and validates with the
    endpoint's own argument model — the very model REST uses, built from the
    same field_spec_for as the signature — so an invalid call gets the shared
    envelope with ``code: "validation_error"`` and the same message as REST.
    Valid arguments go on unchanged (fastmcp then validates them again, with
    the same types, and calls the wrapper). Validation still precedes the
    scope check, which lives in the wrapper.
    """
    from fastmcp.server.middleware import Middleware
    from pydantic import ValidationError as PydanticValidationError

    from restmcp.endpoint import argument_validation_error, error_envelope

    class ArgumentValidation(Middleware):
        async def on_call_tool(self, context, call_next):
            name = context.message.name
            arg_model = getattr(handlers.get(name), "_arg_model", None)
            if arg_model is not None:
                try:
                    arg_model.model_validate(context.message.arguments or {})
                except PydanticValidationError as e:
                    return _error_result(
                        error_envelope(argument_validation_error(e), name))
            return await call_next(context)

    return ArgumentValidation()


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
