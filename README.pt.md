# pythia

Framework Python para construção de MCP servers com arquitetura em camadas.

Pythia padroniza o padrão de MCP server em classes base reutilizáveis e uma CLI de scaffolding, para que você foque na lógica de negócio em vez do boilerplate.

> O nome vem da Pítia — o oráculo de Delfos. MCP servers são oráculos: respondem perguntas de AI clients com dados estruturados.

---

## Instalação

```bash
pip install pythia
```

---

## Início rápido

```bash
pythia new meu-server

cd meu-server
pip install -e .
python main.py
```

Estrutura gerada:

```
meu-server/
├── datasource/        # conexões externas (APIs, bancos de dados)
├── models/            # entidades de domínio (Pydantic)
├── repositories/      # camada de acesso a dados
├── services/          # lógica de negócio
├── tools/             # utilitários internos
├── urls/              # definição de endpoints (auto-discovery)
├── main.py
└── pyproject.toml
```

---

## Arquitetura

```
Endpoint  →  Service  →  Repository  →  DataSource
   ↑              ↑            ↑              ↑
rota HTTP     negócio      acesso        conexão
```

Cada camada conhece apenas a camada imediatamente abaixo. O `Server` singleton cola tudo.

---

## Classes base

### `DataSource`

Abstrai a conexão com uma fonte de dados externa (API REST, banco de dados, arquivo, etc.).

**Regra:** o nome da classe deve terminar com `DataSource`.

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

> **Thread safety** é responsabilidade do DataSource. Clientes HTTP e connection pools (SQLAlchemy, pymongo) são thread-safe por design — compartilhá-los entre instâncias via `copy.copy` é correto e esperado.

---

### `Entity`

Dado estruturado do domínio. Backed por Pydantic `BaseModel` — validação automática de tipos.

**Regra:** o nome da classe deve terminar com `Entity`.

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

Acessa dados via `DataSource` e retorna objetos `Entity`. Uma responsabilidade por Repository: uma fonte, um tipo de dado.

**Regras:**
- O nome da classe deve terminar com `Repository`.
- Deve declarar `data_source` como atributo de classe (instância de `DataSource`).
- Deve implementar `get(**kwargs)`.

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

**Injeção de dependência para testes:**

```python
# Produção — usa o DataSource real
repo = ProductRepository()

# Teste — substitui o DataSource sem alterar a classe
repo = ProductRepository(data_source=MockDataSource())
```

A injeção funciona porque `Repository.__init__` aceita `data_source` opcional. Se não fornecido, usa `copy.copy()` do atributo de classe — garantindo isolamento entre instâncias.

---

### `Service`

Orquestra a lógica de negócio. É aqui que ocorrem joins, transformações e regras que envolvem mais de uma fonte de dados.

**Regras:**
- O nome da classe deve terminar com `Service`.
- Atributos de classe do tipo `Repository` são descobertos automaticamente e isolados por instância via `copy.copy`.
- Aceita overrides de repositories via `**kwargs` no construtor.

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

**Injeção de dependência para testes:**

```python
# Produção
result = GetProductDetailsService().execute(product_id="1")

# Teste — substitui apenas o repository de inventário
result = GetProductDetailsService(
    inventory_repo=MockInventoryRepository()
).execute(product_id="1")
```

> **Join de dois bancos de dados?** Faça no `Service`. Cada `Repository` acessa um único `DataSource`. O `Service` chama os dois e une os dados em Python.

---

### `Endpoint`

Rota HTTP que auto-registra no singleton `Server` no momento em que a classe é definida. Valida parâmetros, delega ao callback e retorna JSON padronizado.

**Regras:**
- O nome da classe deve terminar com `Endpoint`.
- Deve declarar `mcp_definition`, `url`, `method` e `callback`.

```python
from pythia import Endpoint
from services.product import GetProductDetailsService

class GetProductEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_product",
        "description": "Retorna detalhes de um produto pelo ID",
        "parameters": {
            "properties": {
                "product_id": {
                    "type":        "string",
                    "description": "ID do produto",
                },
            },
        },
    }
    url    = "/api/get-product"
    method = "POST"

    def callback(self, product_id: str) -> dict:
        return GetProductDetailsService().execute(product_id)
```

Nenhuma instanciação necessária — **definir a classe já é suficiente**. Assim que Python processa o corpo da `class`, a rota é registrada no servidor.

**Desabilitando um endpoint:**

```python
class GetProductEndpoint(Endpoint):
    disabled = True   # pula o auto-registro
    ...
```

Use `disabled = True` para desativar temporariamente um endpoint sem apagar o código. Ainda pode ser instanciado manualmente se necessário.

**Classes base abstratas** (sem `url`, `method`, `mcp_definition` ou `callback`) nunca são auto-registradas:

```python
class BaseAuthEndpoint(Endpoint):
    method = "POST"

    def callback(self, **kwargs):
        # lógica de autenticação compartilhada
        ...
# ↑ Não registrada — url e mcp_definition ausentes

class GetUserEndpoint(BaseAuthEndpoint):
    mcp_definition = { ... }
    url = "/api/get-user"
    # ↑ Registrada automaticamente — todos os atributos obrigatórios presentes
```

**Resposta de sucesso:**

```json
{
  "tool":    "get_product",
  "result":  { "id": "1", "name": "Widget", "price": 9.99, "stock": 42 },
  "success": true
}
```

**Resposta de erro (`ValidationError` → 400, `NotFoundError` → 404):**

```json
{
  "tool":       "get_product",
  "error":      "product_id é obrigatório",
  "error_type": "ValidationError",
  "success":    false
}
```

---

### `Server`

Singleton Flask com dual-mode: HTTP direto ou protocolo MCP via FastMCP.

```python
from pythia import Server
import urls   # executa urls/__init__.py → importa todos os módulos → registra todas as rotas

server = Server.get_instance()

if __name__ == "__main__":
    server.start(host="0.0.0.0", port=5000)
```

```python
# Modo MCP (para AI clients)
mcp = server.get_mcp()
```

**Rotas padrão:**

| Rota | Método | Descrição |
|------|--------|-----------|
| `/health` | GET | Status do servidor |
| `/mcp/tools` | GET | Lista todas as ferramentas registradas |

**Autenticação via variável de ambiente:**

```bash
AUTH_API_KEY=minha-chave python main.py
```

Todas as rotas (exceto `/health` e `/mcp/tools`) exigem `Authorization: Bearer <chave>`. Múltiplas chaves suportadas, separadas por vírgula.

---

### `Logger`

Wrapper sobre o `logging` padrão com formatação consistente.

```python
from pythia import Logger

logger = Logger(__name__)

logger.info("Servidor iniciado")
logger.warning("Resposta lenta: %.2fs", elapsed)
logger.error("Falha na conexão: %s", err)
logger.debug("Payload recebido: %s", payload)
```

Saída:

```
[2026-06-07 10:30:00] INFO datasource.product_api — Servidor iniciado
```

**Nível de log via variável de ambiente:**

```bash
LOG_LEVEL=DEBUG python main.py   # DEBUG | INFO | WARNING | ERROR
```

---

### Exceptions

Importadas direto de `pythia`. O `Endpoint` as captura automaticamente e converte em resposta HTTP.

```python
from pythia import ValidationError, NotFoundError

raise ValidationError("product_id é obrigatório")   # → HTTP 400
raise NotFoundError("Produto não encontrado")         # → HTTP 404
```

Hierarquia:

```
PythiaException          # base (não exposta diretamente)
├── ValidationError      # → HTTP 400
└── NotFoundError        # → HTTP 404
```

---

## Exemplo completo

```
meu-server/
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
│   └── get_product.py      # GetProductEndpoint — auto-registrada no import
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
            raise NotFoundError(f"Produto {product_id} não encontrado")
        return product.model_dump()
```

**`urls/get_product.py`**
```python
from pythia import Endpoint
from services.product import GetProductService

class GetProductEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_product",
        "description": "Retorna um produto pelo ID",
        "parameters": {
            "properties": {
                "product_id": {"type": "string", "description": "ID do produto"},
            },
        },
    }
    url    = "/api/get-product"
    method = "POST"

    def callback(self, product_id: str) -> dict:
        return GetProductService().execute(product_id)

# Nenhuma instanciação necessária — definir a classe registra a rota automaticamente.
```

**`urls/__init__.py`** — gerado pelo CLI, nunca mais editado
```python
import importlib
import pkgutil

for _info in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_info.name}")
```

**`main.py`**
```python
from pythia import Server
import urls   # dispara urls/__init__.py → importa todos os módulos → registra todos os endpoints

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
```

---

## Testando com injeção

```python
# tests/test_get_product.py
from services.product import GetProductService
from repositories.product import ProductRepository
from pythia import DataSource

class FakeProductApiDataSource(DataSource):
    def fetch(self, product_id: str) -> dict:
        return {"id": product_id, "name": "Widget de Teste", "price": 1.99}

class FakeProductRepository(ProductRepository):
    data_source = FakeProductApiDataSource()

def test_get_product_retorna_dados_corretos():
    svc = GetProductService(repo=FakeProductRepository())
    result = svc.execute(product_id="1")
    assert result["name"] == "Widget de Teste"
```

---

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `AUTH_API_KEY` | _(desativado)_ | Chave Bearer para autenticação. Múltiplas chaves separadas por vírgula. |
| `LOG_LEVEL` | `INFO` | Nível de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Convenção de nomenclatura

Todas as classes base exigem sufixo. A violação causa `TypeError` em tempo de import:

| Classe base | Sufixo obrigatório | Exemplo |
|-------------|-------------------|---------|
| `DataSource` | `*DataSource` | `ProductApiDataSource` |
| `Entity` | `*Entity` | `ProductEntity` |
| `Repository` | `*Repository` | `ProductRepository` |
| `Service` | `*Service` | `GetProductService` |
| `Endpoint` | `*Endpoint` | `GetProductEndpoint` |

---

## Dependências

```toml
flask >= 2.0
flask-cors >= 4.0
fastmcp >= 2.0
pydantic >= 2.0
click >= 8.0
```
