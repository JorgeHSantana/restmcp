"""Issue #18 (parte 1) — `success_code`: o código de sucesso vira declaração.

O 200 estava cravado em dois lugares (a JSONResponse do caminho feliz e a chave
literal "200" do _openapi_responses); mudar um sem o outro produziria um OpenAPI
que discorda do servidor. O atributo declarativo alimenta os dois da mesma fonte,
no idioma da lib (expose/max_body_bytes/required_scope): validado no import,
default 200, nenhum endpoint existente muda.
"""
import pytest
from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.exceptions import ValidationError


def _start_run_endpoint():
    class StartRunEndpoint(Endpoint):
        success_code = 202
        mcp_definition = {
            "name": "start_run", "description": "dispara",
            "parameters": {"properties": {}},
        }
        url = "/api/runs"
        method = "POST"

        def callback(self):
            return {"run_id": "r-1"}
    return StartRunEndpoint


def test_202_na_resposta_e_no_openapi():
    """A mesma declaração alimenta a resposta E o documento — não podem divergir."""
    server = Server.get_instance()
    _start_run_endpoint()
    with TestClient(server.app) as c:
        r = c.post("/api/runs", json={})
        assert r.status_code == 202
        # o envelope continua o mesmo: 202 muda o código, não o shape
        assert r.json() == {"tool": "start_run", "result": {"run_id": "r-1"},
                            "success": True}
        doc = c.get("/openapi.json").json()
        responses = doc["paths"]["/api/runs"]["post"]["responses"]
        assert "202" in responses
        assert "200" not in responses
        assert "default" in responses  # envelope de erro continua documentado


def test_default_continua_200():
    server = Server.get_instance()

    class PingEndpoint(Endpoint):
        mcp_definition = {"name": "ping", "description": "pong",
                          "parameters": {"properties": {}}}
        url = "/api/ping"
        method = "GET"

        def callback(self):
            return {"pong": True}

    with TestClient(server.app) as c:
        assert c.get("/api/ping").status_code == 200


def test_erro_ignora_o_success_code():
    """422/400/409 vêm da exceção; o success_code só fala do caminho feliz."""
    server = Server.get_instance()

    class QuebraEndpoint(Endpoint):
        success_code = 202
        mcp_definition = {"name": "quebra", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/quebra"
        method = "POST"

        def callback(self):
            raise ValidationError("nope")

    with TestClient(server.app) as c:
        assert c.post("/api/quebra", json={}).status_code == 400


def test_204_recusado_no_import():
    """204 proíbe corpo; o envelope sempre tem corpo — a combinação é ilegal por
    construção e explode no registro, não em produção."""
    with pytest.raises(TypeError, match="204"):
        class SemCorpoEndpoint(Endpoint):
            success_code = 204
            mcp_definition = {"name": "s", "description": "x",
                              "parameters": {"properties": {}}}
            url = "/api/sem-corpo"
            method = "DELETE"

            def callback(self):
                return {}


@pytest.mark.parametrize("codigo", [302, 404, 199, "202", True])
def test_fora_da_faixa_2xx_recusado_no_import(codigo):
    with pytest.raises(TypeError, match="success_code"):
        class ForaEndpoint(Endpoint):
            success_code = codigo
            mcp_definition = {"name": "f", "description": "x",
                              "parameters": {"properties": {}}}
            url = "/api/fora"
            method = "GET"

            def callback(self):
                return {}
