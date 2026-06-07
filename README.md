# pythia

Python framework for building MCP servers with a layered architecture.

Pythia standardizes the MCP server pattern into reusable base classes and a scaffolding CLI, so you can focus on business logic instead of boilerplate.

> The name comes from the Pythia — the Oracle of Delphi. MCP servers are oracles: they answer AI clients' questions with structured data.

---

## Installation

```bash
pip install pythia
```

---

## Quick start

```bash
pythia new my-server

cd my-server
pip install -e .
python main.py
```

Generated structure:

```
my-server/
├── datasource/        # external connections (APIs, databases)
├── models/            # domain entities (Pydantic)
├── repositories/      # data access layer
├── services/          # business logic
├── tools/             # internal utilities
├── urls/              # endpoint definitions (auto-discovery)
├── main.py
└── pyproject.toml
```

---

## Architecture

```
Endpoint  →  Service  →  Repository  →  DataSource
   ↑              ↑            ↑              ↑
HTTP route    business      data          connection
              logic         access
```

Each layer knows only the layer directly below it. The `Server` singleton wires everything together.

---

## Base classes

### `DataSource`

Abstracts the connection to an external data source (REST API, database, file, etc.).

**Rule:** the class name must end with `DataSource`.

```python
import os
import requests
from pythia import DataSource

class ProductApiDataSource(DataSource):
    def __init__(self):
        self.base_url = os.getenv("PRODUCT_API_URL")
        self.api_key  = os.getenv("PRODUCT_API_KEY")

    def get(self, path: str, **params) -> dict:
        response = requests.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params=params,
        )
        response.raise_for_status()
        return response.json()
```

> **Thread safety** is the DataSource's responsibility. HTTP clients and connection pools (SQLAlchemy, pymongo) are thread-safe by design — sharing them across instances via `copy.copy` is correct and expected.

---

### `Entity`

Structured domain data. Backed by Pydantic `BaseModel` — automatic type validation.

**Rule:** the class name must end with `Entity`.

```python
from pythia import Entity

class ProductEntity(Entity):
    id:    str
    name:  str
    price: float

class OrderEntity(Entity):
    id:         str
    product_id: str
    quantity:   int
    total:      float
```

```python
product = ProductEntity(id="1", name="Widget", price=9.99)
print(product.model_dump())
# {'id': '1', 'name': 'Widget', 'price': 9.99}
```

---

### `Repository`

Fetches data via a `DataSource` and returns `Entity` objects. One responsibility per Repository: one source, one data type.

**Rules:**
- The class name must end with `Repository`.
- Must declare `data_source` as a class attribute (a `DataSource` instance).
- Must implement `get(**kwargs)`.

```python
from pythia import Repository
from datasource.product_api import ProductApiDataSource
from models.product import ProductEntity

class ProductRepository(Repository):
    data_source = ProductApiDataSource()

    def get(self, product_id: str) -> ProductEntity:
        raw = self.data_source.get(f"/products/{product_id}")
        return ProductEntity(**raw)
```

**Dependency injection for tests:**

```python
# Production — uses the real DataSource
repo = ProductRepository()

# Test — swap the DataSource without changing the class
repo = ProductRepository(data_source=MockDataSource())
```

The injection works because `Repository.__init__` accepts an optional `data_source`. If not provided, it uses `copy.copy()` of the class attribute — ensuring isolation between instances.

---

### `Service`

Orchestrates business logic. This is where joins, transformations, and rules that involve more than one data source happen.

**Rules:**
- The class name must end with `Service`.
- Class attributes of type `Repository` are auto-discovered and isolated per instance via `copy.copy`.
- Accepts repository overrides via `**kwargs` in the constructor.

```python
from pythia import Service
from repositories.product import ProductRepository
from repositories.inventory import InventoryRepository

class GetProductDetailsService(Service):
    product_repo   = ProductRepository()
    inventory_repo = InventoryRepository()

    def execute(self, product_id: str) -> dict:
        product   = self.product_repo.get(product_id=product_id)
        inventory = self.inventory_repo.get(product_id=product_id)

        return {
            **product.model_dump(),
            "stock":      inventory.quantity,
            "available":  inventory.quantity > 0,
        }
```

**Dependency injection for tests:**

```python
# Production
result = GetProductDetailsService().execute(product_id="1")

# Test — swap only the inventory repository
result = GetProductDetailsService(
    inventory_repo=MockInventoryRepository()
).execute(product_id="1")
```

> **Joining data from two databases?** Do it in the `Service`. Each `Repository` accesses a single `DataSource`. The `Service` calls both and merges the data in Python.

---

### `Endpoint`

HTTP route that auto-registers on the `Server` singleton the moment the class is defined. Validates parameters, delegates to the callback, and returns a standardized JSON response.

**Rules:**
- The class name must end with `Endpoint`.
- Must declare `mcp_definition`, `url`, `method`, and `callback`.

```python
from pythia import Endpoint
from services.product import GetProductDetailsService

class GetProductEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_product",
        "description": "Returns product details by ID",
        "parameters": {
            "properties": {
                "product_id": {
                    "type":        "string",
                    "description": "Product ID",
                },
            },
        },
    }
    url    = "/api/get-product"
    method = "POST"

    def callback(self, product_id: str) -> dict:
        return GetProductDetailsService().execute(product_id)
```

No instantiation needed — **defining the class is enough**. As soon as Python processes the `class` body, the route is registered on the server.

**Disabling an endpoint:**

```python
class GetProductEndpoint(Endpoint):
    disabled = True   # skips auto-registration
    ...
```

Set `disabled = True` to temporarily deactivate an endpoint without deleting the code. It can still be instantiated manually.

**Abstract base classes** (missing `url`, `method`, `mcp_definition`, or `callback`) are never auto-registered:

```python
class BaseAuthEndpoint(Endpoint):
    method = "POST"

    def callback(self, **kwargs):
        # shared auth logic
        ...
# ↑ Not registered — url and mcp_definition are missing

class GetUserEndpoint(BaseAuthEndpoint):
    mcp_definition = { ... }
    url = "/api/get-user"
    # ↑ Registered automatically — all required attributes present
```

**Success response:**

```json
{
  "tool":    "get_product",
  "result":  { "id": "1", "name": "Widget", "price": 9.99, "stock": 42 },
  "success": true
}
```

**Error response (`ValidationError` → 400, `NotFoundError` → 404):**

```json
{
  "tool":       "get_product",
  "error":      "product_id is required",
  "error_type": "ValidationError",
  "success":    false
}
```

---

### `Server`

Flask singleton with dual-mode: direct HTTP or MCP protocol via FastMCP.

```python
from pythia import Server
import urls  # runs urls/__init__.py → imports all endpoint modules → auto-registers all routes

server = Server.get_instance()

if __name__ == "__main__":
    server.start(host="0.0.0.0", port=5000)
```

```python
# MCP mode (for AI clients)
mcp = server.get_mcp()
```

**Built-in routes:**

| Route | Method | Description |
|-------|--------|-------------|
| `/health` | GET | Server status |
| `/mcp/tools` | GET | Lists all registered tools |

**Authentication via environment variable:**

```bash
AUTH_API_KEY=my-secret-key python main.py
```

All routes (except `/health` and `/mcp/tools`) require `Authorization: Bearer <key>`. Multiple keys are supported, comma-separated.

---

### `Logger`

Wrapper over Python's standard `logging` with consistent formatting.

```python
from pythia import Logger

logger = Logger(__name__)

logger.info("Server started")
logger.warning("Slow response: %.2fs", elapsed)
logger.error("Connection failed: %s", err)
logger.debug("Received payload: %s", payload)
```

Output:

```
[2026-06-07 10:30:00] INFO datasource.product_api — Server started
```

**Log level via environment variable:**

```bash
LOG_LEVEL=DEBUG python main.py   # DEBUG | INFO | WARNING | ERROR
```

---

### Exceptions

Imported directly from `pythia`. `Endpoint` catches them automatically and converts to HTTP responses.

```python
from pythia import ValidationError, NotFoundError

raise ValidationError("product_id is required")   # → HTTP 400
raise NotFoundError("Product not found")           # → HTTP 404
```

Hierarchy:

```
PythiaException          # base (not exposed directly)
├── ValidationError      # → HTTP 400
└── NotFoundError        # → HTTP 404
```

---

## Full example

```
my-server/
├── datasource/
│   └── product_api.py      # ProductApiDataSource
├── models/
│   └── product.py          # ProductEntity
├── repositories/
│   └── product.py          # ProductRepository
├── services/
│   └── product.py          # GetProductService
├── urls/
│   ├── __init__.py         # auto-scans urls/ — never edit this file
│   └── get_product.py      # GetProductEndpoint — auto-registered on import
└── main.py
```

**`datasource/product_api.py`**
```python
import os
import requests
from pythia import DataSource

class ProductApiDataSource(DataSource):
    def __init__(self):
        self.base_url = os.getenv("PRODUCT_API_URL")

    def fetch(self, product_id: str) -> dict:
        r = requests.get(f"{self.base_url}/products/{product_id}")
        r.raise_for_status()
        return r.json()
```

**`models/product.py`**
```python
from pythia import Entity

class ProductEntity(Entity):
    id:    str
    name:  str
    price: float
```

**`repositories/product.py`**
```python
from pythia import Repository
from datasource.product_api import ProductApiDataSource
from models.product import ProductEntity

class ProductRepository(Repository):
    data_source = ProductApiDataSource()

    def get(self, product_id: str) -> ProductEntity:
        return ProductEntity(**self.data_source.fetch(product_id))
```

**`services/product.py`**
```python
from pythia import NotFoundError, Service
from repositories.product import ProductRepository

class GetProductService(Service):
    repo = ProductRepository()

    def execute(self, product_id: str) -> dict:
        product = self.repo.get(product_id=product_id)
        if not product:
            raise NotFoundError(f"Product {product_id} not found")
        return product.model_dump()
```

**`urls/get_product.py`**
```python
from pythia import Endpoint
from services.product import GetProductService

class GetProductEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_product",
        "description": "Returns a product by ID",
        "parameters": {
            "properties": {
                "product_id": {"type": "string", "description": "Product ID"},
            },
        },
    }
    url    = "/api/get-product"
    method = "POST"

    def callback(self, product_id: str) -> dict:
        return GetProductService().execute(product_id)

# No instantiation needed — defining the class registers the route automatically.
```

**`urls/__init__.py`** — generated once by the CLI, never edited again
```python
import importlib
import pkgutil

for _info in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_info.name}")
```

**`main.py`**
```python
from pythia import Server
import urls   # triggers urls/__init__.py → imports all modules → registers all endpoints

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
```

---

## Testing with injection

```python
# tests/test_get_product.py
from services.product import GetProductService
from repositories.product import ProductRepository
from pythia import DataSource

class FakeProductApiDataSource(DataSource):
    def fetch(self, product_id: str) -> dict:
        return {"id": product_id, "name": "Test Widget", "price": 1.99}

class FakeProductRepository(ProductRepository):
    data_source = FakeProductApiDataSource()

def test_get_product_returns_correct_data():
    svc = GetProductService(repo=FakeProductRepository())
    result = svc.execute(product_id="1")
    assert result["name"] == "Test Widget"
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_API_KEY` | _(disabled)_ | Bearer key for authentication. Multiple keys supported, comma-separated. |
| `LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Naming conventions

All base classes enforce a suffix. Violating it raises `TypeError` at import time:

| Base class | Required suffix | Example |
|------------|----------------|---------|
| `DataSource` | `*DataSource` | `ProductApiDataSource` |
| `Entity` | `*Entity` | `ProductEntity` |
| `Repository` | `*Repository` | `ProductRepository` |
| `Service` | `*Service` | `GetProductService` |
| `Endpoint` | `*Endpoint` | `GetProductEndpoint` |

---

## Dependencies

```toml
flask >= 2.0
flask-cors >= 4.0
fastmcp >= 2.0
pydantic >= 2.0
click >= 8.0
```
