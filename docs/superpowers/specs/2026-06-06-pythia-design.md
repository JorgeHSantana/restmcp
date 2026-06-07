# pythia — Design Spec

**Data:** 2026-06-06  
**Status:** Aprovado

---

## Contexto

`pythia` é um framework Python para construção de MCP servers com arquitetura em camadas. Extrai e generaliza o padrão de projeto dos projetos `mcp-diagnosis-server` e `mcp-financial-server`, tornando-o reutilizável via `pip install pythia`.

O nome vem da Pítia — o oráculo de Delfos. MCP servers são oráculos: respondem perguntas de AI clients com dados estruturados.

---

## Objetivo

Permitir criar um novo MCP server em segundos:

```bash
pip install pythia
pythia new meu-server
```

E ter toda a infraestrutura pronta, bastando implementar as camadas de negócio.

---

## Abordagem escolhida

**Classes base + CLI de scaffolding** (opção B de 3 avaliadas).

- Core obrigatório: `Endpoint`, `Server`, `exceptions`, `logging`
- Camada de dados opcional mas oferecida: `Repository`, `DataSource`, `Entity`
- CLI gera estrutura completa de pastas e arquivos base
- Flask + FastMCP como dependências hard (dual-mode)

---

## Arquitetura do pacote

```
pythia/
├── pythia/
│   ├── __init__.py       # exports: Endpoint, Server, Repository, DataSource, Entity, Logger, ValidationError, NotFoundError
│   ├── server.py         # Server singleton — Flask + FastMCP dual-mode
│   ├── endpoint.py       # Endpoint ABC — auto-registro + sufixo forçado
│   ├── repository.py     # Repository ABC — sufixo forçado
│   ├── datasource.py     # DataSource ABC — sufixo forçado
│   ├── entity.py         # Entity (Pydantic BaseModel) — sufixo forçado
│   ├── exceptions.py     # PythiaException, ValidationError, NotFoundError
│   ├── logging.py        # Logger — stdlib logging configurado
│   └── cli/
│       ├── __init__.py
│       └── new.py        # pythia new <nome>
├── pyproject.toml
└── README.md
```

---

## Interface do desenvolvedor

### DataSource
Abstrai a fonte de dados (API, banco, etc). Sufixo `*DataSource` obrigatório.

```python
from pythia import DataSource

class CropNetDataSource(DataSource):
    def __init__(self):
        self.base_url = os.getenv("CROPNET_URL")
```

### Entity
Dado estruturado do domínio. Pydantic BaseModel por baixo. Sufixo `*Entity` obrigatório.

```python
from pythia import Entity

class ClientEntity(Entity):
    id: str
    name: str
    cnpj: str
```

### Repository
Acesso aos dados via DataSource. Sufixo `*Repository` obrigatório.

```python
from pythia import Repository

class ClientRepository(Repository):
    data_bank = CropNetDataSource()

    def get(self, client_id: str) -> ClientEntity:
        raw = self.data_bank.fetch(client_id)
        return ClientEntity(**raw)
```

### Endpoint
Rota HTTP auto-registrada no Server singleton. Valida parâmetros, chama callback, retorna JSON padronizado. Sufixo `*Endpoint` obrigatório.

```python
from pythia import Endpoint

class GetClientEndpoint(Endpoint):
    mcp_definition = {
        "name": "get_client",
        "description": "Retorna dados de um cliente pelo ID",
        "parameters": {
            "properties": {
                "client_id": {"type": "string", "description": "ID do cliente"}
            }
        },
    }
    url = "/api/get-client"
    method = "POST"

    def callback(self, client_id: str):
        return GetClientService(ClientRepository()).execute(client_id)
```

### main.py
```python
from pythia import Server
import urls  # auto-discovery registra todos os Endpoints

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
```

---

## Convenção de nomenclatura

Sufixo obrigatório em todas as classes base, enforçado via `__init_subclass__` (erro em tempo de import):

| Classe base | Sufixo | Exemplo |
|-------------|--------|---------|
| `Entity` | `*Entity` | `ClientEntity` |
| `Repository` | `*Repository` | `ClientRepository` |
| `DataSource` | `*DataSource` | `CropNetDataSource` |
| `Endpoint` | `*Endpoint` | `GetClientEndpoint` |

Decisão opinionada: consistência interna do framework > convenções externas. Permite grep e navegação sem ambiguidade.

---

## CLI — `pythia new <nome>`

Gera estrutura completa:

```
<nome>/
├── datasource/
│   └── __init__.py
├── models/
│   └── __init__.py
├── repositories/
│   └── __init__.py
├── services/
│   └── __init__.py
├── tools/
│   └── __init__.py
├── urls/
│   └── __init__.py       # auto-discovery: importa cada módulo de urls/ para disparar o __init__ dos Endpoints
├── main.py               # ponto de entrada
└── pyproject.toml
```

---

## Server — dual mode

```python
# Modo Flask (HTTP direto / desenvolvimento)
server = Server.get_instance()
server.start(host="0.0.0.0", port=5000)

# Modo FastMCP (protocolo MCP para AI clients)
mcp = server.get_mcp()
```

O `Server` traduz automaticamente os `Endpoint`s registrados para ferramentas FastMCP.

---

## Logging

```python
from pythia import Logger

logger = Logger(__name__)
logger.info("Iniciando servidor...")
```

- Usa stdlib `logging` — sem dependência extra
- Nível configurável via `LOG_LEVEL` env var (default: `INFO`)
- Formato consistente em todos os projetos que usarem pythia
- Server, Endpoint e erros já logam automaticamente

---

## Exceptions

Importadas direto de `pythia` — sem submódulo:

```python
from pythia import ValidationError, NotFoundError

raise ValidationError("client_id é obrigatório")
raise NotFoundError("Cliente não encontrado")
```

Hierarquia interna:

```
PythiaException          # base (não exposta diretamente)
├── ValidationError      # 400 — parâmetros inválidos
└── NotFoundError        # 404 — recurso não encontrado
```

Capturadas automaticamente pelo `Endpoint._callback` e convertidas em respostas JSON padronizadas.

---

## Dependências

```toml
[project]
dependencies = [
    "flask",
    "flask-cors",
    "fastmcp",
    "pydantic",
    "click",       # CLI
]
```

---

## Padrões de referência

- **Repository Pattern** — Martin Fowler, *Patterns of Enterprise Application Architecture* (2002)
- **DataSource Pattern** — mesmo livro
- **Service Layer** — mesmo livro
- **Convention over Configuration** — Ruby on Rails
- **`__init_subclass__` enforcement** — padrão já validado no `olympus-ai-server`
