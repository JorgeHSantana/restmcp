import asyncio
import inspect
from abc import ABC

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from pydantic import ValidationError as PydanticValidationError
from starlette.responses import Response as StarletteResponse

from restmcp.exceptions import (
    ForbiddenError,
    PayloadTooLargeError,
    RestMCPException,
    ValidationError,
)
from restmcp.logging import Logger
from restmcp.schema import build_arg_model, check_property_name

_logger = Logger("restmcp.endpoint")


async def run_callback(callback: object, /, **kwargs):
    """Invoke an Endpoint callback under restmcp's sync/async contract.

    The contract (identical for REST and MCP):
    - **async callback** -> awaited directly. Keep its I/O async; do not call
      blocking code inside it, or you will stall the event loop.
    - **sync callback** -> run in the default threadpool, so a blocking
      Repository/DataSource call (e.g. a synchronous DB driver) never blocks the
      loop. A plain `def callback` doing blocking I/O is therefore correct.
    """
    if inspect.iscoroutinefunction(callback):
        return await callback(**kwargs)
    # to_thread copies the caller's contextvars into the worker thread
    # (run_in_executor does not), so identity/correlation vars set by
    # middleware survive the hop (issue #16).
    return await asyncio.to_thread(callback, **kwargs)


def _validate_mcp_definition(cls_name: str, mcp_def: object) -> None:
    if not isinstance(mcp_def, dict):
        raise TypeError(
            f"{cls_name}: mcp_definition must be a dict, got {type(mcp_def).__name__}"
        )
    for key in ("name", "description"):
        val = mcp_def.get(key)
        if not isinstance(val, str) or not val.strip():
            raise TypeError(
                f"{cls_name}: mcp_definition['{key}'] must be a non-empty string"
            )
    params = mcp_def.get("parameters")
    if params is not None:
        if not isinstance(params, dict):
            raise TypeError(
                f"{cls_name}: mcp_definition['parameters'] must be a dict"
            )
        props = params.get("properties")
        if props is not None and not isinstance(props, dict):
            raise TypeError(
                f"{cls_name}: mcp_definition['parameters']['properties'] must be a dict"
            )
        if isinstance(props, dict):
            for prop_name in props:
                check_property_name(cls_name, prop_name)
    returns = mcp_def.get("returns")
    if returns is not None and not isinstance(returns, dict):
        raise TypeError(
            f"{cls_name}: mcp_definition['returns'] must be a dict (the JSON "
            f"Schema of the callback's return value), got {type(returns).__name__}"
        )


class Endpoint(ABC):
    """HTTP + MCP endpoint. Subclasses auto-register on class definition when url,
    method, and callback are set; mcp_definition is inferred from the callback
    signature when not provided explicitly. REST parameters are accepted from
    the query string and/or the JSON body (body wins on conflicts) and are
    validated against mcp_definition before reaching the callback."""

    disabled: bool = False
    # Which transports serve this endpoint. "rest" keeps the tool out of the MCP
    # server AND the /mcp/tools catalog (e.g. write endpoints an agent must not
    # even see); "mcp" registers no HTTP route (agent-only tools). Default
    # "both" — existing endpoints are untouched.
    expose: str = "both"
    _EXPOSE_VALUES = ("rest", "mcp", "both")
    # Ceiling for the request body, in bytes. None = the global default
    # (env MAX_BODY_BYTES, 1 MiB). Bodies over the ceiling get 413 before
    # buffering (issue #12) — raise it per endpoint for known-large payloads
    # (e.g. base64 uploads).
    max_body_bytes: int | None = None
    # Scope this endpoint demands from the authenticated key (issue #15,
    # step 2): e.g. "write". None = any authenticated key. Enforced on the
    # REST path before the callback; no-op when auth is disabled. On the MCP
    # side, hide sensitive tools structurally with expose = "rest".
    required_scope: str | None = None
    # HTTP status of the SUCCESS envelope (issue #18). Declarative on purpose:
    # the same value feeds the JSONResponse and the OpenAPI document, so the
    # frozen contract cannot disagree with the server. 2xx only; 204 is
    # rejected (No Content forbids a body, the envelope always has one).
    # Errors ignore this — their code comes from the exception class.
    success_code: int = 200
    # FastAPI escape hatch (issue #18): the callback returns a Starlette
    # Response and it passes through VERBATIM — no envelope, any status,
    # headers, files, redirects. Three locks: requires expose="rest" (a raw
    # response has no MCP representation), is opt-in (a Response returned
    # without this flag is a programming error, never a silent passthrough),
    # and covers success only — raised exceptions still use the error envelope.
    raw_response: bool = False
    _registered: bool = False  # per-subclass; set after successful registration

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Endpoint"):
            raise TypeError(
                f"Endpoint subclasses must end with 'Endpoint' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Endpoint'."
            )
        expose = vars(cls).get("expose", cls.expose)
        if expose not in cls._EXPOSE_VALUES:
            raise TypeError(
                f"{cls.__name__}: expose must be one of {list(cls._EXPOSE_VALUES)} "
                f"(got: {expose!r})."
            )

        raw = vars(cls).get("raw_response", cls.raw_response)
        if raw:
            if expose != "rest":
                raise TypeError(
                    f"{cls.__name__}: raw_response=True requires expose='rest' "
                    f"(got expose={expose!r}). A raw HTTP response has no MCP "
                    f"representation — hide the endpoint from MCP first."
                )
            if "success_code" in vars(cls):
                raise TypeError(
                    f"{cls.__name__}: success_code conflicts with raw_response=True "
                    f"— in raw mode the Response object owns the status code."
                )
        else:
            code = vars(cls).get("success_code", cls.success_code)
            if not isinstance(code, int) or isinstance(code, bool) \
                    or not 200 <= code <= 299:
                raise TypeError(
                    f"{cls.__name__}: success_code must be an int in 200..299 "
                    f"(got: {code!r}). Error codes come from exception classes "
                    f"(RestMCPException.status_code), not from here."
                )
            if code == 204:
                raise TypeError(
                    f"{cls.__name__}: success_code=204 is illegal — 204 No Content "
                    f"forbids a body and the {{tool, result, success}} envelope "
                    f"always has one."
                )

        if getattr(cls, "disabled", False):
            return

        _required = ("url", "method", "callback")
        present = [attr for attr in _required if vars(cls).get(attr)]
        if present and len(present) < len(_required):
            missing = ", ".join(a for a in _required if a not in present)
            raise TypeError(
                f"{cls.__name__}: incomplete endpoint definition — missing: {missing}. "
                f"Define url, method and callback together, or set disabled = True "
                f"on an intermediate base class."
            )
        if len(present) == len(_required):
            if "mcp_definition" not in vars(cls):
                from restmcp.schema import build_mcp_definition, has_returns_doc

                if not has_returns_doc(cls.callback):
                    raise TypeError(
                        f"{cls.__name__}: the callback docstring must document its "
                        f"return value in a 'Returns:' section when mcp_definition "
                        f"is inferred — that text is the only thing the MCP client "
                        f"sees about the output. Example:\n"
                        f'    """One-line summary.\n\n'
                        f"    Returns: what the tool returns.\n"
                        f'    """\n'
                        f"(or set mcp_definition explicitly to override inference)."
                    )
                cls.mcp_definition = build_mcp_definition(cls)
            _validate_mcp_definition(cls.__name__, vars(cls)["mcp_definition"])
            try:
                cls()
            except TypeError as e:
                raise TypeError(
                    f"{cls.__name__}: auto-registration failed. "
                    f"Endpoint subclasses must not define __init__ with parameters — "
                    f"use Service/Repository for dependencies. Original error: {e}"
                ) from e

    async def _callback(self, request: Request):
        try:
            # The auth dependency runs in a threadpool (it is sync), so a
            # contextvar set there dies with the thread; the principal survives
            # in scope["state"]. Promote it here, in the request task, so
            # callbacks (sync included, via to_thread) can read current_auth.
            principal = request.scope.get("state", {}).get("auth")
            if principal is not None:
                from restmcp.auth import current_auth

                current_auth.set(principal)
            self._enforce_scope(principal)
            raw = await self._read_body_capped(request)
            if not raw or not raw.strip():
                body = {}          # absent body: query-string-only calls are fine
            else:
                import json as _json
                try:
                    body = _json.loads(raw)
                except ValueError:
                    # A body was sent but is not JSON — that is a client error,
                    # not an empty body: swallowing it let defaults turn a
                    # truncated payload into a different, "successful" call
                    # (issue #13).
                    raise ValidationError("Request body is not valid JSON")
            if body is None:
                body = {}
            if not isinstance(body, dict):
                raise ValidationError("Request body must be a JSON object")

            # Query filtered to known keys (body-strict, query-tolerant): unknown
            # query keys (tracking params etc.) are ignored, unknown body keys are
            # rejected by the model's extra='forbid'. Body wins on conflicts.
            known = self._arg_model.model_fields
            data = {k: v for k, v in request.query_params.items() if k in known}
            data.update(body)

            try:
                model = self._arg_model(**data)
            except PydanticValidationError as e:
                parts = []
                for err in e.errors():
                    loc = ".".join(str(p) for p in err["loc"]) or "body"
                    parts.append(f"{loc}: {err['msg']}")
                raise ValidationError("; ".join(parts))

            # dict(model): the already-validated values, without model_dump()'s
            # per-request recursive copy of every container.
            result = await run_callback(self.callback, **dict(model))

            if isinstance(result, StarletteResponse):
                if not self.raw_response:
                    raise TypeError(
                        f"{type(self).__name__}: callback returned a Response "
                        f"but the endpoint does not declare raw_response=True. "
                        f"Declare it (requires expose='rest') or return plain data."
                    )
                return result
            if self.raw_response:
                raise TypeError(
                    f"{type(self).__name__}: raw_response=True requires the "
                    f"callback to return a starlette Response "
                    f"(got: {type(result).__name__})."
                )

            return JSONResponse(jsonable_encoder({
                "tool": self.mcp_definition["name"],
                "result": result,
                "success": True,
            }), status_code=self.success_code)

        except RestMCPException as e:
            return JSONResponse(jsonable_encoder({
                "error": e.message,
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": e.__class__.__name__,
            }), status_code=e.status_code)

        except Exception:
            # Full traceback goes to the server log; the client gets a
            # generic message so internals never leak into responses.
            _logger.error(
                "Unhandled error in tool %r", self.mcp_definition["name"], exc_info=True
            )
            return JSONResponse(jsonable_encoder({
                "error": "Internal server error",
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": "InternalServerError",
            }), status_code=500)

    def _enforce_scope(self, principal: dict | None) -> None:
        """403 when the authenticated key lacks this endpoint's required_scope.

        Authorization only — authentication already happened (middleware or
        dependency). With auth disabled there is no principal and no check."""
        import os as _os

        if not self.required_scope or not _os.getenv("AUTH_API_KEY"):
            return
        if principal is None or self.required_scope not in principal["scopes"]:
            who = (principal or {}).get("name") or "key"
            raise ForbiddenError(
                f"{who} lacks the {self.required_scope!r} scope required by "
                f"{self.mcp_definition['name']!r}"
            )

    async def _read_body_capped(self, request: Request) -> bytes:
        """Read the body enforcing the ceiling BEFORE buffering it whole.

        Declared Content-Length over the limit is refused without reading;
        without (or lying) Content-Length, the stream is read in chunks and
        aborted the moment the accumulated size crosses the ceiling — the
        process never allocates more than limit + one chunk (issue #12)."""
        import os as _os

        limit = self.max_body_bytes or int(_os.getenv("MAX_BODY_BYTES", 1_048_576))
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise PayloadTooLargeError(
                f"Request body of {declared} bytes exceeds the limit of {limit} bytes"
            )
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise PayloadTooLargeError(
                    f"Request body exceeds the limit of {limit} bytes"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def __init__(self):
        from restmcp.server import Server
        from restmcp.rest import _auth_dependency

        cls = type(self)
        # Idempotency guard (issue #10): a second instantiation (manual call,
        # module reload) must not re-register the route. Checked via vars() so
        # a subclass never inherits its parent's "already registered" state.
        if vars(cls).get("_registered", False):
            return

        self.mcp_definition = getattr(self, "mcp_definition", None)
        if not self.mcp_definition:
            raise ValueError(f"{self.__class__.__name__}: mcp_definition is required")

        self.method = getattr(self, "method", None)
        if not self.method:
            raise ValueError(f"{self.__class__.__name__}: method is required")

        self.url = getattr(self, "url", None)
        if not self.url:
            raise ValueError(f"{self.__class__.__name__}: url is required")

        if not getattr(self, "callback", None):
            raise ValueError(f"{self.__class__.__name__}: callback is required")

        # Definition errors must surface with the endpoint's name, and as
        # ValueError so __init_subclass__'s TypeError wrapper (which blames
        # __init__ parameters) never swallows them (review findings 3, 4).
        try:
            self._arg_model = build_arg_model(self.mcp_definition)
        except Exception as e:
            raise ValueError(f"{cls.__name__}: invalid mcp_definition — {e}") from e

        # Every declared property reaches the callback (defaults included,
        # matching the MCP transport), so the signature must accept them all —
        # checked here so the mismatch is a registration error, not a
        # per-request 500 (review finding 2).
        sig = inspect.signature(self.callback)
        if not any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        ):
            accepted = {
                p.name
                for p in sig.parameters.values()
                if p.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                )
            }
            rejected = sorted(set(self._arg_model.model_fields) - accepted)
            if rejected:
                raise ValueError(
                    f"{cls.__name__}: callback does not accept declared "
                    f"parameter(s) {', '.join(rejected)} — every mcp_definition "
                    f"property is passed to the callback (defaults included); "
                    f"add the parameter(s) or **kwargs."
                )

        endpoint_self = self

        async def route_handler(request: Request):
            return await endpoint_self._callback(request)

        server = Server.get_instance()
        # Atomic registration (issue #10): in-memory append first (cheap,
        # can't half-fail), ASGI route last, rollback on failure — never a
        # route without a handler or a handler without a route. An "mcp"-only
        # endpoint registers the handler and skips the HTTP route entirely.
        server.register_url_handler(self)
        if self.expose != "mcp":
            try:
                server.app.add_api_route(
                    self.url,
                    route_handler,
                    methods=[self.method],
                    dependencies=[Depends(_auth_dependency)],
                    operation_id=self.mcp_definition["name"],
                    description=self.mcp_definition.get("description"),
                    # status_code: FastAPI SEMPRE injeta um bloco de sucesso
                    # próprio no OpenAPI; declarar o código faz esse bloco cair
                    # na MESMA chave que o nosso openapi_extra sobrescreve —
                    # sem isto, um success_code=202 sairia com um "200:
                    # Successful Response" fantasma ao lado.
                    status_code=self.success_code,
                    openapi_extra=_openapi_extra(
                        self.mcp_definition, self.method,
                        success_code=self.success_code, raw=self.raw_response),
                )
                if self.raw_response:
                    # O bloco automático do FastAPI não tem como ser suprimido
                    # por rota; a poda acontece no openapi() (rest.py), que lê
                    # esta lista. Registrada DEPOIS do add_api_route: rota que
                    # falhou não entra.
                    server.app.state.raw_routes = getattr(
                        server.app.state, "raw_routes", set())
                    server.app.state.raw_routes.add((self.url, self.method.lower()))
            except Exception:
                server.unregister_url_handler(self)
                raise
        cls._registered = True


_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


_ERROR_ENVELOPE = {
    "type": "object",
    "properties": {
        "tool": {"type": "string"},
        "error": {"type": "string"},
        "success": {"type": "boolean"},
        "error_type": {"type": "string"},
    },
    "required": ["tool", "error", "success", "error_type"],
}


def _openapi_extra(mcp_definition: dict, method: str, *,
                   success_code: int = 200, raw: bool = False) -> dict:
    """Request AND response metadata for a route (issue #52 parts A and B)."""
    extra = _openapi_params(mcp_definition, method) or {}
    extra["responses"] = _openapi_responses(
        mcp_definition, success_code=success_code, raw=raw)
    return extra


def _openapi_responses(mcp_definition: dict, *,
                       success_code: int = 200, raw: bool = False) -> dict:
    """Document what a route actually sends back.

    Every success travels in the ``{tool, result, success}`` envelope, so the
    envelope is what OpenAPI describes — with ``result`` typed by the
    ``returns`` JSON Schema when the endpoint declares one (the same slot the
    /mcp/tools catalog publishes) and left open otherwise: the envelope alone
    already gives generated clients a typed skeleton instead of nothing. Errors
    always use the error envelope (see ``_callback``), documented once under
    ``default``. This is part B of ReconcilIA issue #52 — before it, a renamed
    response field compiled fine on the client and simply showed empty data.
    """
    if raw:
        # Raw endpoint (issue #18): no envelope to promise — the endpoint owns
        # code, headers and body. One honest "default" instead of a "200" that
        # would lie about both the code and the shape. Errors raised as
        # exceptions still use the error envelope, and the description says so.
        return {
            "default": {
                "description": (
                    "Resposta crua (raw_response=True): código, headers e corpo "
                    "definidos pelo endpoint. Erros levantados por exceção usam "
                    "o envelope de erro padrão {tool, error, success, error_type}."
                ),
            },
        }

    result_schema = mcp_definition.get("returns") or {}
    success_envelope = {
        "type": "object",
        "properties": {
            "tool": {"type": "string"},
            "result": result_schema,
            "success": {"type": "boolean"},
        },
        "required": ["tool", "result", "success"],
    }
    return {
        str(success_code): {
            "description": "Envelope de sucesso",
            "content": {"application/json": {"schema": success_envelope}},
        },
        "default": {
            "description": "Envelope de erro (validação, conflito ou falha interna)",
            "content": {"application/json": {"schema": _ERROR_ENVELOPE}},
        },
    }


def _openapi_params(mcp_definition: dict, method: str) -> dict | None:
    """OpenAPI request metadata for a route, from the SAME source MCP publishes.

    The generic ``route_handler(request)`` gives FastAPI nothing to describe, so
    every operation used to come out empty and generated clients (e.g.
    openapi-typescript) had no request types at all. This derives
    ``requestBody``/``parameters`` straight from ``mcp_definition`` — not from
    the pydantic arg model — so the published schema is byte-for-byte the JSON
    Schema the author declared (or inference built), with no pydantic dialect
    quirks, and REST/MCP cannot drift.

    Conventions mirrored from validation: a property without a ``default`` key
    is required (`schema.field_spec_for`); unknown keys are rejected
    (extra='forbid'), hence ``additionalProperties: false``. Response schemas
    are part B of the issue (design pending) and stay out on purpose.
    """
    props = (mcp_definition.get("parameters") or {}).get("properties") or {}
    if not props:
        return None
    required = [n for n, p in props.items() if not (isinstance(p, dict) and "default" in p)]
    if method.upper() in _BODY_METHODS:
        schema: dict = {
            "type": "object",
            "properties": props,
            "additionalProperties": False,
        }
        if required:
            schema["required"] = required
        return {"requestBody": {
            "required": bool(required),
            "content": {"application/json": {"schema": schema}},
        }}
    return {"parameters": [
        {"name": name, "in": "query", "required": name in required, "schema": prop}
        for name, prop in props.items()
    ]}
