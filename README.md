# pythia

Framework Python para construção de MCP servers com arquitetura em camadas.

Pythia extrai e padroniza o padrão de projeto dos MCP servers `mcp-diagnosis-server` e `mcp-financial-server`, tornando-o reutilizável e testável via `pip install pythia`.

> O nome vem da Pítia — o oráculo de Delfos. MCP servers são oráculos: respondem perguntas de AI clients com dados estruturados.

---

## Instalação

```bash
pip install pythia
```

---

## Início rápido

```bash
# Cria um novo MCP server com toda a estrutura pronta
pythia new meu-server

cd meu-server
pip install -e .
python main.py
```

Estrutura gerada:

```
meu-server/
├── datasource/        # conexões com APIs e bancos de dados
├── models/            # entidades de domínio (Pydantic)
├── repositories/      # acesso a dados
├── services/          # lógica de negócio
├── tools/             # utilitários internos
├── urls/              # definição de endpoints (auto-discovery)
├── main.py
└── pyproject.toml
```

---

## Arquitetura

Pythia organiza o servidor em camadas com responsabilidades claras:

```
Endpoint  →  Service  →  Repository  →  DataSource
   ↑              ↑            ↑              ↑
HTTP route    negócio      acesso        conexão
```

Cada camada conhece apenas a camada imediatamente abaixo. O `Server` é o singleton que cola tudo.

---

## Classes base

### `DataSource`

Abstrai a conexão com uma fonte de dados externa (API REST, banco de dados, arquivo, etc.).

**Regra:** o nome da classe deve terminar com `DataSource`.

```python
import os
import requests
from pythia import DataSource

class CropNetDataSource(DataSource):
    def __init__(self):
        self.base_url = os.getenv("CROPNET_URL")
        self.api_key  = os.getenv("CROPNET_API_KEY")

    def get(self, path: str, **params) -> dict:
        response = requests.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params=params,
        )
        response.raise_for_status()
        return response.json()
```

> **Thread safety:** o DataSource é responsável pelo próprio estado de conexão. Clientes HTTP e connection pools (SQLAlchemy, pymongo) são thread-safe por design — compartilhá-los via `copy.copy` é seguro e esperado.

---

### `Entity`

Dado estruturado do domínio. Pydantic `BaseModel` por baixo — validação automática de tipos.

**Regra:** o nome da classe deve terminar com `Entity`.

```python
from pythia import Entity

class ClientEntity(Entity):
    id:   str
    name: str
    cnpj: str

class BatteryEntity(Entity):
    client_id:   str
    level:       float
    last_charge: str | None = None
```

```python
# Uso
client = ClientEntity(id="123", name="Fazenda Boa Vista", cnpj="12.345.678/0001-90")
print(client.model_dump())
# {'id': '123', 'name': 'Fazenda Boa Vista', 'cnpj': '12.345.678/0001-90'}
```

---

### `Repository`

Acessa dados via `DataSource` e retorna `Entity`s. Uma responsabilidade por Repository: uma fonte, um tipo de dado.

**Regras:**
- O nome da classe deve terminar com `Repository`.
- Deve definir `data_source` como atributo de classe (instância de `DataSource`).
- Deve implementar o método `get(**kwargs)`.

```python
from pythia import Repository
from datasource.cropnet import CropNetDataSource
from models.client import ClientEntity

class ClientRepository(Repository):
    data_source = CropNetDataSource()

    def get(self, client_id: str) -> ClientEntity:
        raw = self.data_source.get(f"/clients/{client_id}")
        return ClientEntity(**raw)
```

**Injeção de dependência para testes:**

```python
# Produção — usa o CropNetDataSource padrão
repo = ClientRepository()

# Teste — substitui o DataSource sem alterar a classe
repo = ClientRepository(data_source=MockDataSource())
```

A injeção funciona porque o `Repository.__init__` aceita `data_source` opcional. Se não fornecido, usa `copy.copy()` do atributo de classe — garantindo isolamento entre instâncias.

---

### `Service`

Orquestra a lógica de negócio. É aqui que ocorrem joins, transformações e regras que envolvem mais de uma fonte de dados.

**Regras:**
- O nome da classe deve terminar com `Service`.
- Atributos de classe do tipo `Repository` são descobertos automaticamente e isolados por instância via `copy.copy`.
- Aceita overrides de repositories via `**kwargs` no construtor.

```python
from pythia import Service
from repositories.client    import ClientRepository
from repositories.financial import FinancialRepository

class ClientSummaryService(Service):
    client_repo    = ClientRepository()
    financial_repo = FinancialRepository()

    def execute(self, client_id: str) -> dict:
        client    = self.client_repo.get(client_id=client_id)
        financial = self.financial_repo.get(client_id=client_id)

        return {
            **client.model_dump(),
            "balance":      financial.balance,
            "last_payment": financial.last_payment,
        }
```

**Injeção de dependência para testes:**

```python
# Produção
result = ClientSummaryService().execute(client_id="123")

# Teste — substitui apenas o repo financeiro
result = ClientSummaryService(
    financial_repo=MockFinancialRepository()
).execute(client_id="123")
```

> **Onde fazer o join de dois bancos?** No `Service`. Cada `Repository` acessa um único `DataSource`. O `Service` chama os dois Repositories e une os dados em Python.

---

### `Endpoint`

Rota HTTP que auto-registra no `Server` singleton ao ser instanciada. Valida parâmetros, delega para o callback e retorna JSON padronizado.

**Regras:**
- O nome da classe deve terminar com `Endpoint`.
- Deve definir `mcp_definition`, `url`, `method` e `callback`.

```python
from pythia import Endpoint
from services.client_summary import ClientSummaryService

class GetClientSummaryEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_client_summary",
        "description": "Retorna dados consolidados de um cliente",
        "parameters": {
            "properties": {
                "client_id": {
                    "type":        "string",
                    "description": "ID do cliente",
                },
            },
        },
    }
    url    = "/api/get-client-summary"
    method = "POST"

    def callback(self, client_id: str) -> dict:
        return ClientSummaryService().execute(client_id)
```

**Resposta de sucesso:**

```json
{
  "tool":    "get_client_summary",
  "result":  { ... },
  "success": true
}
```

**Resposta de erro (ValidationError → 400, NotFoundError → 404):**

```json
{
  "tool":       "get_client_summary",
  "error":      "client_id is required",
  "error_type": "ValidationError",
  "success":    false
}
```

---

### `Server`

Singleton Flask com dual-mode: HTTP direto ou protocolo MCP via FastMCP.

```python
from pythia import Server
import urls  # importar os módulos de urls dispara o __init__ dos Endpoints

server = Server.get_instance()

# Modo HTTP (desenvolvimento / produção direta)
if __name__ == "__main__":
    server.start(host="0.0.0.0", port=5000)
```

```python
# Modo FastMCP (protocolo MCP para AI clients)
mcp = server.get_mcp()
```

**Endpoints padrão:**

| Rota | Método | Descrição |
|------|--------|-----------|
| `/health` | GET | Status do servidor |
| `/mcp/tools` | GET | Lista todas as ferramentas registradas |

**Autenticação via variável de ambiente:**

```bash
AUTH_API_KEY=minha-chave python main.py
```

Toda rota (exceto `/health` e `/mcp/tools`) exige `Authorization: Bearer <chave>`.

---

### `Logger`

Wrapper sobre o `logging` padrão com formatação consistente.

```python
from pythia import Logger

logger = Logger(__name__)

logger.info("Servidor iniciado")
logger.warning("DataSource lento: %.2fs", elapsed)
logger.error("Falha ao conectar: %s", err)
logger.debug("Payload recebido: %s", payload)
```

Saída:

```
[2026-06-07 10:30:00] INFO datasource.cropnet — Servidor iniciado
```

**Nível configurável via variável de ambiente:**

```bash
LOG_LEVEL=DEBUG python main.py   # DEBUG | INFO | WARNING | ERROR
```

---

### Exceptions

Importadas direto de `pythia`. O `Endpoint` as captura automaticamente e converte em resposta HTTP.

```python
from pythia import ValidationError, NotFoundError

# 400 Bad Request
raise ValidationError("client_id é obrigatório")

# 404 Not Found
raise NotFoundError("Cliente não encontrado")
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
│   └── cropnet.py       # CropNetDataSource
├── models/
│   └── client.py        # ClientEntity
├── repositories/
│   └── client.py        # ClientRepository
├── services/
│   └── client.py        # GetClientService
├── urls/
│   ├── __init__.py      # importa get_client
│   └── get_client.py    # GetClientEndpoint
└── main.py
```

**`datasource/cropnet.py`**
```python
import os
import requests
from pythia import DataSource

class CropNetDataSource(DataSource):
    def __init__(self):
        self.base_url = os.getenv("CROPNET_URL")

    def fetch(self, client_id: str) -> dict:
        r = requests.get(f"{self.base_url}/clients/{client_id}")
        r.raise_for_status()
        return r.json()
```

**`models/client.py`**
```python
from pythia import Entity

class ClientEntity(Entity):
    id:   str
    name: str
    cnpj: str
```

**`repositories/client.py`**
```python
from pythia import Repository
from datasource.cropnet import CropNetDataSource
from models.client import ClientEntity

class ClientRepository(Repository):
    data_source = CropNetDataSource()

    def get(self, client_id: str) -> ClientEntity:
        return ClientEntity(**self.data_source.fetch(client_id))
```

**`services/client.py`**
```python
from pythia import NotFoundError, Service
from repositories.client import ClientRepository

class GetClientService(Service):
    repo = ClientRepository()

    def execute(self, client_id: str) -> dict:
        client = self.repo.get(client_id=client_id)
        if not client:
            raise NotFoundError(f"Client {client_id} not found")
        return client.model_dump()
```

**`urls/get_client.py`**
```python
from pythia import Endpoint
from services.client import GetClientService

class GetClientEndpoint(Endpoint):
    mcp_definition = {
        "name":        "get_client",
        "description": "Retorna dados de um cliente pelo ID",
        "parameters": {
            "properties": {
                "client_id": {"type": "string", "description": "ID do cliente"},
            },
        },
    }
    url    = "/api/get-client"
    method = "POST"

    def callback(self, client_id: str) -> dict:
        return GetClientService().execute(client_id)

GetClientEndpoint()
```

**`urls/__init__.py`**
```python
from urls import get_client
```

**`main.py`**
```python
from pythia import Server
import urls

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
```

---

## Testando com injeção

```python
# tests/test_get_client.py
from services.client import GetClientService
from repositories.client import ClientRepository
from pythia import DataSource

class FakeDataSource(DataSource):
    def fetch(self, client_id: str) -> dict:
        return {"id": client_id, "name": "Fazenda Teste", "cnpj": "00.000.000/0001-00"}

class FakeClientRepository(ClientRepository):
    data_source = FakeDataSource()

def test_get_client_returns_correct_data():
    svc = GetClientService(repo=FakeClientRepository())
    result = svc.execute(client_id="123")
    assert result["name"] == "Fazenda Teste"
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
| `DataSource` | `*DataSource` | `CropNetDataSource` |
| `Entity` | `*Entity` | `ClientEntity` |
| `Repository` | `*Repository` | `ClientRepository` |
| `Service` | `*Service` | `GetClientService` |
| `Endpoint` | `*Endpoint` | `GetClientEndpoint` |

---

## Dependências

```toml
flask >= 2.0
flask-cors >= 4.0
fastmcp >= 2.0
pydantic >= 2.0
click >= 8.0
```
