# Changelog

All notable changes to **restmcp** are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · versioning:
[SemVer](https://semver.org/). Every PR/commit that changes behavior, API or
docs-that-ship must add an entry under **Unreleased**; the release flow moves
that block under the new version heading (the version in `pyproject.toml` and
this file move together — the publish workflow releases whatever version is in
`pyproject.toml`).

## [Unreleased]

_(nothing yet)_

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

[Unreleased]: https://github.com/JorgeHSantana/restmcp/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/JorgeHSantana/restmcp/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/JorgeHSantana/restmcp/compare/v0.1.7...v0.2.0
