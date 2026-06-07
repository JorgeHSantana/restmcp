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
