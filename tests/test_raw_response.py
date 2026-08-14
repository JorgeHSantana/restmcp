"""Issue #18 (parte 2) — `raw_response`: a escotilha FastAPI para REST puro.

Um endpoint `expose="rest"` não tem lado MCP, então nada obriga a resposta a
viver no envelope — arquivos, redirects, códigos condicionais e headers custom
são legítimos ali. As três travas:

1. exige `expose="rest"` — com lado MCP a resposta crua não tem representação
   na tool, e o import explode;
2. é opt-in declarado (`raw_response = True`) — Response devolvida sem a
   declaração explode em runtime (500 com o motivo no log), nunca passa calada;
3. só o SUCESSO é cru: exceção continua virando o envelope de erro com o código
   da classe — o tratamento de erro do cliente tem UM formato.
"""
import pytest
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.exceptions import NotFoundError


def _download_endpoint():
    class BaixarEndpoint(Endpoint):
        expose = "rest"
        raw_response = True
        mcp_definition = {"name": "baixar", "description": "arquivo",
                          "parameters": {"properties": {}}}
        url = "/api/baixar"
        method = "GET"

        def callback(self):
            return PlainTextResponse(
                "conteudo-cru", status_code=201,
                headers={"content-disposition": 'attachment; filename="x.txt"'},
            )
    return BaixarEndpoint


def test_resposta_crua_passa_direto_sem_envelope():
    server = Server.get_instance()
    _download_endpoint()
    with TestClient(server.app) as c:
        r = c.get("/api/baixar")
        assert r.status_code == 201                      # o código é do endpoint
        assert r.text == "conteudo-cru"                  # corpo cru, sem envelope
        assert "attachment" in r.headers["content-disposition"]


def test_erro_em_endpoint_raw_continua_envelopado():
    """Trava 3: a escotilha é do sucesso; o erro mantém o contrato único."""
    server = Server.get_instance()

    class SomeErroEndpoint(Endpoint):
        expose = "rest"
        raw_response = True
        mcp_definition = {"name": "some_erro", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/some-erro"
        method = "GET"

        def callback(self):
            raise NotFoundError("não existe")

    with TestClient(server.app) as c:
        r = c.get("/api/some-erro")
        assert r.status_code == 404
        body = r.json()
        assert body["success"] is False
        assert body["error_type"] == "NotFoundError"


@pytest.mark.parametrize("modo", ["both", "mcp"])
def test_raw_fora_do_rest_puro_explode_no_import(modo):
    """Trava 1: onde o MCP enxerga, resposta crua não tem representação."""
    with pytest.raises(TypeError, match="raw_response"):
        class VazaEndpoint(Endpoint):
            expose = modo
            raw_response = True
            mcp_definition = {"name": f"vaza_{modo}", "description": "x",
                              "parameters": {"properties": {}}}
            url = f"/api/vaza-{modo}"
            method = "GET"

            def callback(self):
                return {}


def test_raw_com_success_code_explode_no_import():
    """Declarações conflitantes: em modo cru, quem manda no código é a Response."""
    with pytest.raises(TypeError, match="success_code"):
        class ConflitoEndpoint(Endpoint):
            expose = "rest"
            raw_response = True
            success_code = 202
            mcp_definition = {"name": "conflito", "description": "x",
                              "parameters": {"properties": {}}}
            url = "/api/conflito"
            method = "GET"

        def callback(self):
            return PlainTextResponse("x")


def test_response_sem_declarar_explode_em_runtime():
    """Trava 2: devolver Response sem raw_response=True é erro de programação —
    500 com a mensagem apontando o atributo no log, nunca passthrough calado."""
    server = Server.get_instance()

    class EscorregaEndpoint(Endpoint):
        expose = "rest"
        mcp_definition = {"name": "escorrega", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/escorrega"
        method = "GET"

        def callback(self):
            return JSONResponse({"driblei": True}, status_code=201)

    with TestClient(server.app) as c:
        r = c.get("/api/escorrega")
        assert r.status_code == 500
        assert r.json()["error_type"] == "InternalServerError"


def test_raw_que_devolve_dict_explode_em_runtime():
    """O contrato declarado vale nos dois sentidos: modo cru exige Response."""
    server = Server.get_instance()

    class MeiaBocaEndpoint(Endpoint):
        expose = "rest"
        raw_response = True
        mcp_definition = {"name": "meia_boca", "description": "x",
                          "parameters": {"properties": {}}}
        url = "/api/meia-boca"
        method = "GET"

        def callback(self):
            return {"sou": "dict"}

    with TestClient(server.app) as c:
        r = c.get("/api/meia-boca")
        assert r.status_code == 500
        assert r.json()["error_type"] == "InternalServerError"


def test_openapi_do_raw_nao_promete_envelope():
    server = Server.get_instance()
    _download_endpoint()
    with TestClient(server.app) as c:
        doc = c.get("/openapi.json").json()
        responses = doc["paths"]["/api/baixar"]["get"]["responses"]
        assert "200" not in responses      # nenhum envelope de sucesso prometido
        assert "default" in responses      # a descrição honesta mora aqui
        assert "cru" in responses["default"]["description"].lower()
