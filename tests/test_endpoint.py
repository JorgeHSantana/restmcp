import pytest
from starlette.testclient import TestClient

from restmcp.datasource import DataSource
from restmcp.endpoint import Endpoint
from restmcp.exceptions import NotFoundError, ValidationError
from restmcp.repository import Repository
from restmcp.server import Server
from restmcp.service import Service


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


# --- mcp_definition structure validation ---

def test_mcp_definition_not_a_dict_raises():
    with pytest.raises(TypeError, match="must be a dict"):
        class BadEndpoint(Endpoint):
            mcp_definition = "not a dict"
            url = "/x"
            method = "POST"
            def callback(self): pass


def test_mcp_definition_missing_name_raises():
    with pytest.raises(TypeError, match="'name'"):
        class BadEndpoint(Endpoint):
            mcp_definition = {"description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
            def callback(self): pass


def test_mcp_definition_missing_description_raises():
    with pytest.raises(TypeError, match="'description'"):
        class BadEndpoint(Endpoint):
            mcp_definition = {"name": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"
            def callback(self): pass


def test_mcp_definition_bad_properties_raises():
    with pytest.raises(TypeError, match="'properties'"):
        class BadEndpoint(Endpoint):
            mcp_definition = {
                "name": "x",
                "description": "x",
                "parameters": {"properties": "not a dict"},
            }
            url = "/x"
            method = "POST"
            def callback(self): pass


# --- partial definitions fail loudly at class-definition time ---

def test_partial_endpoint_definition_raises():
    with pytest.raises(TypeError, match="incomplete endpoint definition.*method"):
        class TypoEndpoint(Endpoint):
            url = "/api/typo"
            metod = "POST"  # typo: 'method' missing
            def callback(self):
                """X.

                Returns: x.
                """
                return {}


def test_base_class_with_no_attrs_is_allowed():
    class SharedBaseEndpoint(Endpoint):
        pass  # no url/method/callback: intermediate base, nothing registered


# --- validation errors on missing attributes ---

def test_endpoint_infers_mcp_definition_when_absent():
    class InferDefEndpoint(Endpoint):
        url = "/x"
        method = "POST"
        def callback(self):
            """Infer the definition.

            Returns: nothing meaningful.
            """

    handler = Server.get_instance().url_handlers[-1]
    assert handler.mcp_definition["name"] == "infer_def"


def test_endpoint_missing_url_raises_at_definition():
    with pytest.raises(TypeError, match="incomplete endpoint definition.*url"):
        class NoUrlEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            method = "POST"
            def callback(self): pass


def test_endpoint_missing_method_raises_at_definition():
    with pytest.raises(TypeError, match="incomplete endpoint definition.*method"):
        class NoMethodEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            def callback(self): pass


def test_endpoint_missing_callback_raises_at_definition():
    with pytest.raises(TypeError, match="incomplete endpoint definition.*callback"):
        class NoCallbackEndpoint(Endpoint):
            mcp_definition = {"name": "x", "description": "x", "parameters": {"properties": {}}}
            url = "/x"
            method = "POST"


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
    # An intermediate base that shares a callback but is not itself an endpoint
    # opts out with disabled = True (a partial definition otherwise raises).
    class BaseCustomEndpoint(Endpoint):
        disabled = True
        method = "POST"
        def callback(self, **kwargs): return {}

    server = Server.get_instance()
    assert not any(
        getattr(h, "__class__", None) is BaseCustomEndpoint
        for h in server.url_handlers
    )


# --- HTTP callbacks (sync) ---

def test_endpoint_callback_success():
    _make_get_item_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/get-item", json={"item_id": "42"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["id"] == "42"


def test_endpoint_callback_invalid_param():
    _make_get_item_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/get-item", json={"unknown_param": "val"})
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error_type"] == "ValidationError"


def test_endpoint_callback_validation_error_from_callback():
    class RaisingEndpoint(Endpoint):
        mcp_definition = {"name": "raising_tool", "description": "raises", "parameters": {"properties": {}}}
        url = "/api/raising"
        method = "POST"
        def callback(self):
            raise ValidationError("invalid input")

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/raising", json={})
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_endpoint_callback_not_found_error():
    class NotFoundEndpoint(Endpoint):
        mcp_definition = {"name": "notfound_tool", "description": "404", "parameters": {"properties": {}}}
        url = "/api/notfound"
        method = "POST"
        def callback(self):
            raise NotFoundError("not found")

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/notfound", json={})
    assert response.status_code == 404


def test_endpoint_callback_internal_error():
    class BoomEndpoint(Endpoint):
        mcp_definition = {"name": "boom_tool", "description": "explode", "parameters": {"properties": {}}}
        url = "/api/boom"
        method = "POST"
        def callback(self):
            raise RuntimeError("unexpected boom")

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/boom", json={})
    assert response.status_code == 500
    assert response.json()["error_type"] == "InternalServerError"


# --- async callback ---

def test_endpoint_async_callback_is_awaited():
    class AsyncEndpoint(Endpoint):
        mcp_definition = {
            "name": "async_tool",
            "description": "async callback",
            "parameters": {"properties": {"x": {"type": "string"}}},
        }
        url = "/api/async"
        method = "POST"

        async def callback(self, x: str):
            return {"async": True, "x": x}

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/async", json={"x": "hello"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["result"]["async"] is True
    assert data["result"]["x"] == "hello"


# --- reference_date no longer special ---

def test_reference_date_passed_as_is():
    class DateEndpoint(Endpoint):
        mcp_definition = {
            "name": "date_tool",
            "description": "date passthrough",
            "parameters": {"properties": {"reference_date": {"type": "string"}}},
        }
        url = "/api/date"
        method = "POST"

        def callback(self, reference_date: str):
            return {"received": reference_date}

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/date", json={"reference_date": "2024-01-01"})
    assert response.status_code == 200
    assert response.json()["result"]["received"] == "2024-01-01"


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

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/fullstack", json={"item_id": "1"})
    assert response.status_code == 200
    assert response.json()["result"]["name"] == "Real Item"


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

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/fullstack-mock", json={"item_id": "99"})
    assert response.status_code == 200
    assert response.json()["result"]["name"] == "Mock Item"


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

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/fullstack-notfound", json={"item_id": "missing"})
    assert response.status_code == 404
    assert response.json()["error_type"] == "NotFoundError"


# --- client errors must be 400, not 500 ---

def test_non_object_json_body_returns_400():
    _make_get_item_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/get-item", json=[1, 2, 3])
    assert response.status_code == 400
    assert response.json()["error_type"] == "ValidationError"


def test_missing_required_param_returns_400():
    _make_get_item_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/get-item", json={})
    assert response.status_code == 400
    body = response.json()
    assert body["error_type"] == "ValidationError"
    assert "item_id" in body["error"]


# --- REST type validation mirrors the MCP (pydantic) path ---

def _make_typed_endpoint():
    class TypedEndpoint(Endpoint):
        mcp_definition = {
            "name": "typed_tool",
            "description": "typed params",
            "parameters": {"properties": {
                "n": {"type": "integer"},
                "flag": {"type": "boolean", "default": False},
            }},
        }
        url = "/api/typed"
        method = "POST"

        def callback(self, n: int, flag: bool = False):
            return {"n": n, "flag": flag}


def test_wrong_type_returns_400():
    _make_typed_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/typed", json={"n": "abc"})
    assert response.status_code == 400
    assert response.json()["error_type"] == "ValidationError"


def test_correct_types_pass_through():
    _make_typed_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/typed", json={"n": 5, "flag": True})
    assert response.status_code == 200
    assert response.json()["result"] == {"n": 5, "flag": True}


def test_numeric_string_is_coerced():
    _make_typed_endpoint()
    client = TestClient(Server.get_instance().app)
    response = client.post("/api/typed", json={"n": "5"})
    assert response.status_code == 200
    assert response.json()["result"]["n"] == 5


def test_explicit_null_allowed_when_default_is_none():
    class NullableEndpoint(Endpoint):
        mcp_definition = {
            "name": "nullable_tool",
            "description": "nullable param",
            "parameters": {"properties": {
                "ids": {"type": "array", "items": {"type": "integer"}, "default": None},
            }},
        }
        url = "/api/nullable"
        method = "POST"

        def callback(self, ids: list | None = None):
            return {"ids": ids}

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/nullable", json={"ids": None})
    assert response.status_code == 200
    assert response.json()["result"]["ids"] is None


# --- query-string parameters (GET endpoints) ---

def test_get_endpoint_reads_query_params():
    class QueryEndpoint(Endpoint):
        mcp_definition = {
            "name": "query_tool",
            "description": "query params",
            "parameters": {"properties": {
                "q": {"type": "string", "default": "none"},
                "n": {"type": "integer", "default": 0},
            }},
        }
        url = "/api/query"
        method = "GET"

        def callback(self, q: str = "none", n: int = 0):
            return {"q": q, "n": n}

    client = TestClient(Server.get_instance().app)
    response = client.get("/api/query?q=hello&n=7")
    assert response.status_code == 200
    assert response.json()["result"] == {"q": "hello", "n": 7}


def test_unknown_query_param_is_ignored():
    class Query2Endpoint(Endpoint):
        mcp_definition = {
            "name": "query2_tool",
            "description": "query params",
            "parameters": {"properties": {"q": {"type": "string", "default": "none"}}},
        }
        url = "/api/query2"
        method = "GET"

        def callback(self, q: str = "none"):
            return {"q": q}

    client = TestClient(Server.get_instance().app)
    response = client.get("/api/query2?nope=1")          # unknown query key ignored
    assert response.status_code == 200
    assert response.json()["result"] == {"q": "none"}


def test_internal_error_does_not_leak_details():
    class LeakEndpoint(Endpoint):
        mcp_definition = {"name": "leak_tool", "description": "leak", "parameters": {"properties": {}}}
        url = "/api/leak"
        method = "POST"

        def callback(self):
            raise RuntimeError("secret internal detail")

    client = TestClient(Server.get_instance().app)
    response = client.post("/api/leak", json={})
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal server error"
    assert "secret internal detail" not in str(body)


# --- registration is idempotent and atomic (issue #10) ---

def test_double_instantiation_does_not_duplicate_route():
    class DupEndpoint(Endpoint):
        mcp_definition = {"name": "dup_tool", "description": "dup", "parameters": {"properties": {}}}
        url = "/api/dup"
        method = "POST"
        def callback(self):
            return {}

    server = Server.get_instance()

    def route_count():
        return len([r for r in server.app.routes if getattr(r, "path", None) == "/api/dup"])

    assert route_count() == 1
    assert len(server.url_handlers) == 1
    DupEndpoint()  # manual second instantiation must be a no-op
    assert route_count() == 1
    assert len(server.url_handlers) == 1


def test_handler_registration_failure_leaves_no_orphan_route(monkeypatch):
    server = Server.get_instance()

    def boom(handler):
        raise RuntimeError("handler list exploded")

    monkeypatch.setattr(server, "register_url_handler", boom)

    with pytest.raises(RuntimeError, match="handler list exploded"):
        class Orphan2Endpoint(Endpoint):
            mcp_definition = {"name": "orphan2_tool", "description": "orphan", "parameters": {"properties": {}}}
            url = "/api/orphan2"
            method = "POST"
            def callback(self):
                return {}

    # with append-first ordering, the ASGI route must never have been added
    assert all(getattr(r, "path", None) != "/api/orphan2" for r in server.app.routes)


def test_route_registration_failure_rolls_back_handler(monkeypatch):
    server = Server.get_instance()

    def boom(*args, **kwargs):
        raise RuntimeError("route table exploded")

    monkeypatch.setattr(server.app, "add_api_route", boom)

    with pytest.raises(RuntimeError, match="route table exploded"):
        class Orphan3Endpoint(Endpoint):
            mcp_definition = {"name": "orphan3_tool", "description": "orphan", "parameters": {"properties": {}}}
            url = "/api/orphan3"
            method = "POST"
            def callback(self):
                return {}

    # rollback: the handler appended before the route failure must be removed
    assert server.url_handlers == []


# --- unified validation via the shared pydantic model ---

def test_integral_float_and_numeric_string_accepted():
    _make_typed_endpoint()  # n: integer (required), flag: boolean default False
    client = TestClient(Server.get_instance().app)
    assert client.post("/api/typed", json={"n": 5.0}).json()["result"]["n"] == 5
    assert client.post("/api/typed", json={"n": "5"}).json()["result"]["n"] == 5


def test_bool_rejected_for_integer():
    _make_typed_endpoint()
    client = TestClient(Server.get_instance().app)
    r = client.post("/api/typed", json={"n": True})
    assert r.status_code == 400
    assert r.json()["error_type"] == "ValidationError"


def test_unknown_body_param_returns_400():
    _make_typed_endpoint()
    client = TestClient(Server.get_instance().app)
    r = client.post("/api/typed", json={"n": 1, "bogus": 2})
    assert r.status_code == 400
    assert r.json()["error_type"] == "ValidationError"


def test_missing_required_reports_field_name():
    _make_typed_endpoint()
    client = TestClient(Server.get_instance().app)
    r = client.post("/api/typed", json={})
    assert r.status_code == 400
    assert "n" in r.json()["error"]


# --- registration-time definition errors (review findings 1, 3, 4) ---

def test_underscore_property_name_fails_at_class_definition():
    with pytest.raises(TypeError, match="_secret"):
        class Under1Endpoint(Endpoint):
            mcp_definition = {
                "name": "under1_tool",
                "description": "x",
                "parameters": {"properties": {"_secret": {"type": "string"}}},
            }
            url = "/api/under1"
            method = "POST"
            def callback(self, _secret): return {}


def test_pydantic_reserved_property_name_fails_with_context():
    with pytest.raises(TypeError, match="Reserved1Endpoint"):
        class Reserved1Endpoint(Endpoint):
            mcp_definition = {
                "name": "reserved1_tool",
                "description": "x",
                "parameters": {"properties": {"model_dump": {"type": "string"}}},
            }
            url = "/api/reserved1"
            method = "POST"
            def callback(self, **kwargs): return {}


def test_none_parameters_registers_and_serves():
    # 'parameters': None passes _validate_mcp_definition and must keep working
    # (review finding 3: it used to crash the import with AttributeError).
    class NoneParams1Endpoint(Endpoint):
        mcp_definition = {
            "name": "none_params1_tool",
            "description": "x",
            "parameters": None,
        }
        url = "/api/none-params1"
        method = "POST"
        def callback(self): return {"ok": True}

    client = TestClient(Server.get_instance().app)
    r = client.post("/api/none-params1", json={})
    assert r.status_code == 200
    assert r.json()["result"] == {"ok": True}


def test_bad_default_fails_at_class_definition_with_context():
    with pytest.raises((TypeError, ValueError), match="BadDefault1Endpoint|default"):
        class BadDefault1Endpoint(Endpoint):
            mcp_definition = {
                "name": "bad_default1_tool",
                "description": "x",
                "parameters": {"properties":
                    {"n": {"type": "integer", "default": "abc"}}},
            }
            url = "/api/bad-default1"
            method = "POST"
            def callback(self, n=0): return {"n": n}
