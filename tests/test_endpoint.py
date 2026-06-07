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
