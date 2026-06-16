"""
restmcp usage example — sync vs async

Patterns demonstrated:
  1. Sync callback    → runs in thread pool (via run_in_executor), does not block the event loop
  2. Async callback   → awaited directly on the event loop
  3. Parallel async   → asyncio.gather inside the DataSource (multiple simultaneous requests)
  4. Dependency injection → Service(repo=MockRepository()) isolates tests from the network

All endpoints are registered automatically when example.urls is imported.
Starlette's TestClient executes synchronous requests against the ASGI app — no real server needed.
"""

import sys
import importlib
import pytest
from starlette.testclient import TestClient
from restmcp.server import Server


def _setup_endpoints():
    """Clear module cache and re-import to re-register endpoints after Server._reset()."""
    for key in list(sys.modules.keys()):
        if "example" in key:
            del sys.modules[key]
    importlib.import_module("example.urls")


@pytest.fixture(scope="module", autouse=True)
def setup_server():
    Server._reset()
    _setup_endpoints()
    yield
    Server._reset()


def client():
    return TestClient(Server.get_instance().app)


# ---------------------------------------------------------------------------
# 1. SYNC callback — requests + thread pool
# ---------------------------------------------------------------------------

class TestSyncEndpoint:
    """
    GetPostEndpoint uses `def callback` (sync).
    restmcp detects it via inspect.iscoroutinefunction() and calls:
        loop.run_in_executor(None, lambda: self.callback(**params))

    The event loop is not blocked. Python's thread pool handles the
    blocking requests.get() call.
    """

    def test_get_post_returns_correct_fields(self):
        response = client().post("/posts/get", json={"post_id": 1})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        post = data["result"]
        assert post["id"] == 1
        assert "title" in post
        assert "body" in post
        assert "userId" in post

    def test_get_post_validates_entity(self):
        """PostEntity (Pydantic) enforces correct types."""
        response = client().post("/posts/get", json={"post_id": 5})
        post = response.json()["result"]
        assert isinstance(post["id"], int)
        assert isinstance(post["userId"], int)
        assert isinstance(post["title"], str)

    def test_list_posts_without_filter(self):
        response = client().post("/posts/list", json={})
        data = response.json()
        assert data["success"] is True
        posts = data["result"]
        assert len(posts) == 100  # JSONPlaceholder returns 100 posts

    def test_list_posts_filtered_by_user(self):
        response = client().post("/posts/list", json={"user_id": 1})
        posts = response.json()["result"]
        assert len(posts) == 10
        assert all(p["userId"] == 1 for p in posts)

    def test_invalid_param_returns_400(self):
        response = client().post("/posts/get", json={"post_id": 1, "extra": "bad"})
        assert response.status_code == 400
        assert response.json()["error_type"] == "ValidationError"


# ---------------------------------------------------------------------------
# 2. ASYNC callback — httpx + event loop
# ---------------------------------------------------------------------------

class TestAsyncEndpoint:
    """
    GetPostAsyncEndpoint uses `async def callback`.
    restmcp detects it and calls:
        result = await self.callback(**params)

    httpx.AsyncClient makes the request without blocking the event loop.
    Best suited when a single request needs multiple sequential async calls.
    """

    def test_get_post_async_returns_same_data_as_sync(self):
        sync_resp = client().post("/posts/get", json={"post_id": 1})
        async_resp = client().post("/posts/get-async", json={"post_id": 1})
        assert sync_resp.status_code == 200
        assert async_resp.status_code == 200
        assert sync_resp.json()["result"] == async_resp.json()["result"]

    def test_async_callback_returns_correct_fields(self):
        response = client().post("/posts/get-async", json={"post_id": 3})
        assert response.status_code == 200
        post = response.json()["result"]
        assert post["id"] == 3
        assert "title" in post


# ---------------------------------------------------------------------------
# 3. PARALLEL async — asyncio.gather
# ---------------------------------------------------------------------------

class TestAsyncParallel:
    """
    GetManyPostsAsyncEndpoint fetches multiple posts in parallel.
    The DataSource uses asyncio.gather to fire all requests simultaneously —
    total time equals the slowest single request, not the sum of all.

    Example: fetching 5 posts takes ~200ms in parallel vs ~1000ms sequentially.
    """

    def test_get_many_returns_all_requested_posts(self):
        response = client().post("/posts/get-many", json={"post_ids": [1, 2, 3]})
        assert response.status_code == 200
        posts = response.json()["result"]
        assert len(posts) == 3
        ids = {p["id"] for p in posts}
        assert ids == {1, 2, 3}

    def test_get_many_order_preserved(self):
        response = client().post("/posts/get-many", json={"post_ids": [5, 10, 15]})
        posts = response.json()["result"]
        assert posts[0]["id"] == 5
        assert posts[1]["id"] == 10
        assert posts[2]["id"] == 15

    def test_get_many_single_post(self):
        response = client().post("/posts/get-many", json={"post_ids": [42]})
        posts = response.json()["result"]
        assert len(posts) == 1
        assert posts[0]["id"] == 42


# ---------------------------------------------------------------------------
# 4. Dependency injection — mocked DataSource (no network)
# ---------------------------------------------------------------------------

class TestDependencyInjection:
    """
    restmcp's injection pattern: Service(repo=MockRepository())
    Isolates the test from the network — zero HTTP calls.
    """

    def test_sync_service_with_mock(self):
        from restmcp import DataSource, Repository
        from example.services.posts import PostsService
        from example.models.post import PostEntity

        class MockDataSource(DataSource):
            def get_post(self, post_id):
                return {"id": post_id, "title": "Mock Title", "body": "Mock Body", "userId": 99}
            def get_posts(self, user_id=None):
                return []

        class MockRepository(Repository):
            data_source = MockDataSource()
            def get(self, post_id):
                return PostEntity(**self.data_source.get_post(post_id))
            def list(self, user_id=None):
                return []

        result = PostsService(repo=MockRepository()).get_post(1)
        assert result["title"] == "Mock Title"
        assert result["userId"] == 99

    def test_async_service_with_mock(self):
        import asyncio
        from restmcp import DataSource, Repository
        from example.services.posts import AsyncPostsService
        from example.models.post import PostEntity

        class MockAsyncDataSource(DataSource):
            async def get_post(self, post_id):
                return {"id": post_id, "title": "Async Mock", "body": "body", "userId": 1}
            async def get_posts(self, post_ids):
                return [{"id": pid, "title": f"Post {pid}", "body": "body", "userId": 1} for pid in post_ids]

        class MockAsyncRepository(Repository):
            data_source = MockAsyncDataSource()
            async def get(self, post_id):
                return PostEntity(**await self.data_source.get_post(post_id))
            async def get_many(self, post_ids):
                raws = await self.data_source.get_posts(post_ids)
                return [PostEntity(**r) for r in raws]

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            AsyncPostsService(repo=MockAsyncRepository()).get_post(7)
        )
        assert result["title"] == "Async Mock"
