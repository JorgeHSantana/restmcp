# restmcp

[![Test & Publish](https://github.com/JorgeHSantana/restmcp/actions/workflows/publish.yml/badge.svg)](https://github.com/JorgeHSantana/restmcp/actions/workflows/publish.yml)
[![codecov](https://codecov.io/gh/JorgeHSantana/restmcp/branch/main/graph/badge.svg)](https://codecov.io/gh/JorgeHSantana/restmcp)
[![PyPI](https://img.shields.io/pypi/v/restmcp.svg)](https://pypi.org/project/restmcp/)
[![Python](https://img.shields.io/pypi/pyversions/restmcp.svg)](https://pypi.org/project/restmcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> One framework. MCP tools and REST endpoints, auto-registered.

Python framework for building **MCP servers** with a layered architecture and REST compatibility.  
Annotated classes become MCP tools and HTTP endpoints: auto-registered, dependency-injected, sync/async agnostic.

---

## Architecture

```mermaid
graph LR
    LLM["🤖 LLM / Client"] -->|"HTTP or MCP"| EP["Endpoint"]
    EP --> SV["Service"]
    SV --> RP["Repository"]
    RP --> DS["DataSource"]
    DS --> EX[("External\nAPI / DB")]

    style EP fill:#4f46e5,color:#fff,stroke:none
    style SV fill:#7c3aed,color:#fff,stroke:none
    style RP fill:#9333ea,color:#fff,stroke:none
    style DS fill:#a855f7,color:#fff,stroke:none
```

Each layer knows only the layer directly below it. Every class name is suffix-enforced at import time: a typo raises `TypeError` before the server starts.

---

## Installation

```bash
pip install restmcp
```

---

## Quick start

```bash
restmcp new my-server
cd my-server
pip install -e .
python main.py
```

Generated structure:

```
my-server/
├── datasources/       # external connections (APIs, databases)
├── entities/          # domain models (Pydantic)
├── repositories/      # data access layer
├── services/          # business logic
├── utils/             # internal helpers
├── endpoints/         # endpoint definitions (auto-discovered)
├── main.py
└── pyproject.toml
```

---

## Changelog

Release-by-release record in [CHANGELOG.md](CHANGELOG.md) — every behavior/API
change lands there under *Unreleased* and ships with the version bump.

---

## Behaviour changes in 0.8.0

Input handling is stricter on **both** transports (REST and MCP `tools/call`):

- **Booleans are strict.** A `bool` parameter accepts only JSON `true`/`false`;
  `"true"`, `"yes"`, `"on"`, `1`, `0` are now rejected (they were coerced). In a
  REST query string, where nothing is typed, the literals `true`/`false` are the
  only accepted spellings (`?flag=true`).
- **`Literal[...]` becomes `enum`.** `Literal["a", "b"]` (also `Optional[...]`,
  with a default, and `list[Literal[...]]`) is published with `enum` in
  `tools/list`, `/mcp/tools` and OpenAPI, and a value outside the set is
  rejected. An `enum` in a hand-written `mcp_definition` is enforced too (it was
  only published).
- **Rejected arguments carry `code: "validation_error"`.** Still HTTP 400 with
  `error_type: "ValidationError"` (the `code` was `null`); over MCP the same
  envelope is the `structuredContent` of the `isError` result, which used to be
  fastmcp's raw pydantic text with the rejected value echoed back. The message
  names the parameter, never the value.

---

## Breaking changes in 0.2.0

Definition errors now fail at **registration (import time)** instead of per-request, always naming the endpoint class or tool:

- Parameter names starting with `_` or `model_` (or that are not valid Python identifiers) are rejected — pydantic silently dropped or refused them before.
- A declared `default` that does not match its declared type is rejected (defaults are now validated and coerced at registration).
- The callback signature must accept every declared property (defaults included) — on 0.1.x this worked on REST and broke only on MCP.

Runtime changes: unknown query-string parameters are now ignored (previously HTTP 400); REST and MCP now validate identically via one shared pydantic model, so HTTP 400 messages are pydantic-style (e.g. "Extra inputs are not permitted"); explicit JSON `null` is accepted only when the property's default is `null`; pydantic-lax boolean inputs (`1`/`0`, `"on"`/`"off"`, `"yes"`/`"no"`) are accepted (until 0.7.x — strict since 0.8.0, see above).

---

## How it works

```mermaid
sequenceDiagram
    participant C as Client / LLM
    participant E as Endpoint
    participant S as Service
    participant R as Repository
    participant D as DataSource

    C->>E: POST /api/get-product {"product_id": "1"}
    E->>S: service.execute(product_id="1")
    S->>R: repo.get(product_id="1")
    R->>D: data_source.fetch("1")
    D-->>R: raw dict
    R-->>S: ProductEntity
    S-->>E: result dict
    E-->>C: {"tool": "get_product", "result": {...}, "success": true}
```

---

## Base classes

### `DataSource`

Abstracts the connection to an external data source (REST API, database, file).  
**Rule:** class name must end with `DataSource`.

```python
import httpx
from restmcp import DataSource

class ProductApiDataSource(DataSource):
    base_url = "https://api.example.com"

    async def fetch(self, product_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{self.base_url}/products/{product_id}")
            r.raise_for_status()
            return r.json()
```

---

### `Entity`

Structured domain data backed by Pydantic. Automatic type validation.  
**Rule:** class name must end with `Entity`.

```python
from restmcp import Entity

class ProductEntity(Entity):
    id:    str
    name:  str
    price: float
```

---

### `Repository`

Fetches data via a `DataSource` and returns `Entity` objects. One source, one data type.  
**Rules:** name ends with `Repository`; must declare `data_source` as class attribute; must implement `get()`.

```python
from restmcp import Repository
from datasources.product_api import ProductApiDataSource
from entities.product import ProductEntity

class ProductRepository(Repository):
    data_source = ProductApiDataSource()

    async def get(self, product_id: str) -> ProductEntity:
        raw = await self.data_source.fetch(product_id)
        return ProductEntity(**raw)
```

**Dependency injection:**

```python
repo = ProductRepository()                              # uses real DataSource
repo = ProductRepository(data_source=MockDataSource())  # injects mock for tests
```

`Repository.__init__` uses `copy.copy()` of the class attribute: instances are always isolated.

---

### `Service`

Orchestrates business logic. Where joins, transformations, and multi-source rules live.  
**Rules:** name ends with `Service`; must declare at least one `Repository` as class attribute.

```python
from restmcp import Service
from repositories.product import ProductRepository

class GetProductService(Service):
    repo = ProductRepository()

    async def execute(self, product_id: str) -> dict:
        product = await self.repo.get(product_id=product_id)
        return product.model_dump()
```

**Dependency injection:**

```python
svc = GetProductService()                       # production
svc = GetProductService(repo=MockRepository())  # test
```

Repository class attributes are auto-discovered via MRO and isolated per instance.

---

### `Endpoint`

HTTP + MCP route. **Auto-registers on class definition**: no manual wiring needed.  
**Rules:** name ends with `Endpoint`; must declare `url`, `method`, and `callback`. `mcp_definition` is inferred from the callback when omitted.

```python
from typing import Annotated

from restmcp import Endpoint
from services.product import GetProductService

class GetProductEndpoint(Endpoint):
    url    = "/api/get-product"
    method = "POST"

    async def callback(self, product_id: Annotated[str, "Product ID"]) -> dict:
        """Get a product by ID.

        Returns: the product object (id, name, price, currency).
        """
        return await GetProductService().execute(product_id)
```

The MCP tool name (`get_product`), description (the **full** callback docstring),
and parameter schema (types + `Annotated` text) are inferred from the `callback`.

**The callback docstring must include a `Returns:` section** — the MCP client only
ever sees the tool description, so an inferred tool is required to spell out what it
returns there (the Portuguese `Retorna:`/`Retorno:` are also accepted). Defining an
inferred endpoint without one raises a `TypeError` at class-definition time.

Set `mcp_definition` explicitly only when you need to override the inferred schema;
the `Returns:` requirement does not apply to hand-written definitions.

Defining the class is enough. The route is registered on the `Server` singleton the moment Python processes the class body.

**Choosing the transport (0.3.0+):**

```python
class RejectEndpoint(Endpoint):
    expose = "rest"   # "rest" | "mcp" | "both" (default)
    ...
```

`"rest"` serves the HTTP route but keeps the tool out of the MCP server **and**
the `/mcp/tools` catalog — an agent never even sees it (write endpoints an LLM
must not call, binary downloads that make no sense as tools). `"mcp"` registers
the tool with no public HTTP route (agent-only tools). Invalid values raise at
class definition. The filter is one place (`Server.mcp_handlers`), so the
catalog and the MCP server cannot disagree.

**OpenAPI schemas (0.3.0/0.4.0+):** `/openapi.json` documents every operation
from the same `mcp_definition` the MCP side publishes — REST and MCP cannot
drift:

- **Request** (0.3.0): `requestBody` for `POST/PUT/PATCH`, query `parameters`
  otherwise, plus `operationId` and `description`. `required` mirrors
  validation (a property without a `default`); `additionalProperties: false`
  documents the extra-key rejection.
- **Response** (0.4.0): declare `mcp_definition["returns"]` as the JSON Schema
  of the callback's return value and the `200` documents the
  `{tool, result, success}` envelope with `result` typed by it (open when
  undeclared — the envelope alone already types the skeleton). Errors are
  documented once, under `default`, with the error envelope.

**Parameter types and validation:** each callback annotation becomes one JSON
Schema property, and REST and MCP validate it with the same pydantic model:

| Annotation | Schema | Accepts |
|---|---|---|
| `str` | `{"type": "string"}` | strings only (no number/boolean coercion) |
| `int` | `{"type": "integer"}` | integers, integral floats, numeric strings; never a boolean |
| `float` | `{"type": "number"}` | numbers, numeric strings; never a boolean |
| `bool` | `{"type": "boolean"}` | JSON `true`/`false` only (0.8.0+); query string: `true`/`false` |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` | a member of the set (0.8.0+); integer literals also take `"2"`, never a boolean |
| `list[T]` | `{"type": "array", "items": <T>}` | a JSON array, each item validated as `T` |
| `dict` | `{"type": "object"}` | a JSON object |

`Optional[T]` / a default of `None` also accepts `null`; a non-`None` default is
validated against `T` at registration. A missing required parameter, an unknown
one, or a value of the wrong type answers HTTP 400 (REST) / `isError` (MCP) with
`code: "validation_error"`.

```python
class GetProductEndpoint(Endpoint):
    mcp_definition = {
        "name": "get_product",
        "description": "Get a product by ID.",
        "parameters": {"properties": {"product_id": {"type": "string"}}},
        "returns": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "price": {"type": "number"}},
            "required": ["id", "price"],
        },
    }
    ...
```

Generated clients (`openapi-typescript`, `openapi-python-client`, …) now get
full request/response types — a renamed response field becomes a codegen diff
instead of silently empty UI data.

**Success status code (0.6.0+):** the HTTP code of the success envelope is a
*declaration*, and the same declaration feeds the response and the OpenAPI
document — they cannot disagree:

```python
class StartRunEndpoint(Endpoint):
    success_code = 202   # "accepted, poll for the outcome" — default 200
    ...
```

2xx only, validated at class definition; `204` is rejected (No Content forbids
a body, the envelope always has one). Errors ignore it — their code comes from
the exception class (`RestMCPException.status_code`), so the full picture is:
**error code = exception type, success code = endpoint declaration.**

**Raw responses (0.6.0+):** the FastAPI escape hatch, for responses that do not
fit the envelope (file downloads, redirects, conditional codes, custom
headers). Three locks:

```python
class ExportCsvEndpoint(Endpoint):
    expose = "rest"        # lock 1: no MCP side — required, or import fails
    raw_response = True    # lock 2: opt-in, never inferred from the return type
    ...
    def callback(self, device_id):
        return PlainTextResponse(csv, media_type="text/csv",
                                 headers={"content-disposition": "attachment"})
```

1. **Requires `expose = "rest"`** — a raw HTTP response has no MCP
   representation, so the tool must not exist on that side.
2. **Opt-in declared** — a callback returning a `Response` *without* the flag
   is a programming error (500, pointed message in the log), never a silent
   passthrough; declared but returning plain data errors the same way.
3. **Success only** — exceptions raised in a raw endpoint still produce the
   standard error envelope with the exception's status code: clients keep one
   error format everywhere. Auth, scopes, body limits and parameter validation
   also apply unchanged — the hatch is about the response, not the pipeline.

In OpenAPI a raw operation promises nothing it cannot keep: no success
envelope, one honest `default` describing that code, headers and body belong
to the endpoint.

**Disabling an endpoint:**

```python
class GetProductEndpoint(Endpoint):
    disabled = True  # skips auto-registration; can still be instantiated manually
    ...
```

**Abstract base classes** (missing any required attribute) are never auto-registered:

```python
class BaseAuthEndpoint(Endpoint):
    method = "POST"
    def callback(self, **kwargs): ...
# ↑ not registered: url is missing

class GetUserEndpoint(BaseAuthEndpoint):
    url = "/api/get-user"
    def callback(self, user_id: str) -> dict: ...
# ↑ registered automatically: url, method, and callback all present
```

**Sync and async callbacks** are both supported: restmcp detects and handles either:

```python
# sync: runs in a thread pool, does not block the event loop
def callback(self, product_id: str) -> dict:
    return requests.get(f"https://api.example.com/products/{product_id}").json()

# async: awaited directly; use asyncio.gather for parallel I/O
async def callback(self, product_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.example.com/products/{product_id}")
        return r.json()
```

**The contract (identical for REST and MCP):**

- A **sync** callback runs in a threadpool, so blocking work — a synchronous DB
  driver, `requests`, file I/O — never stalls the event loop. Writing your
  `Repository`/`DataSource` synchronously is the simple, correct default.
- An **async** callback is awaited directly. Inside it, **keep the I/O async**
  (`httpx`, an async DB driver): calling blocking code from an async callback
  *does* stall the loop, because it is not moved to a thread.

Rule of thumb: sync all the way down, or async all the way down — don't put
blocking calls inside an `async def` callback.

**Response format:**

```json
{ "tool": "get_product", "result": { ... }, "success": true }
```

```json
{ "tool": "get_product", "error": "not found", "error_type": "NotFoundError", "success": false, "code": null }
```

`code` (0.7.0+) is always present: the exception's machine-readable `code`, or
`null` when it defines none. `tool` is `null` when the error happens before an
endpoint is resolved (e.g. the 401 from auth, which carries
`code: "invalid_api_key"`).

Arguments the framework rejects (wrong type, missing required, unknown
parameter, value outside an `enum`, non-boolean for a boolean, body that is not
a JSON object) answer HTTP 400 with `code: "validation_error"` (0.8.0+; `null`
before). The message names each parameter and what it expects — never the
rejected value:

```json
{ "tool": "cancel_line", "error": "confirm: Input should be a valid boolean", "success": false, "error_type": "ValidationError", "code": "validation_error" }
```

---

### `Server`

Singleton serving REST (FastAPI/uvicorn) and the MCP protocol (FastMCP) from one
codebase. The recommended entry point is `asgi_app()`, which mounts both:

```python
import uvicorn

from restmcp import Server, autodiscover

autodiscover("endpoints")  # imports every endpoint module so each one registers

app = Server.get_instance().asgi_app()  # REST at "/", MCP at "/mcp-protocol/"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```python
# REST only (no MCP), if that is all you need:
Server.get_instance().start(host="0.0.0.0", port=5000)

# The raw FastMCP instance (escape hatch):
mcp = Server.get_instance().get_mcp()
```

**Built-in routes:**

| Route | Method | Auth required |
|-------|--------|---------------|
| `/health` | GET | No |
| `/mcp/tools` | GET | No |
| _your endpoints_ | POST | Yes (if `AUTH_API_KEY` is set) |

---

## Production checklist

- **Running REST + MCP together:** use `app = server.asgi_app()` — it mounts both and wires the FastMCP lifespan. **Do not** call `server.app.mount(...)` directly: it raises "Task group is not initialized" on the first MCP request. MCP is served at the `mcp_path` you pass (default `/mcp-protocol/`, trailing slash); REST stays at `/`.
- **Opening and closing resources (HTTP clients, pools):** pass `lifespan=` to `asgi_app()` — a callable taking the parent Starlette app and returning an async context manager. It is chained to the FastMCP lifespan (FastMCP starts first and stops last), so MCP keeps working; an exception before the `yield` propagates and the server does not come up.

  Keep the resource where your code can reach it — a class attribute or module-level variable. The `app` passed to the lifespan is the parent Starlette app; callbacks receive no request, so they cannot reach its `app.state`.

  ```python
  from contextlib import asynccontextmanager
  import httpx
  from restmcp import DataSource, Server

  class ProductApiDataSource(DataSource):
      client: httpx.AsyncClient | None = None   # opened/closed by the lifespan below

      async def fetch(self, product_id: str) -> dict:
          r = await ProductApiDataSource.client.get(f"https://api.example.com/products/{product_id}")
          r.raise_for_status()
          return r.json()

  @asynccontextmanager
  async def lifespan(app):
      ProductApiDataSource.client = httpx.AsyncClient(timeout=10)
      try:
          yield
      finally:
          await ProductApiDataSource.client.aclose()
          ProductApiDataSource.client = None

  app = Server.get_instance().asgi_app(lifespan=lifespan)
  ```
- **Long calls:** restmcp imposes no per-call deadline, on REST or MCP; the deadline belongs to the ASGI server / proxy in front (e.g. Cloud Run `timeoutSeconds`). Verified with 300 s and 330 s calls on both transports (fastmcp 4.2.1, uvicorn 0.54). Raise the **client's** timeout above your longest call — `httpx` defaults to 5 s (`httpx.AsyncClient(timeout=None)` or a large `read`); `fastmcp.Client(url, timeout=...)` for MCP. MCP results stream as SSE with a keep-alive ping every 15 s, so idle-read timeouts do not fire; a REST response is silent until the callback returns, so every idle timeout on the path (load balancer, reverse proxy) must exceed the call.
- **Auth:** set `AUTH_API_KEY` (Bearer). `asgi_app()` protects REST **and** the mounted MCP; `/health` and `/mcp/tools` remain public. Multiple keys: comma-separated.
- **Serialization:** callback return values are serialized with `jsonable_encoder` — `datetime` → ISO 8601, `Decimal` → string, Pydantic models → dict, automatically. Override per-entity via `serialize()`.
- **Typed parameters:** a parameter declared as `{"type": "string", "format": "date-time"}` arrives in the callback as a **string** — coerce to `datetime` if needed.
- **Caching:** wrap an expensive Service method with `@cached_method(ttl=seconds, maxsize=128)` — the cache key is built from the arguments (via `repr`), so it works even with `list`/`dict` args. The store is bounded (`maxsize`) and self-purging (TTL), so it is safe in long-running processes. Cache plain-data arguments, not rich objects.
- **Folders vs suffixes:** only **class suffixes** are enforced (`*Entity`, `*Repository`, `*Service`, `*Endpoint`, `*DataSource`); folder names are free.
- **Dependencies:** 0.8.0 requires `fastmcp>=3.4`; the test suite passes on fastmcp 4.2.1, 3.4.11 and 3.4.0 (fastmcp 3.0–3.3 and 2.x fail it). Installing fastmcp also pulls in `starlette`.

A complete, runnable server using all of the above lives in [examples/telemetry/](examples/telemetry/) — no database required.

---

## Exceptions

Raised inside `callback`: caught by `Endpoint` and converted to HTTP responses automatically.

```python
from restmcp import ValidationError, NotFoundError

raise ValidationError("product_id is required")  # → HTTP 400
raise NotFoundError("Product not found")          # → HTTP 404
raise ValidationError("token expired", code="session_expired")  # → 400, "code" in the envelope (0.7.0+)
```

`"validation_error"` is the code the framework itself sets when it rejects the
arguments; a `ValidationError` raised by your callback keeps the `code` you
give it (`null` by default), so clients can tell "bad input shape" from a
business rule.

The base class and the auth errors are imported from `restmcp.exceptions` (not
re-exported by `restmcp`); use the base class for any other status with a `code`:

```python
from restmcp.exceptions import RestMCPException, UnauthorizedError, ForbiddenError

raise RestMCPException("upstream session expired", 503, code="session_expired")  # → 503
raise ForbiddenError("not your tenant", code="wrong_tenant")                       # → 403
```

```mermaid
graph TD
    RestMCPException --> ValidationError["ValidationError (400)"]
    RestMCPException --> NotFoundError["NotFoundError (404)"]
```

---

## Testing with injection

```python
from restmcp import DataSource
from repositories.product import ProductRepository
from services.product import GetProductService

class FakeProductApiDataSource(DataSource):
    async def fetch(self, product_id: str) -> dict:
        return {"id": product_id, "name": "Test Widget", "price": 1.99}

def test_get_product():
    svc = GetProductService(repo=ProductRepository(data_source=FakeProductApiDataSource()))
    result = svc.execute(product_id="1")
    assert result["name"] == "Test Widget"
```

---

## Key identity and scopes (0.5.0+)

`AUTH_API_KEY` entries accept an optional `name:key:scope` form alongside the
plain `key` form (which keeps full scope):

```bash
export AUTH_API_KEY="painel:sk_abc:read, campo:sk_def:read+write, sk_legacy"
```

The matched principal `{"name", "scopes"}` is published as `request.state.auth`
and via the `restmcp.auth.current_auth` contextvar (visible inside sync
callbacks too). Declare `required_scope = "write"` on an `Endpoint` (0.5.0+;
enforced on MCP since 0.7.0) and a key that lacks it is refused before the
callback on **both** transports: REST answers `403`, an MCP `tools/call`
answers `isError: true` with the same error envelope as `structuredContent`
(`code: "forbidden_scope"`). `expose = "rest"` is no longer needed as a scope
workaround — keep it for endpoints that make no sense as a tool. The secret
itself never propagates.

Order of checks: over MCP the arguments are validated before the scope
check, so a key without the scope that sends invalid arguments gets
`code: "validation_error"` rather than `forbidden_scope` (the callback runs in
neither case), while REST checks the scope first.

Over MCP every `RestMCPException` becomes `isError: true` with the shared
envelope (`tool, error, success, error_type, code`) as `structuredContent` —
and so do invalid arguments (0.8.0+, `code: "validation_error"`, same message
as REST);
fastmcp's own exceptions (e.g. a deliberate `ToolError`) keep fastmcp's
handling; any other exception is logged and reaches the client as the generic
`InternalServerError` envelope, exactly as on REST.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_API_KEY` | _(disabled)_ | Bearer token. Multiple keys supported comma-separated. |
| `CORS_ORIGINS` | *(unset — deny)* | Allowed origins, comma-separated. **Absent or empty denies cross-origin (0.5.0; was `*`)** — set `'*'` explicitly to allow any. A warning is logged when denied by omission. |
| `MAX_BODY_BYTES` | `1048576` | Global request-body ceiling (bytes); bodies over it get **413**. Override per endpoint with the `max_body_bytes` class attribute. |
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

---

## Naming conventions

All base classes enforce a suffix. Violating it raises `TypeError` at import time: before the server starts.

| Base class | Required suffix | Example |
|------------|----------------|---------|
| `DataSource` | `*DataSource` | `ProductApiDataSource` |
| `Entity` | `*Entity` | `ProductEntity` |
| `Repository` | `*Repository` | `ProductRepository` |
| `Service` | `*Service` | `GetProductService` |
| `Endpoint` | `*Endpoint` | `GetProductEndpoint` |

---

## Dependencies

```
fastapi    >= 0.100
uvicorn    >= 0.20
fastmcp    >= 2.0
pydantic   >= 2.0
click      >= 8.0
```

---

## Author

**Jorge Henrique Moreira Santana**  
Electrical Engineer, Postgraduate in Artificial Intelligence  
[LinkedIn](https://www.linkedin.com/in/jorge-santana-b246874a/) · jorge.henrique.moreira.santana@gmail.com

---

## License

[MIT](LICENSE)
