# Async Migration: Flask → FastAPI

**Date:** 2026-06-07  
**Status:** Approved

## Summary

Replace Flask with FastAPI across the pythia framework. The goal is async-native HTTP handling while keeping the developer-facing interface (auto-registration, suffixes, `disabled`, `callback`) unchanged.

## Scope

| File | Change |
|---|---|
| `pythia/server.py` | Flask → FastAPI, auth via dependency injection |
| `pythia/endpoint.py` | `_callback` → `async def`, sync/async detection, remove `reference_date` |
| `pyproject.toml` | Remove `flask`/`flask-cors`, add `fastapi`/`uvicorn[standard]`/`httpx` |
| `tests/test_server.py` | Adapt to Starlette `TestClient` |
| `tests/test_endpoint.py` | Adapt to Starlette `TestClient` |

**Not in scope:** Repository, Service, DataSource, Entity, CLI — unchanged.

## Architecture

### Server (`server.py`)

- `self.app = FastAPI()` replaces `Flask(__name__)`
- CORS via `CORSMiddleware` from `starlette.middleware.cors`
- Auth via FastAPI dependency function injected per-route (replaces `@app.before_request`)
- Multiple API keys remain supported via comma-separated `AUTH_API_KEY` env var
- Default routes (`/health`, `/mcp/tools`) use `@self.app.get` decorators
- `server.start()` calls `uvicorn.run(self.app, host=host, port=port)`
- `server.get_mcp()` for FastMCP — unchanged
- Singleton (`_instance`, `_reset`, `get_instance`) — unchanged

### Endpoint (`endpoint.py`)

`_callback` becomes `async def` and detects whether the user's `callback` is sync or async:

```python
async def _callback(self, request: Request):
    data = await request.json() or {}
    # parameter validation (unchanged logic)
    ...

    if inspect.iscoroutinefunction(self.callback):
        result = await self.callback(**parameters)
    else:
        result = await asyncio.to_thread(self.callback, **parameters)

    return JSONResponse({"tool": ..., "result": result, "success": True})
```

- Sync `callback` runs via `asyncio.to_thread()` — uses Python's default `ThreadPoolExecutor`, does not block the event loop
- Async `callback` is awaited directly
- `request.get_json()` → `await request.json()`
- `jsonify` → `JSONResponse` from `starlette.responses`
- Route registration: `app.add_url_rule` → `app.add_api_route`
- `__init_subclass__`, `disabled`, suffix enforcement — unchanged

### `reference_date` removal

The hardcoded `reference_date` parsing (current `endpoint.py:39-44`) is removed as part of this migration. It was domain logic leaking into the framework. The rewrite of `_callback` is the natural moment to excise it.

## Developer Interface

No changes to how developers use the framework:

```python
class GetClientEndpoint(Endpoint):
    url = "/clients/{client_id}"
    method = "POST"
    mcp_definition = {...}

    def callback(self, client_id: int):       # sync — works
        return self.service.get_client(client_id)

    # or

    async def callback(self, client_id: int): # async — also works
        return await self.service.get_client(client_id)
```

Note: FastAPI uses `{param}` path syntax instead of Flask's `<type:param>`.

## Dependencies

```toml
# removed
flask
flask-cors

# added
fastapi
uvicorn[standard]
httpx              # required by Starlette TestClient
```

## Testing

- `TestClient` from `starlette.testclient` replaces Flask's test client
- Interface is synchronous — tests stay `def test_...`, no `async def` needed
- `client.post(url, json={...})` calls remain identical
- Main changes: imports and `conftest.py` fixtures that mock `request.get_json()`

## Trade-offs

| | Flask (current) | FastAPI (target) |
|---|---|---|
| Concurrency | Thread-per-request | Async event loop |
| Sync callbacks | Native | Via `asyncio.to_thread()` |
| Async callbacks | Not supported | Native |
| Max simultaneous slow requests | ~100 (thread pool) | Thousands |
| Test client | Flask built-in | Starlette (requires `httpx`) |
| Breaking change for users | — | URL param syntax (`<int:id>` → `{id}`) |

## Breaking Change Note

Flask uses `<int:client_id>` in URLs; FastAPI uses `{client_id}`. This is the only interface change visible to framework users, and only affects the `url` attribute of their `Endpoint` subclasses.
