import pytest
from starlette.testclient import TestClient
from pythia.endpoint import Endpoint
from pythia.server import Server


def test_server_is_singleton():
    s1 = Server.get_instance()
    s2 = Server.get_instance()
    assert s1 is s2


def test_server_has_app():
    server = Server.get_instance()
    assert server.app is not None


def test_health_endpoint_returns_200():
    server = Server.get_instance()
    client = TestClient(server.app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_mcp_tools_endpoint_returns_empty_list():
    server = Server.get_instance()
    client = TestClient(server.app)
    response = client.get("/mcp/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["tools"] == []


def test_register_url_handler():
    server = Server.get_instance()

    class FakeHandler:
        mcp_definition = {
            "name": "fake_tool",
            "description": "test tool",
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
            "description": "description",
            "parameters": {"properties": {}},
        }

    server.register_url_handler(FakeHandler())
    client = TestClient(server.app)
    response = client.get("/mcp/tools")
    tools = response.json()["tools"]
    assert any(t["name"] == "my_tool" for t in tools)


def test_server_reset_clears_instance():
    s1 = Server.get_instance()
    Server._reset()
    s2 = Server.get_instance()
    assert s1 is not s2


# --- auth ---

def _make_auth_endpoint():
    class AuthedEndpoint(Endpoint):
        mcp_definition = {"name": "authed_tool", "description": "requires auth", "parameters": {"properties": {}}}
        url = "/api/authed"
        method = "POST"
        def callback(self): return {"ok": True}


def test_auth_valid_key_accepted(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "secret123")
    _make_auth_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/authed", json={}, headers={"Authorization": "Bearer secret123"})
    assert response.status_code == 200


def test_auth_invalid_key_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "secret123")
    _make_auth_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/authed", json={}, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_auth_no_key_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "secret123")
    _make_auth_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/authed", json={})
    assert response.status_code == 401


def test_auth_health_bypasses_auth(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "secret123")
    client = TestClient(Server.get_instance().app)
    response = client.get("/health")
    assert response.status_code == 200


def test_auth_mcp_tools_bypasses_auth(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "secret123")
    client = TestClient(Server.get_instance().app)
    response = client.get("/mcp/tools")
    assert response.status_code == 200


def test_auth_multiple_keys_accepted(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "key1,key2,key3")
    _make_auth_endpoint()
    client = TestClient(Server.get_instance().app)
    assert client.post("/api/authed", json={}, headers={"Authorization": "Bearer key2"}).status_code == 200
    assert client.post("/api/authed", json={}, headers={"Authorization": "Bearer key3"}).status_code == 200
