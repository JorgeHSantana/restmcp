# pythia

Framework Python para construir servidores MCP con arquitectura en capas.

Pythia estandariza el patrón de MCP server en clases base reutilizables y una CLI de scaffolding, para que te concentres en la lógica de negocio en vez del boilerplate.

> El nombre viene de la Pitia — el oráculo de Delfos. Los MCP servers son oráculos: responden preguntas de AI clients con datos estructurados.

---

## Instalación

```bash
pip install pythia
```

---

## Inicio rápido

```bash
pythia new mi-servidor

cd mi-servidor
pip install -e .
python main.py
```

Estructura generada:

```
mi-servidor/
├── datasource/        # conexiones externas (APIs, bases de datos)
├── models/            # entidades de dominio (Pydantic)
├── repositories/      # capa de acceso a datos
├── services/          # lógica de negocio
├── tools/             # utilitarios internos
├── urls/              # definición de endpoints (auto-discovery)
├── main.py
└── pyproject.toml
```

---

## Arquitectura

```
Endpoint  →  Service  →  Repository  →  DataSource
   ↑              ↑            ↑              ↑
ruta HTTP     negocio       acceso        conexión
```

Cada capa conoce únicamente la capa directamente inferior. El singleton `Server` conecta todo.

---

## Clases base

### `DataSource`

Abstrae la conexión con una fuente de datos externa (API REST, base de datos, archivo, etc.).

**Regla:** el nombre de la clase debe terminar con `DataSource`.

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

> **Thread safety** es responsabilidad del DataSource. Los clientes HTTP y los connection pools (SQLAlchemy, pymongo) son thread-safe por diseño — compartirlos entre instancias vía `copy.copy` es correcto y esperado.

---

### `Entity`

Dato estructurado del dominio. Respaldado por Pydantic `BaseModel` — validación automática de tipos.

**Regla:** el nombre de la clase debe terminar con `Entity`.

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

Accede a datos vía `DataSource` y retorna objetos `Entity`. Una responsabilidad por Repository: una fuente, un tipo de dato.

**Reglas:**
- El nombre de la clase debe terminar con `Repository`.
- Debe declarar `data_source` como atributo de clase (instancia de `DataSource`).
- Debe implementar `get(**kwargs)`.

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

**Inyección de dependencias para tests:**

```python
# Producción — usa el DataSource real
repo = ProductRepository()

# Test — reemplaza el DataSource sin modificar la clase
repo = ProductRepository(data_source=MockDataSource())
```

La inyección funciona porque `Repository.__init__` acepta `data_source` opcional. Si no se provee, usa `copy.copy()` del atributo de clase — garantizando aislamiento entre instancias.

---

### `Service`

Orquesta la lógica de negocio. Aquí ocurren los joins, transformaciones y reglas que involucran más de una fuente de datos.

**Reglas:**
- El nombre de la clase debe terminar con `Service`.
- Atributos de clase del tipo `Repository` son descubiertos automáticamente y aislados por instancia vía `copy.copy`.
- Acepta overrides de repositories vía `**kwargs` en el constructor.

```python
from pythia import Service
from repositories.product   import ProductRepository
from repositories.inventory import InventoryRepository

class GetProductDetailsService(Service):
    product_repo   = ProductRepository()
    inventory_repo = InventoryRepository()

    def execute(self, product_id: str) -> dict:
        product   = self.product_repo.get(product_id=product_id)
        inventory = self.inventory_repo.get(product_id=product_id)

        return {
            **product.model_dump(),
            "stock":     inventory.quantity,
            "available": inventory.quantity > 0,
        }
```

**Inyección de dependencias para tests:**

```python
# Producción
result = GetProductDetailsService().execute(product_id="1")

# Test — reemplaza solo el repository de inventario
result = GetProductDetailsService(
    inventory_repo=MockInventoryRepository()
).execute(product_id="1")
```

> **¿Join de dos bases de datos?** Hazlo en el `Service`. Cada `Repository` accede a un único `DataSource`. El `Service` llama a ambos y une los datos en Python.

---

### `Endpoint`

Ruta HTTP que se auto-registra en el singleton `Server` en el momento en que se define la clase. Valida parámetros, delega al callback y retorna JSON estandarizado.

**Reglas:**
- El nombre de la clase debe terminar con `Endpoint`.
- Debe declarar `mcp_definition`, `url`, `method` y `callback`.

```python
from pythia import Endpoint
from services.product import GetProductDetailsService

class GetProductEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_product",
        "description": "Retorna detalles de un producto por ID",
        "parameters": {
            "properties": {
                "product_id": {
                    "type":        "string",
                    "description": "ID del producto",
                },
            },
        },
    }
    url    = "/api/get-product"
    method = "POST"

    def callback(self, product_id: str) -> dict:
        return GetProductDetailsService().execute(product_id)
```

> **Parámetros de path** usan sintaxis FastAPI: `url = "/clients/{client_id}"`. La sintaxis Flask `<int:client_id>` no funciona.

No es necesario instanciar — **definir la clase es suficiente**. En cuanto Python procesa el cuerpo de la `class`, la ruta queda registrada en el servidor.

**Deshabilitar un endpoint:**

```python
class GetProductEndpoint(Endpoint):
    disabled = True   # omite el auto-registro
    ...
```

Usa `disabled = True` para desactivar temporalmente un endpoint sin borrar el código. Puede seguir instanciándose manualmente si es necesario.

**Clases base abstractas** (sin `url`, `method`, `mcp_definition` o `callback`) nunca se auto-registran:

```python
class BaseAuthEndpoint(Endpoint):
    method = "POST"

    def callback(self, **kwargs):
        # lógica de autenticación compartida
        ...
# ↑ No registrada — faltan url y mcp_definition

class GetUserEndpoint(BaseAuthEndpoint):
    mcp_definition = { ... }
    url = "/api/get-user"
    # ↑ Registrada automáticamente — todos los atributos requeridos presentes
```

**Respuesta exitosa:**

```json
{
  "tool":    "get_product",
  "result":  { "id": "1", "name": "Widget", "price": 9.99, "stock": 42 },
  "success": true
}
```

**Respuesta de error (`ValidationError` → 400, `NotFoundError` → 404):**

```json
{
  "tool":       "get_product",
  "error":      "product_id es requerido",
  "error_type": "ValidationError",
  "success":    false
}
```

---

### `Server`

Singleton FastAPI con dual-mode: HTTP directo o protocolo MCP vía FastMCP. `server.start()` usa uvicorn internamente.

```python
from pythia import Server
import urls   # ejecuta urls/__init__.py → importa todos los módulos → registra todas las rutas

server = Server.get_instance()

if __name__ == "__main__":
    server.start(host="0.0.0.0", port=5000)
```

```python
# Modo MCP (para AI clients)
mcp = server.get_mcp()
```

**Rutas por defecto:**

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/health` | GET | Estado del servidor |
| `/mcp/tools` | GET | Lista todas las herramientas registradas |

**Autenticación vía variable de entorno:**

```bash
AUTH_API_KEY=mi-clave-secreta python main.py
```

Todas las rutas (excepto `/health` y `/mcp/tools`) requieren `Authorization: Bearer <clave>`. Se soportan múltiples claves separadas por coma.

---

### `Logger`

Wrapper sobre el `logging` estándar de Python con formato consistente.

```python
from pythia import Logger

logger = Logger(__name__)

logger.info("Servidor iniciado")
logger.warning("Respuesta lenta: %.2fs", elapsed)
logger.error("Fallo de conexión: %s", err)
logger.debug("Payload recibido: %s", payload)
```

Salida:

```
[2026-06-07 10:30:00] INFO datasource.product_api — Servidor iniciado
```

**Nivel de log vía variable de entorno:**

```bash
LOG_LEVEL=DEBUG python main.py   # DEBUG | INFO | WARNING | ERROR
```

---

### Exceptions

Importadas directamente desde `pythia`. El `Endpoint` las captura automáticamente y las convierte en respuesta HTTP.

```python
from pythia import ValidationError, NotFoundError

raise ValidationError("product_id es requerido")   # → HTTP 400
raise NotFoundError("Producto no encontrado")        # → HTTP 404
```

Jerarquía:

```
PythiaException          # base (no expuesta directamente)
├── ValidationError      # → HTTP 400
└── NotFoundError        # → HTTP 404
```

---

## Ejemplo completo

```
mi-servidor/
├── datasource/
│   └── product_api.py      # ProductApiDataSource
├── models/
│   └── product.py          # ProductEntity
├── repositories/
│   └── product.py          # ProductRepository
├── services/
│   └── product.py          # GetProductService
├── urls/
│   ├── __init__.py         # auto-scan de urls/ — nunca editar
│   └── get_product.py      # GetProductEndpoint — auto-registrada al importar
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
            raise NotFoundError(f"Producto {product_id} no encontrado")
        return product.model_dump()
```

**`urls/get_product.py`**
```python
from pythia import Endpoint
from services.product import GetProductService

class GetProductEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_product",
        "description": "Retorna un producto por ID",
        "parameters": {
            "properties": {
                "product_id": {"type": "string", "description": "ID del producto"},
            },
        },
    }
    url    = "/api/get-product"
    method = "POST"

    def callback(self, product_id: str) -> dict:
        return GetProductService().execute(product_id)

# No es necesario instanciar — definir la clase registra la ruta automáticamente.
```

**`urls/__init__.py`** — generado por el CLI, nunca se vuelve a editar
```python
import importlib
import pkgutil

for _info in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_info.name}")
```

**`main.py`**
```python
from pythia import Server
import urls   # dispara urls/__init__.py → importa todos los módulos → registra todos los endpoints

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
```

---

## Soporte Async

`callback` puede ser sync o async — pythia detecta y maneja ambos:

```python
# sync — se ejecuta en thread pool, no bloquea el event loop
def callback(self, client_id: int):
    return requests.get(f"https://api.ejemplo.com/clients/{client_id}").json()

# async — se awaita directamente
async def callback(self, client_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.ejemplo.com/clients/{client_id}")
        return response.json()
```

Usa callbacks sync para casos simples. Migra a async cuando necesites I/O concurrente dentro de una única solicitud (ej: llamar múltiples APIs en paralelo con `asyncio.gather`).

---

## Tests con inyección

```python
# tests/test_get_product.py
from services.product import GetProductService
from repositories.product import ProductRepository
from pythia import DataSource

class FakeProductApiDataSource(DataSource):
    def fetch(self, product_id: str) -> dict:
        return {"id": product_id, "name": "Widget de Prueba", "price": 1.99}

class FakeProductRepository(ProductRepository):
    data_source = FakeProductApiDataSource()

def test_get_product_retorna_datos_correctos():
    svc = GetProductService(repo=FakeProductRepository())
    result = svc.execute(product_id="1")
    assert result["name"] == "Widget de Prueba"
```

---

## Variables de entorno

| Variable | Valor por defecto | Descripción |
|----------|------------------|-------------|
| `AUTH_API_KEY` | _(desactivado)_ | Clave Bearer para autenticación. Múltiples claves separadas por coma. |
| `LOG_LEVEL` | `INFO` | Nivel de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Convención de nomenclatura

Todas las clases base exigen sufijo. Violarlo lanza `TypeError` en tiempo de import:

| Clase base | Sufijo requerido | Ejemplo |
|------------|-----------------|---------|
| `DataSource` | `*DataSource` | `ProductApiDataSource` |
| `Entity` | `*Entity` | `ProductEntity` |
| `Repository` | `*Repository` | `ProductRepository` |
| `Service` | `*Service` | `GetProductService` |
| `Endpoint` | `*Endpoint` | `GetProductEndpoint` |

---

## Dependencias

```toml
fastapi >= 0.100
uvicorn >= 0.20
fastmcp >= 2.0
pydantic >= 2.0
click >= 8.0
```
