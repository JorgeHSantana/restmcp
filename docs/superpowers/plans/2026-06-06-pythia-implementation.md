# pythia Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o pacote Python `pythia` — framework para MCP servers com arquitetura em camadas, CLI de scaffolding e dual-mode Flask + FastMCP.

**Architecture:** Classes base declarativas com `__init_subclass__` enforcement de sufixos. Server singleton Flask + FastMCP. CLI `pythia new <nome>` gera estrutura completa. Cada camada (DataSource → Repository → Endpoint → Server) é independente e testável.

**Tech Stack:** Python 3.11+, Flask, flask-cors, fastmcp, pydantic, click, pytest

---

## Estrutura de arquivos

```
pythia/
├── pythia/
│   ├── __init__.py
│   ├── exceptions.py
│   ├── logging.py
│   ├── datasource.py
│   ├── entity.py
│   ├── repository.py
│   ├── server.py
│   ├── endpoint.py
│   └── cli/
│       ├── __init__.py
│       └── new.py
├── tests/
│   ├── conftest.py
│   ├── test_exceptions.py
│   ├── test_logger.py
│   ├── test_datasource.py
│   ├── test_entity.py
│   ├── test_repository.py
│   ├── test_server.py
│   ├── test_endpoint.py
│   └── test_cli.py
└── pyproject.toml
```

---

## Task 1: Setup do projeto

**Files:**
- Create: `pyproject.toml`
- Create: `pythia/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Criar pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pythia"
version = "0.1.0"
description = "Framework Python para construção de MCP servers"
requires-python = ">=3.11"
dependencies = [
    "flask",
    "flask-cors",
    "fastmcp",
    "pydantic",
    "click",
]

[project.scripts]
pythia = "pythia.cli:app"

[project.optional-dependencies]
dev = ["pytest", "pytest-cov"]
```

- [ ] **Step 2: Criar pythia/__init__.py vazio**

```python
```

- [ ] **Step 3: Criar tests/conftest.py com fixture de reset do Server**

```python
import pytest

@pytest.fixture(autouse=True)
def reset_server():
    from pythia.server import Server
    Server._reset()
    yield
    Server._reset()
```

- [ ] **Step 4: Instalar em modo editável**

```bash
pip install -e ".[dev]"
```

Expected: sem erros.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml pythia/__init__.py tests/conftest.py
git commit -m "chore: project setup"
```

---

## Task 2: Exceptions

**Files:**
- Create: `pythia/exceptions.py`
- Create: `tests/test_exceptions.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_exceptions.py
import pytest
from pythia.exceptions import ValidationError, NotFoundError, PythiaException


def test_validation_error_status_code():
    err = ValidationError("campo inválido")
    assert err.status_code == 400


def test_validation_error_message():
    err = ValidationError("campo inválido")
    assert err.message == "campo inválido"


def test_not_found_error_status_code():
    err = NotFoundError("recurso não encontrado")
    assert err.status_code == 404


def test_not_found_error_message():
    err = NotFoundError("recurso não encontrado")
    assert err.message == "recurso não encontrado"


def test_validation_error_is_pythia_exception():
    assert issubclass(ValidationError, PythiaException)


def test_not_found_error_is_pythia_exception():
    assert issubclass(NotFoundError, PythiaException)


def test_exceptions_are_raiseable():
    with pytest.raises(ValidationError) as exc_info:
        raise ValidationError("erro de validação")
    assert exc_info.value.status_code == 400
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_exceptions.py -v
```

Expected: `ImportError` ou `ModuleNotFoundError`.

- [ ] **Step 3: Implementar pythia/exceptions.py**

```python
class PythiaException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationError(PythiaException):
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class NotFoundError(PythiaException):
    def __init__(self, message: str):
        super().__init__(message, status_code=404)
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_exceptions.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pythia/exceptions.py tests/test_exceptions.py
git commit -m "feat: add exceptions (ValidationError, NotFoundError)"
```

---

## Task 3: Logger

**Files:**
- Create: `pythia/logging.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_logger.py
import logging
from pythia.logging import Logger


def test_logger_instantiation():
    logger = Logger(__name__)
    assert logger is not None


def test_logger_has_info_method():
    logger = Logger(__name__)
    assert callable(logger.info)


def test_logger_has_warning_method():
    logger = Logger(__name__)
    assert callable(logger.warning)


def test_logger_has_error_method():
    logger = Logger(__name__)
    assert callable(logger.error)


def test_logger_has_debug_method():
    logger = Logger(__name__)
    assert callable(logger.debug)


def test_logger_does_not_raise_on_use(caplog):
    logger = Logger("test.logger")
    with caplog.at_level(logging.INFO, logger="test.logger"):
        logger.info("mensagem de teste")
    assert "mensagem de teste" in caplog.text


def test_logger_default_level_is_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logger = Logger("test.level")
    assert logger._logger.level == logging.INFO
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_logger.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implementar pythia/logging.py**

```python
import logging
import os


class Logger:
    def __init__(self, name: str):
        level_name = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)

        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)

        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s — %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_logger.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pythia/logging.py tests/test_logger.py
git commit -m "feat: add Logger class"
```

---

## Task 4: DataSource

**Files:**
- Create: `pythia/datasource.py`
- Create: `tests/test_datasource.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_datasource.py
import pytest
from pythia.datasource import DataSource


def test_valid_datasource_subclass():
    class MyDataSource(DataSource):
        pass
    assert issubclass(MyDataSource, DataSource)


def test_datasource_suffix_enforced():
    with pytest.raises(TypeError, match="DataSource"):
        class InvalidName(DataSource):
            pass


def test_datasource_is_abstract():
    with pytest.raises(TypeError):
        DataSource()


def test_datasource_can_be_instantiated_via_subclass():
    class ValidDataSource(DataSource):
        def __init__(self):
            self.connected = True

    ds = ValidDataSource()
    assert ds.connected is True
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_datasource.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implementar pythia/datasource.py**

```python
from abc import ABC


class DataSource(ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("DataSource"):
            raise TypeError(
                f"Subclasses de DataSource devem terminar com 'DataSource' "
                f"(encontrado: '{cls.__name__}'). Renomeie para '{cls.__name__}DataSource'."
            )
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_datasource.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pythia/datasource.py tests/test_datasource.py
git commit -m "feat: add DataSource base class"
```

---

## Task 5: Entity

**Files:**
- Create: `pythia/entity.py`
- Create: `tests/test_entity.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_entity.py
import pytest
from pythia.entity import Entity


def test_valid_entity_subclass():
    class PersonEntity(Entity):
        name: str
        age: int

    p = PersonEntity(name="Jorge", age=30)
    assert p.name == "Jorge"
    assert p.age == 30


def test_entity_suffix_enforced():
    with pytest.raises(TypeError, match="Entity"):
        class InvalidName(Entity):
            name: str


def test_entity_is_pydantic():
    class ProductEntity(Entity):
        price: float

    with pytest.raises(Exception):
        ProductEntity(price="nao_e_numero")


def test_entity_serializes_to_dict():
    class ItemEntity(Entity):
        id: int
        label: str

    item = ItemEntity(id=1, label="test")
    data = item.model_dump()
    assert data == {"id": 1, "label": "test"}
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_entity.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implementar pythia/entity.py**

```python
from pydantic import BaseModel


class Entity(BaseModel):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Entity"):
            raise TypeError(
                f"Subclasses de Entity devem terminar com 'Entity' "
                f"(encontrado: '{cls.__name__}'). Renomeie para '{cls.__name__}Entity'."
            )
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_entity.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pythia/entity.py tests/test_entity.py
git commit -m "feat: add Entity base class (Pydantic)"
```

---

## Task 6: Repository

**Files:**
- Create: `pythia/repository.py`
- Create: `tests/test_repository.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_repository.py
import pytest
from pythia.repository import Repository
from pythia.datasource import DataSource


class FakeDataSource(DataSource):
    pass


class ClientRepository(Repository):
    data_bank = FakeDataSource()

    def get(self, **kwargs):
        return {"id": 1}


def test_valid_repository():
    repo = ClientRepository()
    assert repo is not None


def test_repository_get_returns_data():
    repo = ClientRepository()
    assert repo.get() == {"id": 1}


def test_repository_suffix_enforced():
    with pytest.raises(TypeError, match="Repository"):
        class InvalidName(Repository):
            data_bank = FakeDataSource()
            def get(self, **kwargs):
                pass


def test_repository_requires_data_bank():
    class NoDataBankRepository(Repository):
        def get(self, **kwargs):
            pass

    with pytest.raises(ValueError, match="data_bank"):
        NoDataBankRepository()


def test_repository_requires_datasource_instance():
    class BadDataBankRepository(Repository):
        data_bank = "nao_e_datasource"
        def get(self, **kwargs):
            pass

    with pytest.raises(ValueError, match="DataSource"):
        BadDataBankRepository()


def test_repository_get_is_abstract():
    class AbstractRepository(Repository):
        data_bank = FakeDataSource()

    with pytest.raises(TypeError):
        AbstractRepository()
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_repository.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implementar pythia/repository.py**

```python
from abc import ABC, abstractmethod
from pythia.datasource import DataSource


class Repository(ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Repository"):
            raise TypeError(
                f"Subclasses de Repository devem terminar com 'Repository' "
                f"(encontrado: '{cls.__name__}'). Renomeie para '{cls.__name__}Repository'."
            )

    def __init__(self):
        data_bank = getattr(self, "data_bank", None)
        if not data_bank:
            raise ValueError(f"{self.__class__.__name__}: data_bank is required")
        if not isinstance(data_bank, DataSource):
            raise ValueError(
                f"{self.__class__.__name__}: data_bank must be a DataSource instance"
            )

    @abstractmethod
    def get(self, **kwargs):
        pass
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_repository.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pythia/repository.py tests/test_repository.py
git commit -m "feat: add Repository base class"
```

---

## Task 7: Server

**Files:**
- Create: `pythia/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_server.py
import pytest
from pythia.server import Server


def test_server_is_singleton():
    s1 = Server.get_instance()
    s2 = Server.get_instance()
    assert s1 is s2


def test_server_has_flask_app():
    server = Server.get_instance()
    assert server.app is not None


def test_health_endpoint_returns_200():
    server = Server.get_instance()
    client = server.app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"


def test_mcp_tools_endpoint_returns_empty_list():
    server = Server.get_instance()
    client = server.app.test_client()
    response = client.get("/mcp/tools")
    assert response.status_code == 200
    data = response.get_json()
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
    client = server.app.test_client()
    response = client.get("/mcp/tools")
    tools = response.get_json()["tools"]
    assert any(t["name"] == "my_tool" for t in tools)


def test_server_reset_clears_instance():
    s1 = Server.get_instance()
    Server._reset()
    s2 = Server.get_instance()
    assert s1 is not s2
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_server.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implementar pythia/server.py**

```python
import datetime as dt
import os
from typing import Any, List, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS


def _validate_api_key(raw_key: str) -> bool:
    env_keys = os.getenv("AUTH_API_KEY", "")
    return bool(raw_key) and raw_key in [k.strip() for k in env_keys.split(",") if k.strip()]


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

        self.app = Flask(__name__)
        CORS(self.app)
        self.url_handlers: List = []

        @self.app.before_request
        def check_auth():
            if not os.getenv("AUTH_API_KEY"):
                return
            if request.endpoint in ("health_check", "list_tools"):
                return
            auth_header = request.headers.get("Authorization")
            api_key = None
            if auth_header and auth_header.startswith("Bearer "):
                api_key = auth_header.split(" ")[1]
            if not api_key or not _validate_api_key(api_key):
                return jsonify({"error": "Unauthorized"}), 401

        self._setup_default_routes()
        self._initialized = True

    def _setup_default_routes(self):
        @self.app.route("/mcp/tools", methods=["GET"])
        def list_tools():
            return jsonify({
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
            })

        @self.app.route("/health", methods=["GET"])
        def health_check():
            return jsonify({
                "status": "healthy",
                "timestamp": dt.datetime.utcnow().isoformat(),
            })

    def register_url_handler(self, handler: Any):
        self.url_handlers.append(handler)

    def start(self, host: str = "0.0.0.0", port: int = 5000, debug: bool = True):
        self.app.run(host=host, port=port, debug=debug)

    def get_mcp(self):
        from fastmcp import FastMCP
        from pydantic import Field, create_model
        from typing import List, Optional
        import inspect

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

        def tool_wrapper(args: ModelClass) -> dict:  # type: ignore
            return handler.callback(**args.model_dump())

        tool_wrapper.__name__ = name
        tool_wrapper.__doc__ = description
        sig = inspect.signature(tool_wrapper)
        new_param = inspect.Parameter(
            "args", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ModelClass
        )
        tool_wrapper.__signature__ = sig.replace(parameters=(new_param,))  # type: ignore
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

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_server.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pythia/server.py tests/test_server.py
git commit -m "feat: add Server singleton (Flask + FastMCP dual-mode)"
```

---

## Task 8: Endpoint

**Files:**
- Create: `pythia/endpoint.py`
- Create: `tests/test_endpoint.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_endpoint.py
import pytest
from pythia.endpoint import Endpoint
from pythia.server import Server
from pythia.exceptions import ValidationError, NotFoundError


def make_endpoint():
    class GetItemEndpoint(Endpoint):
        mcp_definition = {
            "name": "get_item",
            "description": "Retorna um item",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/get-item"
        method = "POST"

        def callback(self, item_id: str):
            return {"id": item_id, "name": "Test Item"}

    return GetItemEndpoint()


def test_endpoint_suffix_enforced():
    with pytest.raises(TypeError, match="Endpoint"):
        class GetItem(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
            def callback(self): pass


def test_endpoint_requires_mcp_definition():
    with pytest.raises(ValueError, match="mcp_definition"):
        class NoDefEndpoint(Endpoint):
            url = "/x"
            method = "POST"
            def callback(self): pass
        NoDefEndpoint()


def test_endpoint_requires_url():
    with pytest.raises(ValueError, match="url"):
        class NoUrlEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            method = "POST"
            def callback(self): pass
        NoUrlEndpoint()


def test_endpoint_requires_method():
    with pytest.raises(ValueError, match="method"):
        class NoMethodEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            def callback(self): pass
        NoMethodEndpoint()


def test_endpoint_requires_callback():
    with pytest.raises(ValueError, match="callback"):
        class NoCallbackEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
        NoCallbackEndpoint()


def test_endpoint_registers_on_server():
    make_endpoint()
    server = Server.get_instance()
    assert any(h.mcp_definition["name"] == "get_item" for h in server.url_handlers)


def test_endpoint_callback_success():
    make_endpoint()
    server = Server.get_instance()
    client = server.app.test_client()
    response = client.post("/api/get-item", json={"item_id": "42"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["result"]["id"] == "42"


def test_endpoint_callback_invalid_param():
    make_endpoint()
    server = Server.get_instance()
    client = server.app.test_client()
    response = client.post("/api/get-item", json={"unknown_param": "val"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error_type"] == "ValidationError"


def test_endpoint_callback_validation_error_from_callback():
    class RaisingEndpoint(Endpoint):
        mcp_definition = {
            "name": "raising_tool",
            "description": "raises",
            "parameters": {"properties": {}},
        }
        url = "/api/raising"
        method = "POST"

        def callback(self):
            raise ValidationError("algo inválido")

    RaisingEndpoint()
    server = Server.get_instance()
    client = server.app.test_client()
    response = client.post("/api/raising", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_endpoint_callback_not_found_error():
    class NotFoundEndpoint(Endpoint):
        mcp_definition = {
            "name": "notfound_tool",
            "description": "404",
            "parameters": {"properties": {}},
        }
        url = "/api/notfound"
        method = "POST"

        def callback(self):
            raise NotFoundError("não encontrado")

    NotFoundEndpoint()
    server = Server.get_instance()
    client = server.app.test_client()
    response = client.post("/api/notfound", json={})
    assert response.status_code == 404


def test_endpoint_callback_internal_error():
    class BoomEndpoint(Endpoint):
        mcp_definition = {
            "name": "boom_tool",
            "description": "explode",
            "parameters": {"properties": {}},
        }
        url = "/api/boom"
        method = "POST"

        def callback(self):
            raise RuntimeError("explosão inesperada")

    BoomEndpoint()
    server = Server.get_instance()
    client = server.app.test_client()
    response = client.post("/api/boom", json={})
    assert response.status_code == 500
    assert response.get_json()["error_type"] == "InternalServerError"
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_endpoint.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implementar pythia/endpoint.py**

```python
import datetime as dt
from abc import ABC

from flask import jsonify, request

from pythia.exceptions import PythiaException, ValidationError


class Endpoint(ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Endpoint"):
            raise TypeError(
                f"Subclasses de Endpoint devem terminar com 'Endpoint' "
                f"(encontrado: '{cls.__name__}'). Renomeie para '{cls.__name__}Endpoint'."
            )

    def _callback(self, **kwargs):
        try:
            data = request.get_json() or {}
            valid_params = self.mcp_definition.get("parameters", {}).get("properties", {})
            parameters = {}

            for key, value in data.items():
                if key not in valid_params:
                    raise ValidationError(f"Invalid parameter: {key}")
                parameters[key] = value

            for key, value in parameters.items():
                if isinstance(value, str) and key == "reference_date":
                    try:
                        dt_parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                        parameters[key] = dt_parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
                    except ValueError:
                        raise ValidationError(f"Invalid date format for reference_date: {value}")

            result = self.callback(**parameters)
            return jsonify({
                "tool": self.mcp_definition["name"],
                "result": result,
                "success": True,
            })

        except PythiaException as e:
            return jsonify({
                "error": e.message,
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": e.__class__.__name__,
            }), e.status_code

        except Exception as e:
            return jsonify({
                "error": str(e),
                "tool": self.mcp_definition["name"],
                "success": False,
                "error_type": "InternalServerError",
            }), 500

    def __init__(self):
        from pythia.server import Server

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

        server = Server.get_instance()
        server.app.add_url_rule(
            self.url,
            self.mcp_definition["name"],
            self._callback,
            methods=[self.method],
        )
        server.register_url_handler(self)
```

- [ ] **Step 4: Rodar testes**

```bash
pytest tests/test_endpoint.py -v
```

Expected: 11 PASSED.

- [ ] **Step 5: Commit**

```bash
git add pythia/endpoint.py tests/test_endpoint.py
git commit -m "feat: add Endpoint base class with auto-registration"
```

---

## Task 9: __init__.py (exports públicos)

**Files:**
- Modify: `pythia/__init__.py`

- [ ] **Step 1: Implementar exports**

```python
# pythia/__init__.py
from pythia.datasource import DataSource
from pythia.entity import Entity
from pythia.repository import Repository
from pythia.endpoint import Endpoint
from pythia.server import Server
from pythia.logging import Logger
from pythia.exceptions import ValidationError, NotFoundError

__all__ = [
    "DataSource",
    "Entity",
    "Repository",
    "Endpoint",
    "Server",
    "Logger",
    "ValidationError",
    "NotFoundError",
]
```

- [ ] **Step 2: Verificar imports**

```bash
python -c "from pythia import DataSource, Entity, Repository, Endpoint, Server, Logger, ValidationError, NotFoundError; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Rodar todos os testes**

```bash
pytest tests/ -v
```

Expected: todos PASSED.

- [ ] **Step 4: Commit**

```bash
git add pythia/__init__.py
git commit -m "feat: expose public API from pythia root"
```

---

## Task 10: CLI — `pythia new`

**Files:**
- Create: `pythia/cli/__init__.py`
- Create: `pythia/cli/new.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Escrever testes falhando**

```python
# tests/test_cli.py
import os
import pytest
from click.testing import CliRunner
from pythia.cli import app


@pytest.fixture
def runner():
    return CliRunner()


def test_new_creates_directory(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["new", "meu-server"])
        assert result.exit_code == 0
        assert os.path.isdir("meu-server")


def test_new_creates_expected_dirs(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        for d in ["datasource", "models", "repositories", "services", "tools", "urls"]:
            assert os.path.isdir(f"meu-server/{d}"), f"Missing dir: {d}"


def test_new_creates_init_files(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        for d in ["datasource", "models", "repositories", "services", "tools", "urls"]:
            assert os.path.isfile(f"meu-server/{d}/__init__.py"), f"Missing __init__.py in {d}"


def test_new_creates_main_py(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        assert os.path.isfile("meu-server/main.py")
        content = open("meu-server/main.py").read()
        assert "Server" in content
        assert "import urls" in content


def test_new_creates_pyproject_toml(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        assert os.path.isfile("meu-server/pyproject.toml")
        content = open("meu-server/pyproject.toml").read()
        assert "meu-server" in content


def test_new_fails_if_directory_exists(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        os.makedirs("meu-server")
        result = runner.invoke(app, ["new", "meu-server"])
        assert result.exit_code != 0
```

- [ ] **Step 2: Rodar para confirmar falha**

```bash
pytest tests/test_cli.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implementar pythia/cli/new.py**

```python
import os
import click

TEMPLATE_DIRS = ["datasource", "models", "repositories", "services", "tools", "urls"]

MAIN_PY = """\
from pythia import Server
import urls  # auto-discovery

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
"""

URLS_INIT = """\
# Auto-discovery: importe aqui cada módulo de endpoint
# Exemplo:
# from urls import get_client
"""

PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pythia",
]
"""


@click.command()
@click.argument("name")
def new_command(name: str):
    """Cria um novo MCP server com a estrutura pythia."""
    base = os.path.join(os.getcwd(), name)

    if os.path.exists(base):
        click.echo(f"Erro: diretório '{name}' já existe.", err=True)
        raise SystemExit(1)

    os.makedirs(base)

    for d in TEMPLATE_DIRS:
        os.makedirs(os.path.join(base, d))
        open(os.path.join(base, d, "__init__.py"), "w").close()

    with open(os.path.join(base, "urls", "__init__.py"), "w") as f:
        f.write(URLS_INIT)

    with open(os.path.join(base, "main.py"), "w") as f:
        f.write(MAIN_PY)

    with open(os.path.join(base, "pyproject.toml"), "w") as f:
        f.write(PYPROJECT.format(name=name))

    click.echo(f"Projeto '{name}' criado com sucesso.")
    click.echo(f"  cd {name} && pip install -e . && python main.py")
```

- [ ] **Step 4: Implementar pythia/cli/__init__.py**

```python
import click
from pythia.cli.new import new_command


@click.group()
def app():
    """pythia — framework para MCP servers."""
    pass


app.add_command(new_command, name="new")
```

- [ ] **Step 5: Rodar testes**

```bash
pytest tests/test_cli.py -v
```

Expected: 6 PASSED.

- [ ] **Step 6: Rodar suite completa**

```bash
pytest tests/ -v
```

Expected: todos PASSED.

- [ ] **Step 7: Verificar CLI funciona**

```bash
pythia new test-server && ls test-server/
```

Expected: `datasource  models  repositories  services  tools  urls  main.py  pyproject.toml`

```bash
rm -rf test-server
```

- [ ] **Step 8: Commit**

```bash
git add pythia/cli/ tests/test_cli.py
git commit -m "feat: add CLI — pythia new <nome>"
```

---

## Task 11: Verificação final

- [ ] **Step 1: Rodar suite completa com cobertura**

```bash
pytest tests/ -v --cov=pythia --cov-report=term-missing
```

Expected: todos PASSED, cobertura > 90%.

- [ ] **Step 2: Commit final**

```bash
git add .
git commit -m "chore: complete pythia v0.1.0"
```
