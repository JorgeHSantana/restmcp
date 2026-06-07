# Async Migration (Flask → FastAPI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Flask with FastAPI in `server.py` and `endpoint.py`, making `_callback` async with automatic sync/async detection, and removing the hardcoded `reference_date` logic.

**Architecture:** `Server` uses `FastAPI` + `CORSMiddleware` + `uvicorn`; auth becomes a dependency function injected per route via `Depends`. `Endpoint._callback` becomes `async def`, detecting whether the user's `callback` is sync (`asyncio.to_thread`) or async (`await`). All other layers (Repository, Service, DataSource, Entity, CLI) are untouched.

**Tech Stack:** `fastapi>=0.100`, `uvicorn[standard]>=0.20`, `httpx>=0.24` (dev, required by Starlette TestClient), `starlette` (installed with FastAPI).

---

### Task 1: Update dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Edit `pyproject.toml`**

Replace the `dependencies` and `dev` blocks:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pythia"
version = "0.1.0"
description = "Framework Python para construção de MCP servers"
requires-python = ">=3.11"
authors = [{ name = "pythia" }]
license = { text = "MIT" }
dependencies = [
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "fastmcp>=2.0",
    "pydantic>=2.0",
    "click>=8.0",
]

[project.scripts]
pythia = "pythia.cli:app"

[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "httpx>=0.24"]
```

- [ ] **Step 2: Install updated dependencies**

```bash
pip install -e ".[dev]"
```

Expected: installs `fastapi`, `uvicorn`, `httpx`; uninstalls `flask`, `flask-cors` if pip removes them (or just leave them installed — they won't be imported anymore).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: replace flask/flask-cors with fastapi/uvicorn in dependencies"
```

---

### Task 2: Update `test_server.py` (RED)

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: Rewrite `tests/test_server.py`**

```python
import pytest
from starlette.testclient import TestClient
from pythia.server import Server


def test_server_is_singleton():
    s1 = Server.get_instance()
    s2 = Server.get_instance()
    assert s1 is s2


def test_server_has_app():
    server = Server.get_instance()
    assert server.app is not None


def test_health_endpoint_returns_200():
    server = Server.get_instance()
    client = TestClient(server.app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_mcp_tools_endpoint_returns_empty_list():
    server = Server.get_instance()
    client = TestClient(server.app)
    response = client.get("/mcp/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["tools"] == []


def test_register_url_handler():
    server = Server.get_instance()

    class FakeHandler:
        mcp_definition = {
            "name": "fake_tool",
            "description": "tool de teste",
            "parameters": {"properties": {}},
        }

    handler = FakeHandler()
    server.register_url_handler(handler)
    assert handler in server.url_handlers


def test_mcp_tools_lists_registered_handler():
    server = Server.get_instance()

    class FakeHandler:
        mcp_definition = {
            "name": "my_tool",
            "description": "descrição",
            "parameters": {"properties": {}},
        }

    server.register_url_handler(FakeHandler())
    client = TestClient(server.app)
    response = client.get("/mcp/tools")
    tools = response.json()["tools"]
    assert any(t["name"] == "my_tool" for t in tools)


def test_server_reset_clears_instance():
    s1 = Server.get_instance()
    Server._reset()
    s2 = Server.get_instance()
    assert s1 is not s2
```

- [ ] **Step 2: Run to confirm RED**

```bash
pytest tests/test_server.py -v
```

Expected: most tests FAIL (Flask test_client / get_json not found or import errors).

---

### Task 3: Rewrite `server.py` (GREEN)

**Files:**
- Modify: `pythia/server.py`

- [ ] **Step 1: Rewrite `pythia/server.py`**

```python
import datetime as dt
import os
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware


def _validate_api_key(raw_key: str) -> bool:
    env_keys = os.getenv("AUTH_API_KEY", "")
    return bool(raw_key) and raw_key in [k.strip() for k in env_keys.split(",") if k.strip()]


def _auth_dependency(request: Request):
    if not os.getenv("AUTH_API_KEY"):
        return
    auth_header = request.headers.get("Authorization")
    api_key = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else None
    if not api_key or not _validate_api_key(api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


class Server:
    _instance: Optional["Server"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.app = FastAPI()
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.url_handlers: List = []
        self._setup_default_routes()
        self._initialized = True

    def _setup_default_routes(self):
        @self.app.get("/mcp/tools")
        def list_tools():
            return {
                "tools": [
                    {
                        "name": h.mcp_definition["name"],
                        "description": h.mcp_definition["description"],
                        "parameters": h.mcp_definition["parameters"],
                        "returns": h.mcp_definition.get("returns", {}),
                    }
                    for h in self.url_handlers
                ],
                "server": "pythia",
                "version": "0.1.0",
            }

        @self.app.get("/health")
        def health_check():
            return {
                "status": "healthy",
                "timestamp": dt.datetime.utcnow().isoformat(),
            }

    def register_url_handler(self, handler: Any):
        self.url_handlers.append(handler)

    def start(self, host: str = "0.0.0.0", port: int = 5000, debug: bool = True):
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)

    def get_mcp(self):
        from fastmcp import FastMCP

        mcp = FastMCP("pythia")
        for handler in self.url_handlers:
            self._register_fastmcp_tool(mcp, handler)
        return mcp

    def _register_fastmcp_tool(self, mcp: Any, handler: Any):
        from pydantic import Field, create_model
        from typing import List, Optional
        import inspect

        def_dict = handler.mcp_definition
        name = def_dict["name"]
        description = def_dict["description"]
        properties = def_dict.get("parameters", {}).get("properties", {})

        pydantic_fields = {}
        for prop_name, prop_data in properties.items():
            ptype = prop_data.get("type")
            py_type = str
            if ptype == "integer":
                py_type = int
            elif ptype == "boolean":
                py_type = bool
            elif ptype == "array":
                item_type = int if prop_data.get("items", {}).get("type") == "integer" else str
                py_type = List[item_type]

            default_val = prop_data.get("default", ...)
            if default_val is None:
                py_type = Optional[py_type]

            pydantic_fields[prop_name] = (
                py_type,
                Field(default=default_val, description=prop_data.get("description", "")),
            )

        ModelClass = create_model(f"{name}_args", **pydantic_fields)

        def tool_wrapper(args: ModelClass) -> dict:
            return handler.callback(**args.model_dump())

        tool_wrapper.__name__ = name
        tool_wrapper.__doc__ = description
        sig = inspect.signature(tool_wrapper)
        new_param = inspect.Parameter(
            "args", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ModelClass
        )
        tool_wrapper.__signature__ = sig.replace(parameters=(new_param,))
        mcp.add_tool(tool_wrapper)

    @classmethod
    def get_instance(cls) -> "Server":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls):
        cls._instance = None
```

- [ ] **Step 2: Run to confirm GREEN**

```bash
pytest tests/test_server.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add pythia/server.py tests/test_server.py
git commit -m "feat: replace Flask with FastAPI in Server"
```

---

### Task 4: Update `test_endpoint.py` (RED)

**Files:**
- Modify: `tests/test_endpoint.py`

- [ ] **Step 1: Rewrite `tests/test_endpoint.py`**

```python
import pytest
from starlette.testclient import TestClient

from pythia.datasource import DataSource
from pythia.endpoint import Endpoint
from pythia.exceptions import NotFoundError, ValidationError
from pythia.repository import Repository
from pythia.server import Server
from pythia.service import Service


# --- helpers ---

def _make_get_item_endpoint():
    class GetItemEndpoint(Endpoint):
        mcp_definition = {
            "name": "get_item",
            "description": "Returns an item",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/get-item"
        method = "POST"

        def callback(self, item_id: str):
            return {"id": item_id, "name": "Test Item"}


# --- suffix enforcement ---

def test_endpoint_suffix_enforced():
    with pytest.raises(TypeError, match="Endpoint"):
        class GetItem(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
            def callback(self): pass


# --- validation errors on missing attributes ---

def test_endpoint_requires_mcp_definition():
    class NoDefEndpoint(Endpoint):
        url = "/x"
        method = "POST"
        def callback(self): pass

    with pytest.raises(ValueError, match="mcp_definition"):
        NoDefEndpoint()


def test_endpoint_requires_url():
    class NoUrlEndpoint(Endpoint):
        mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
        method = "POST"
        def callback(self): pass

    with pytest.raises(ValueError, match="url"):
        NoUrlEndpoint()


def test_endpoint_requires_method():
    class NoMethodEndpoint(Endpoint):
        mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
        url = "/x"
        def callback(self): pass

    with pytest.raises(ValueError, match="method"):
        NoMethodEndpoint()


def test_endpoint_requires_callback():
    with pytest.raises(ValueError, match="callback"):
        class NoCallbackEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
        NoCallbackEndpoint()


# --- auto-registration ---

def test_endpoint_auto_registers_on_class_definition():
    class AutoEndpoint(Endpoint):
        mcp_definition = {"name": "auto_tool", "description": "auto", "parameters": {"properties": {}}}
        url = "/api/auto"
        method = "POST"
        def callback(self): return {}

    server = Server.get_instance()
    assert any(h.mcp_definition["name"] == "auto_tool" for h in server.url_handlers)


def test_endpoint_registers_on_server():
    _make_get_item_endpoint()
    server = Server.get_instance()
    assert any(h.mcp_definition["name"] == "get_item" for h in server.url_handlers)


# --- disabled ---

def test_endpoint_disabled_skips_registration():
    class DisabledEndpoint(Endpoint):
        disabled = True
        mcp_definition = {"name": "disabled_tool", "description": "x", "parameters": {"properties": {}}}
        url = "/api/disabled"
        method = "POST"
        def callback(self): return {}

    server = Server.get_instance()
    assert not any(h.mcp_definition["name"] == "disabled_tool" for h in server.url_handlers)


def test_endpoint_disabled_can_be_instantiated_manually():
    class ManualEndpoint(Endpoint):
        disabled = True
        mcp_definition = {"name": "manual_tool", "description": "x", "parameters": {"properties": {}}}
        url = "/api/manual"
        method = "POST"
        def callback(self): return {}

    ManualEndpoint()
    server = Server.get_instance()
    assert any(h.mcp_definition["name"] == "manual_tool" for h in server.url_handlers)


# --- abstract base class (no auto-registration without required attrs) ---

def test_abstract_base_endpoint_not_auto_registered():
    class BaseCustomEndpoint(Endpoint):
        method = "POST"
        def callback(self, **kwargs): return {}

    server = Server.get_instance()
    assert not any(
        getattr(h, "__class__", None) is BaseCustomEndpoint
        for h in server.url_handlers
    )


# --- HTTP callbacks (sync) ---

def test_endpoint_callback_success():
    _make_get_item_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/get-item", json={"item_id": "42"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["id"] == "42"


def test_endpoint_callback_invalid_param():
    _make_get_item_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/get-item", json={"unknown_param": "val"})
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error_type"] == "ValidationError"


def test_endpoint_callback_validation_error_from_callback():
    class RaisingEndpoint(Endpoint):
        mcp_definition = {"name": "raising_tool", "description": "raises", "parameters": {"properties": {}}}
        url = "/api/raising"
        method = "POST"
        def callback(self):
            raise ValidationError("invalid input")

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/raising", json={})
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_endpoint_callback_not_found_error():
    class NotFoundEndpoint(Endpoint):
        mcp_definition = {"name": "notfound_tool", "description": "404", "parameters": {"properties": {}}}
        url = "/api/notfound"
        method = "POST"
        def callback(self):
            raise NotFoundError("not found")

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/notfound", json={})
    assert response.status_code == 404


def test_endpoint_callback_internal_error():
    class BoomEndpoint(Endpoint):
        mcp_definition = {"name": "boom_tool", "description": "explode", "parameters": {"properties": {}}}
        url = "/api/boom"
        method = "POST"
        def callback(self):
            raise RuntimeError("unexpected boom")

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/boom", json={})
    assert response.status_code == 500
    assert response.json()["error_type"] == "InternalServerError"


# --- async callback ---

def test_endpoint_async_callback_is_awaited():
    class AsyncEndpoint(Endpoint):
        mcp_definition = {
            "name": "async_tool",
            "description": "async callback",
            "parameters": {"properties": {"x": {"type": "string"}}},
        }
        url = "/api/async"
        method = "POST"

        async def callback(self, x: str):
            return {"async": True, "x": x}

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/async", json={"x": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["async"] is True
    assert data["result"]["x"] == "hello"


# --- reference_date no longer special ---

def test_reference_date_passed_as_is():
    class DateEndpoint(Endpoint):
        mcp_definition = {
            "name": "date_tool",
            "description": "date passthrough",
            "parameters": {"properties": {"reference_date": {"type": "string"}}},
        }
        url = "/api/date"
        method = "POST"

        def callback(self, reference_date: str):
            return {"received": reference_date}

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/date", json={"reference_date": "2024-01-01"})
    assert response.status_code == 200
    assert response.json()["result"]["received"] == "2024-01-01"


# --- Full-stack injection: Endpoint → Service → Repository → DataSource ---

class _FakeDataSource(DataSource):
    def __init__(self, records: dict):
        self._records = records


class _ItemRepository(Repository):
    data_source = _FakeDataSource({"1": "Real Item"})

    def get(self, item_id: str):
        return self.data_source._records.get(item_id)


class _GetItemService(Service):
    repo = _ItemRepository()

    def execute(self, item_id: str):
        result = self.repo.get(item_id=item_id)
        if result is None:
            raise NotFoundError(f"Item {item_id} not found")
        return {"id": item_id, "name": result}


def test_endpoint_uses_service_with_real_repository():
    class FullStackEndpoint(Endpoint):
        mcp_definition = {
            "name": "fullstack_tool",
            "description": "full stack",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/fullstack"
        method = "POST"

        def callback(self, item_id: str):
            return _GetItemService().execute(item_id)

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/fullstack", json={"item_id": "1"})
    assert response.status_code == 200
    assert response.json()["result"]["name"] == "Real Item"


def test_endpoint_uses_service_with_injected_mock_repository():
    class MockItemRepository(Repository):
        data_source = _FakeDataSource({"99": "Mock Item"})

        def get(self, item_id: str):
            return self.data_source._records.get(item_id)

    class FullStackMockEndpoint(Endpoint):
        mcp_definition = {
            "name": "fullstack_mock_tool",
            "description": "full stack mock",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/fullstack-mock"
        method = "POST"

        def callback(self, item_id: str):
            return _GetItemService(repo=MockItemRepository()).execute(item_id)

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/fullstack-mock", json={"item_id": "99"})
    assert response.status_code == 200
    assert response.json()["result"]["name"] == "Mock Item"


def test_endpoint_service_not_found_propagates_as_404():
    class NotFoundMockRepository(Repository):
        data_source = _FakeDataSource({})

        def get(self, **kwargs):
            return None

    class FullStackNotFoundEndpoint(Endpoint):
        mcp_definition = {
            "name": "fullstack_notfound_tool",
            "description": "full stack 404",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/fullstack-notfound"
        method = "POST"

        def callback(self, item_id: str):
            return _GetItemService(repo=NotFoundMockRepository()).execute(item_id)

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/fullstack-notfound", json={"item_id": "missing"})
    assert response.status_code == 404
    assert response.json()["error_type"] == "NotFoundError"
```

- [ ] **Step 2: Run to confirm RED**

```bash
pytest tests/test_endpoint.py -v
```

Expected: HTTP callback tests FAIL (`app.test_client` not found); structural tests (suffix, auto-register, disabled) may pass since they don't hit HTTP.

---

### Task 5: Rewrite `endpoint.py` (GREEN)

**Files:**
- Modify: `pythia/endpoint.py`

- [ ] **Step 1: Rewrite `pythia/endpoint.py`**

```python
import asyncio
import inspect
from abc import ABC

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from pythia.exceptions import PythiaException, ValidationError


class Endpoint(ABC):
    disabled: bool = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Endpoint"):
            raise TypeError(
                f"Endpoint subclasses must end with 'Endpoint' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Endpoint'."
            )

        if getattr(cls, "disabled", False):
            return

        _required = ("url", "method", "mcp_definition", "callback")
        if all(vars(cls).get(attr) for attr in _required):
            cls()

    async def _callback(self, request: Request):
        try:
            try:
                data = await request.json()
            except Exception:
                data = {}
            data = data or {}

            valid_params = self.mcp_definition.get("parameters", {}).get("properties", {})
            parameters = {}

            for key, value in data.items():
                if key not in valid_params:
                    raise ValidationError(f"Invalid parameter: {key}")
                parameters[key] = value

            if inspect.iscoroutinefunction(self.callback):
                result = await self.callback(**parameters)
            else:
                result = await asyncio.to_thread(self.callback, **parameters)

            return JSONResponse({
                "tool": self.mcp_definition["name"],
                "result": result,
                "success": True,
            })

        except PythiaException as e:
            return JSONResponse({
                "error": e.message,
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": e.__class__.__name__,
            }, status_code=e.status_code)

        except Exception as e:
            return JSONResponse({
                "error": str(e),
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": "InternalServerError",
            }, status_code=500)

    def __init__(self):
        from pythia.server import Server, _auth_dependency

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

        endpoint_self = self

        async def route_handler(request: Request):
            return await endpoint_self._callback(request)

        server = Server.get_instance()
        server.app.add_api_route(
            self.url,
            route_handler,
            methods=[self.method],
            dependencies=[Depends(_auth_dependency)],
        )
        server.register_url_handler(self)
```

- [ ] **Step 2: Run endpoint tests to confirm GREEN**

```bash
pytest tests/test_endpoint.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Run full suite**

```bash
pytest --tb=short
```

Expected: all tests pass. If any non-endpoint/server test fails, investigate — the other layers were not modified.

- [ ] **Step 4: Commit**

```bash
git add pythia/endpoint.py tests/test_endpoint.py
git commit -m "feat: async endpoint _callback + remove reference_date (Flask → FastAPI)"
```

---

### Task 6: Final verification

- [ ] **Step 1: Run full suite with coverage**

```bash
pytest --cov=pythia --cov-report=term-missing
```

Expected: all tests pass, coverage comparable to before migration.

- [ ] **Step 2: Confirm `flask` is no longer imported anywhere**

```bash
grep -r "from flask\|import flask" pythia/
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore: verify async migration complete — flask fully removed"
```
