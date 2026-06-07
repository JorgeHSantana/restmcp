import pytest
from pythia.datasource import DataSource
from pythia.endpoint import Endpoint
from pythia.exceptions import NotFoundError, ValidationError
from pythia.repository import Repository
from pythia.server import Server
from pythia.service import Service


# --- helpers ---

def _make_get_item_endpoint():
    class GetItemEndpoint(Endpoint):
        mcp_definition = {
            "name": "get_item",
            "description": "Returns an item",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/get-item"
        method = "POST"

        def callback(self, item_id: str):
            return {"id": item_id, "name": "Test Item"}


# --- suffix enforcement ---

def test_endpoint_suffix_enforced():
    with pytest.raises(TypeError, match="Endpoint"):
        class GetItem(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
            def callback(self): pass


# --- validation errors on missing attributes ---

def test_endpoint_requires_mcp_definition():
    class NoDefEndpoint(Endpoint):
        url = "/x"
        method = "POST"
        def callback(self): pass

    with pytest.raises(ValueError, match="mcp_definition"):
        NoDefEndpoint()


def test_endpoint_requires_url():
    class NoUrlEndpoint(Endpoint):
        mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
        method = "POST"
        def callback(self): pass

    with pytest.raises(ValueError, match="url"):
        NoUrlEndpoint()


def test_endpoint_requires_method():
    class NoMethodEndpoint(Endpoint):
        mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
        url = "/x"
        def callback(self): pass

    with pytest.raises(ValueError, match="method"):
        NoMethodEndpoint()


def test_endpoint_requires_callback():
    with pytest.raises(ValueError, match="callback"):
        class NoCallbackEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
        NoCallbackEndpoint()


# --- auto-registration ---

def test_endpoint_auto_registers_on_class_definition():
    class AutoEndpoint(Endpoint):
        mcp_definition = {"name": "auto_tool", "description": "auto", "parameters": {"properties": {}}}
        url = "/api/auto"
        method = "POST"
        def callback(self): return {}

    server = Server.get_instance()
    assert any(h.mcp_definition["name"] == "auto_tool" for h in server.url_handlers)


def test_endpoint_registers_on_server():
    _make_get_item_endpoint()
    server = Server.get_instance()
    assert any(h.mcp_definition["name"] == "get_item" for h in server.url_handlers)


# --- disabled ---

def test_endpoint_disabled_skips_registration():
    class DisabledEndpoint(Endpoint):
        disabled = True
        mcp_definition = {"name": "disabled_tool", "description": "x", "parameters": {"properties": {}}}
        url = "/api/disabled"
        method = "POST"
        def callback(self): return {}

    server = Server.get_instance()
    assert not any(h.mcp_definition["name"] == "disabled_tool" for h in server.url_handlers)


def test_endpoint_disabled_can_be_instantiated_manually():
    class ManualEndpoint(Endpoint):
        disabled = True
        mcp_definition = {"name": "manual_tool", "description": "x", "parameters": {"properties": {}}}
        url = "/api/manual"
        method = "POST"
        def callback(self): return {}

    ManualEndpoint()
    server = Server.get_instance()
    assert any(h.mcp_definition["name"] == "manual_tool" for h in server.url_handlers)


# --- abstract base class (no auto-registration without required attrs) ---

def test_abstract_base_endpoint_not_auto_registered():
    class BaseCustomEndpoint(Endpoint):
        method = "POST"
        def callback(self, **kwargs): return {}

    server = Server.get_instance()
    # BaseCustomEndpoint has no url or mcp_definition — must not be registered
    assert not any(
        getattr(h, "__class__", None) is BaseCustomEndpoint
        for h in server.url_handlers
    )


# --- HTTP callbacks ---

def test_endpoint_callback_success():
    _make_get_item_endpoint()
    client = Server.get_instance().app.test_client()
    response = client.post("/api/get-item", json={"item_id": "42"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["result"]["id"] == "42"


def test_endpoint_callback_invalid_param():
    _make_get_item_endpoint()
    client = Server.get_instance().app.test_client()
    response = client.post("/api/get-item", json={"unknown_param": "val"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["success"] is False
    assert data["error_type"] == "ValidationError"


def test_endpoint_callback_validation_error_from_callback():
    class RaisingEndpoint(Endpoint):
        mcp_definition = {"name": "raising_tool", "description": "raises", "parameters": {"properties": {}}}
        url = "/api/raising"
        method = "POST"
        def callback(self):
            raise ValidationError("invalid input")

    client = Server.get_instance().app.test_client()
    response = client.post("/api/raising", json={})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_endpoint_callback_not_found_error():
    class NotFoundEndpoint(Endpoint):
        mcp_definition = {"name": "notfound_tool", "description": "404", "parameters": {"properties": {}}}
        url = "/api/notfound"
        method = "POST"
        def callback(self):
            raise NotFoundError("not found")

    client = Server.get_instance().app.test_client()
    response = client.post("/api/notfound", json={})
    assert response.status_code == 404


def test_endpoint_callback_internal_error():
    class BoomEndpoint(Endpoint):
        mcp_definition = {"name": "boom_tool", "description": "explode", "parameters": {"properties": {}}}
        url = "/api/boom"
        method = "POST"
        def callback(self):
            raise RuntimeError("unexpected boom")

    client = Server.get_instance().app.test_client()
    response = client.post("/api/boom", json={})
    assert response.status_code == 500
    assert response.get_json()["error_type"] == "InternalServerError"


# --- Full-stack injection: Endpoint → Service → Repository → DataSource ---

class _FakeDataSource(DataSource):
    def __init__(self, records: dict):
        self._records = records


class _ItemRepository(Repository):
    data_source = _FakeDataSource({"1": "Real Item"})

    def get(self, item_id: str):
        return self.data_source._records.get(item_id)


class _GetItemService(Service):
    repo = _ItemRepository()

    def execute(self, item_id: str):
        result = self.repo.get(item_id=item_id)
        if result is None:
            raise NotFoundError(f"Item {item_id} not found")
        return {"id": item_id, "name": result}


def test_endpoint_uses_service_with_real_repository():
    class FullStackEndpoint(Endpoint):
        mcp_definition = {
            "name": "fullstack_tool",
            "description": "full stack",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/fullstack"
        method = "POST"

        def callback(self, item_id: str):
            return _GetItemService().execute(item_id)

    client = Server.get_instance().app.test_client()
    response = client.post("/api/fullstack", json={"item_id": "1"})
    assert response.status_code == 200
    assert response.get_json()["result"]["name"] == "Real Item"


def test_endpoint_uses_service_with_injected_mock_repository():
    class MockItemRepository(Repository):
        data_source = _FakeDataSource({"99": "Mock Item"})

        def get(self, item_id: str):
            return self.data_source._records.get(item_id)

    class FullStackMockEndpoint(Endpoint):
        mcp_definition = {
            "name": "fullstack_mock_tool",
            "description": "full stack mock",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/fullstack-mock"
        method = "POST"

        def callback(self, item_id: str):
            return _GetItemService(repo=MockItemRepository()).execute(item_id)

    client = Server.get_instance().app.test_client()
    response = client.post("/api/fullstack-mock", json={"item_id": "99"})
    assert response.status_code == 200
    assert response.get_json()["result"]["name"] == "Mock Item"


def test_endpoint_service_not_found_propagates_as_404():
    class NotFoundMockRepository(Repository):
        data_source = _FakeDataSource({})

        def get(self, **kwargs):
            return None

    class FullStackNotFoundEndpoint(Endpoint):
        mcp_definition = {
            "name": "fullstack_notfound_tool",
            "description": "full stack 404",
            "parameters": {"properties": {"item_id": {"type": "string"}}},
        }
        url = "/api/fullstack-notfound"
        method = "POST"

        def callback(self, item_id: str):
            return _GetItemService(repo=NotFoundMockRepository()).execute(item_id)

    client = Server.get_instance().app.test_client()
    response = client.post("/api/fullstack-notfound", json={"item_id": "missing"})
    assert response.status_code == 404
    assert response.get_json()["error_type"] == "NotFoundError"
