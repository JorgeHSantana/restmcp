# Changelog

All notable changes to **restmcp** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning:
[SemVer](https://semver.org/). Every PR/commit that changes behavior, API or
docs-that-ship must add an entry under **Unreleased**; the release flow moves
that block under the new version heading (the version in `pyproject.toml` and
this file move together — the publish workflow releases whatever version is in
`pyproject.toml`).

## [Unreleased]

## [0.8.0] - 2026-11-18

Stricter input handling on both transports: strict booleans, `Literal` as
`enum`, and a machine-readable `code` on every argument the framework rejects.

### Changed (breaking/behaviour changes)
- **Booleans are strict**: a parameter annotated `bool` (or declared
  `{"type": "boolean"}`) accepts only JSON `true`/`false`, on REST and on MCP
  `tools/call`. `"true"`, `"yes"`, `"on"`, `1`, `0` — coerced by pydantic-lax
  until 0.7.x — are now a validation error (HTTP 400 / `isError`). Optional
  booleans still accept `null` and integers/numbers still reject booleans.
  Strictness is for what the client sends: declared defaults keep 0.7's lax
  coercion, so `flag: bool = 0` or a hand-written
  `{"type": "boolean", "default": "false"}` still register (as `False`); a
  default 0.7 rejected (`"banana"`) still raises. In a REST query string, which
  carries no types, `true`/`false` in any case (`true`, `True`, `FALSE`) are
  the only accepted spellings; `?flag=1`, `?flag=yes`, `?flag=on` are rejected.
  Clients that send `"true"`/`1` in a JSON body or MCP arguments must send
  JSON booleans.
- **`Literal[...]` is published as `enum` and enforced**: `Literal["a", "b"]`
  (also `Optional[...]`, with a default, and `list[Literal[...]]`) was reduced
  to `{"type": "string"}` and accepted any string; it now appears as
  `{"type": "string", "enum": ["a", "b"]}` in MCP `tools/list`, `/mcp/tools`
  and OpenAPI, and a value outside the set is a validation error. Integer
  literals (`Literal[1, 2]` → `{"type": "integer", "enum": [1, 2]}`) take what
  `int` takes (`2`, `"2"`, `2.0`), never `true`; float literals
  (`Literal[1.5, 2.5]`) publish `type: number`; `Union[Literal["a"],
  Literal["b"]]` is treated as `Literal["a", "b"]`; a mixed
  `Literal[True, "auto"]` publishes a bare `enum`, and its query-string
  `true`/`false` become booleans. An `enum` in a hand-written `mcp_definition`
  (str/int/float/bool/null members) is now enforced as well — it used to be
  published only. With a declared `type` the value is validated by that type
  first, so the callback receives the same Python type as in 0.7 (a
  `{"type": "number", "enum": [1, 2]}` still hands over floats).
  Defaults outside the set: a hand-written enum whose `default` is not a
  member **does not raise** — registration emits a `UserWarning` naming the
  tool and parameter, the default is still used when the client omits the
  parameter, and a client cannot send it; a `Literal` annotation whose default
  is not a member (`mode: Literal["a", "b"] = "c"`) raises `TypeError` at class
  definition (an author type error).
- **`code: "validation_error"` on rejected arguments**: wrong type, missing
  required, unknown parameter, value outside an `enum`, non-boolean for a
  boolean, and a body that is not a JSON object still answer HTTP 400 with
  `error_type: "ValidationError"`, but `code` is `"validation_error"` instead
  of `null`. Over MCP the same failures now return `isError: true` with the
  shared envelope (same message as REST, `code: "validation_error"`) as
  `structuredContent`; until 0.7.x they returned fastmcp's raw pydantic text,
  without envelope or `code`, and echoed the rejected value
  (`input_value='...'`). The message names each parameter and what it expects
  (`"confirm: Input should be a valid boolean"`), never the rejected value. A
  `ValidationError` raised by a callback keeps its own `code`. The MCP text for
  a missing argument changed accordingly (`"n: Field required"`, was fastmcp's
  `"Missing required keyword only argument"`). An unknown parameter's name is
  cut to 64 characters in the message.
- **MCP checks `required_scope` before the arguments**, as REST does: a key
  without the scope now gets `forbidden_scope` whatever it sends (0.7.x
  validated the arguments first and answered a validation error). With auth
  disabled nothing changes.
- **`McpApp.build()` fails closed**: a handler without `_arg_model` raises
  `TypeError` (only reachable when building MCP from objects that are not
  registered `Endpoint`s).

### Notes
- Over MCP, valid arguments are validated twice (restmcp's middleware, then
  fastmcp, same types) — negligible cost, kept so fastmcp's own path is
  untouched.
- Protocol-level errors the MCP SDK raises before a tool is resolved (e.g. a
  malformed JSON-RPC batch) are outside restmcp and may quote the request.

### Docs
- README and RAG knowledge base: parameter types and what each accepts, strict
  booleans, `Literal`/`enum`, the `validation_error` code; the stale
  "fastmcp 2.x alias" text for `transport="streamable-http"` now says it is an
  alias of `http`.

## [0.7.0] - 2026-11-17

One error envelope for every transport, `required_scope` enforced on MCP, and
an application lifespan hook for `asgi_app()`.

### Changed (breaking)
- **`required_scope` now holds on MCP `tools/call`**: a key without the scope
  (e.g. a `read` key calling a `write` tool) used to reach the callback through
  MCP; it now gets `isError: true` with `code: "forbidden_scope"` and the
  callback does not run (see Fixed). Clients that relied on the gap must use a
  key that carries the scope.
- **The framework's 401 body changed shape**: `AuthMiddleware` (which also
  guards the mounted MCP) answered `{"error": "Unauthorized"}` and the REST
  auth dependency FastAPI's `{"detail": "Unauthorized"}`; both now answer the
  standard error envelope
  `{"tool": null, "error": "Unauthorized", "success": false, "error_type": "UnauthorizedError", "code": "invalid_api_key"}`.
  Clients that read `detail` or a bare `error` key must read the envelope.
- **Unexpected MCP errors no longer carry the exception text**: an exception
  that is neither a `RestMCPException` nor one of fastmcp's own is logged with
  its traceback and returned as the generic `InternalServerError` envelope
  (`"error": "Internal server error"`), as REST already did. fastmcp echoed
  `str(e)` before (its `mask_error_details` defaults to `False`).
- **MCP error text for a `RestMCPException` lost fastmcp's prefix**: the text
  content is now the exception message alone (`"no such thing"`), where
  fastmcp rendered `"Error calling tool 'gone': no such thing"`; the same
  applies to the `ToolError` message raised by `fastmcp.Client.call_tool`.
  Clients matching on the prefix must match the message or, better, read
  `structuredContent.code`.
- **Over MCP HTTP the principal comes from the request, not from
  `current_auth`**: the scope check (and `current_auth` inside the callback)
  uses the principal the framework's `AuthMiddleware` stored on the request
  making the `tools/call`. A custom auth middleware that only sets the
  `current_auth` contextvar is no longer seen over MCP HTTP: tools with
  `required_scope` answer `forbidden_scope` and `current_auth.get()` is `None`
  in the callback. REST and the in-memory transport are unaffected.
- **Dependency floor raised to `fastmcp>=3.4`** (was `fastmcp>=2.0`): fastmcp
  2.x already failed the test suite before this release, and 3.0–3.3 lack the
  `ToolResult(is_error=...)` the structured MCP errors need.

### Added
- `asgi_app(lifespan=...)`: the application's startup/shutdown hook (open and
  close HTTP clients, pools). A callable taking the parent Starlette app and
  returning an async context manager; it is chained to the FastMCP lifespan —
  FastMCP enters first and exits last — so MCP keeps working. An exception in
  the app's startup propagates as itself (not wrapped in an `ExceptionGroup`)
  and the server does not come up; if FastMCP's shutdown then fails too, its
  exception propagates with the app's attached as a note. Default `None`:
  unchanged behavior.
- `code` in `RestMCPException` (`RestMCPException(message, status_code, code=None)`;
  the built-in subclasses accept it too, without changing their status): a
  machine-readable identifier (e.g. `"session_expired"`) clients can branch on
  without parsing the message. Subclasses written for 0.6.x that do not call
  `RestMCPException.__init__` keep their status and envelope: `message`,
  `status_code` and `code` have class-level defaults (`None` → `str(exc)`,
  `500`, `None`).
- One error envelope, `{tool, error, success, error_type, code}`, shared by the
  REST callback, the auth middleware, the REST auth dependency and MCP. `code`
  is **always present**, `null` when the exception defines none; `tool` is
  `null` when the error happens before an endpoint is resolved (the 401). The
  OpenAPI error schema (`default`) declares `code` (`["string", "null"]`,
  required) and now types `tool` as `["string", "null"]`. `RestApp` registers
  a `RestMCPException` handler so exceptions raised outside the callback
  (route dependencies) get the same envelope.
- `UnauthorizedError` (401, `code="invalid_api_key"`, message `"Unauthorized"`).
- The `required_scope` 403 carries `code: "forbidden_scope"`, on REST and MCP.
- Structured MCP errors: a `RestMCPException` raised in a tool (or by the
  scope check) becomes `isError: true` with the shared error envelope as
  `structuredContent` and the message as text content. fastmcp's own
  exceptions (`FastMCPError`, which covers `ToolError`, and the MCP SDK's
  `MCPError`) pass through to fastmcp's handling untouched.

### Fixed
- `required_scope` was not enforced on MCP `tools/call`: a `read` key could
  run a `write` tool through MCP. The scope is now checked before the callback
  on both transports, against the principal of the HTTP request making the
  `tools/call` (`scope["state"]["auth"]`, read through fastmcp's per-request
  `get_http_request()`), so a session opened by one key does not lend its
  scopes to calls made with another — verified on fastmcp 3.4.11 (where the
  session task otherwise carries the opener's `current_auth`) and 4.2.1,
  Streamable HTTP and SSE. During the call `current_auth` is set to that same
  principal, so callbacks reading it see the calling key. It fails closed:
  an HTTP request without a principal is refused whatever `current_auth`
  says, and without an HTTP request (fastmcp's in-memory transport)
  `current_auth` is the source and unset means refused. `expose = "rest"` is
  no longer needed as a workaround. Over MCP, fastmcp validates the arguments before the tool runs,
  so invalid arguments from a key without the scope get a validation error
  rather than `forbidden_scope`; REST checks the scope first. The callback
  runs in neither case.

### Verified
- Long calls: a 300 s callback (and a 330 s one) completes through REST and
  through MCP (Streamable HTTP, `fastmcp.Client` and a raw JSON-RPC client)
  served by `asgi_app()` under uvicorn — restmcp imposes no per-call deadline.
  Measured with fastmcp 4.2.1, mcp 2.3.0, uvicorn 0.54.0, starlette 1.10.0.
  The deadline is the ASGI server's / proxy's (e.g. Cloud Run
  `timeoutSeconds`); clients must raise their own timeouts (README →
  Production checklist).
- The test suite for this release passes on fastmcp 4.2.1 (mcp 2.3.0),
  3.4.11 and 3.4.0 (mcp 1.30.0), Python 3.14; it fails on fastmcp 3.0–3.3,
  hence the `fastmcp>=3.4` floor.

## [0.6.1] - 2026-09-08

### Fixed
- `/mcp/tools` returned **500** when any registered endpoint carried a
  hand-written `mcp_definition` without a `parameters` key — a shape
  `_validate_mcp_definition` accepts (the OpenAPI and MCP builders already
  tolerated it). The catalog now publishes `{"properties": {}}` for it.

### Added
- Tests pin that the key identity (#15) reaches the callback over a real MCP
  `tools/call` through `asgi_app()`, sync and async — the contextvar hop fix
  (#16) was only covered on REST and in isolation; the MCP path depends on
  FastMCP executing the tool inside the request task.
- `examples/telemetry`: `whoami` endpoint + `IdentityService` reading
  `restmcp.auth.current_auth` (with `required_scope = "read"`), README rows,
  curl walkthrough, named-keys sample in `.env.example`, and an end-to-end
  test over REST and MCP.

## [0.6.0] - 2026-08-13

Issue #18, both halves — the status code stops being hardwired.

### Added
- **`success_code`** (#18): class-level declaration of the success envelope's
  HTTP status (default 200 — no existing endpoint changes). One declaration
  feeds the `JSONResponse` AND the OpenAPI document, so a frozen contract
  cannot disagree with the server. 2xx only, validated at class definition;
  204 rejected (No Content forbids a body, the envelope always has one).
  Errors keep coming from exception classes. Born for ReconcilIA's
  `POST /runs` → 202 Accepted.
- **`raw_response`** (#18): the FastAPI escape hatch — the callback returns a
  Starlette `Response` and it passes through verbatim (files, redirects,
  conditional codes, custom headers). Three locks: requires `expose="rest"`
  (raw has no MCP representation — import-time error otherwise, and
  `success_code` alongside it is rejected as conflicting); opt-in declared
  (a `Response` returned without the flag is a 500 with a pointed log message,
  never a silent passthrough — and raw returning plain data errors
  symmetrically); success only (exceptions still produce the standard error
  envelope, and the request pipeline — auth, scopes, body cap, validation —
  applies unchanged). In OpenAPI a raw operation documents one honest
  `default`; FastAPI's automatic success block is pruned via the `openapi()`
  override in `RestApp`.
- `examples/telemetry`: two new endpoints exercising both features through all
  layers — `recalibrate_fleet` (202 ticket) and `export_readings` (raw CSV
  download with the 404 path proving errors stay enveloped) — plus README
  rows, curl walkthrough and service-level tests.

### Changed
- Routes are now registered with FastAPI's `status_code` parameter derived
  from `success_code`, so FastAPI's automatic OpenAPI success block lands on
  the declared code instead of leaving a phantom `"200"` beside a custom one.

## [0.5.1] - 2026-08-11

### Fixed
- **CORS preflight passes through auth** (#17): with `AUTH_API_KEY` set,
  `AuthMiddleware` wraps the whole app — including `CORSMiddleware` — so the
  browser's `OPTIONS` preflight (which never carries `Authorization`, per the
  CORS spec) got 401 before CORS could answer, blocking every cross-origin
  call even with a valid token. A request is only exempt when it is strictly
  a preflight (`OPTIONS` + `Access-Control-Request-Method`); a bare `OPTIONS`
  still authenticates, and so does the actual request. Found on ReconcilIA's
  first real browser-to-authenticated-backend session.
- `examples/telemetry/README.md`: feature table now lists the
  `purge_readings` endpoint (expose + returns) added in 0.4.1.

## [0.5.0] - 2026-08-03

Six tracked issues closed in one pass (#11-#16), all TDD.

### Changed (breaking)
- **CORS safe default** (#11): absent `CORS_ORIGINS` now **denies**
  cross-origin requests (was `*` — any origin, silently); effectively-empty
  values (`""`, `","`) also deny instead of producing the
  blocks-everything-silently `[""]`. Both cases log a warning. Set
  `CORS_ORIGINS='*'` explicitly to restore the old behavior.
- **Malformed JSON is now HTTP 400** (#13): a body that is present but not
  valid JSON raises `ValidationError` instead of being silently treated as
  empty (defaults could turn a truncated payload into a different,
  "successful" call). Absent/empty bodies remain tolerated.

### Added
- **Request-body ceiling with 413** (#12): global `MAX_BODY_BYTES` (default
  1 MiB) enforced before buffering — declared Content-Length is refused
  upfront, streams are cut at the limit; per-endpoint override via the
  `max_body_bytes` class attribute. New `PayloadTooLargeError` (413).
- **Key identity and scopes** (#15): `AUTH_API_KEY` accepts `name:key:scope`
  entries (plain `key` keeps full scope); the matched principal
  `{"name", "scopes"}` is published as `request.state.auth` and via the
  `restmcp.auth.current_auth` contextvar; `Endpoint.required_scope` returns
  403 (`ForbiddenError`) before the callback. Bearer parsing unified in
  `token_from_authorization` (two subtly-different copies before).
- **Service DI beyond Repository** (#14): any declared non-callable,
  non-underscore class attribute is injectable via the constructor (webhook
  publishers, clocks, aggregation sources); Repositories keep the
  per-instance `copy.copy`; the at-least-one-Repository rule is unchanged.

### Fixed
- **contextvars survive the thread hop** (#16): sync callbacks now run via
  `asyncio.to_thread` (copies the caller's context) instead of a bare
  `run_in_executor` — identity/correlation vars set by middleware reach the
  callback.

## [0.4.1] - 2026-08-03

### Added
- README: `Endpoint` section now documents transport selection (`expose`) and
  the OpenAPI request/response schemas, with examples.
- `examples/telemetry`: new `purge_readings` endpoint demonstrating
  `expose = "rest"` (invisible to MCP agents) plus a declared `returns`
  schema, implemented through all three layers (the in-memory DataSource keeps
  purge state) with a DI-style test.
- `RAG_KNOWLEDGE_BASE.md`: full pass to 0.4.1 — new §11.8 (expose) and §11.9
  (OpenAPI schemas), catalog/MCP-build notes, all version scopes updated.

### Changed
- `serves_mcp()` (`restmcp/rest.py`) is now the single expose predicate,
  consumed by both the `/mcp/tools` catalog and `Server.mcp_handlers` — the
  filter previously existed as two copies.

## [0.4.0] - 2026-08-03

### Added
- **Response schemas in `/openapi.json`**: `mcp_definition["returns"]` — the
  slot the `/mcp/tools` catalog already published — is now the JSON Schema of
  the callback's return value. The `200` response documents the
  `{tool, result, success}` envelope with `result` typed by it (open when
  undeclared; the envelope alone already types the skeleton). Errors are
  documented once under `default` with the error envelope
  `{tool, error, success, error_type}`. A non-dict `returns` raises
  `TypeError` at class-definition time.

## [0.3.0] - 2026-08-02

### Added
- **Request schemas in `/openapi.json`**: `requestBody` (`POST/PUT/PATCH`) and
  query `parameters` (other methods) derived from `mcp_definition` — the same
  source the MCP side publishes, so REST and MCP cannot drift. Includes
  `operationId` (tool name) and `description`; `required` mirrors validation
  (property without a `default` key); `additionalProperties: false` documents
  the extra-key rejection. Before this, every operation was empty and
  generated clients (`openapi-typescript` etc.) produced no types.
- **Per-endpoint transport selection**: `expose = "rest" | "mcp" | "both"`
  (default `"both"`). `"rest"` keeps the tool out of the MCP server and the
  `/mcp/tools` catalog (structural guarantee for write/destructive endpoints an
  agent must not see); `"mcp"` registers no public HTTP route (agent-only
  tools). Invalid values raise at class definition.

## [0.2.0] - 2026-07-02

### Changed (breaking)
- Definition errors fail at **registration (import time)** instead of
  per-request, always naming the endpoint class or tool:
  - parameter names starting with `_`/`model_` (or invalid identifiers) are
    rejected — pydantic silently dropped or refused them before;
  - a declared `default` that does not match its declared type is rejected
    (defaults are validated and coerced at registration);
  - the callback signature must accept every declared property (defaults
    included) — on 0.1.x this worked on REST and broke only on MCP.
- Unknown query-string parameters are now ignored (previously HTTP 400).
- REST and MCP validate identically via one shared pydantic model
  (`build_arg_model`); HTTP 400 messages are pydantic-style.
- Explicit JSON `null` accepted only when the property's default is `null`;
  pydantic-lax boolean inputs accepted (`1`/`0`, `"on"`/`"off"`, `"yes"`/`"no"`).

## [0.1.7] - 2026-07-02 · [0.1.6] - 2026-06-29 · [0.1.5] - 2026-06-16 and earlier

Early development line: layered scaffolding (`DataSource`/`Entity`/
`Repository`/`Service`/`Endpoint` with auto-registration and discovery), REST +
MCP from one definition, Bearer auth middleware (`AUTH_API_KEY`), method cache,
CLI (`restmcp new`), `Returns:` docstring requirement for inferred definitions,
publish workflow (PyPI + GitHub Releases). See git history for the
commit-level record.

[Unreleased]: https://github.com/JorgeHSantana/restmcp/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/JorgeHSantana/restmcp/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/JorgeHSantana/restmcp/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/JorgeHSantana/restmcp/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.1.7...v0.2.0
