from typing import List, Optional

from restmcp import Endpoint
from example.services.posts import AsyncPostsService, PostsService


# --- SYNC: callback uses requests, runs in thread pool automatically ---

class GetPostEndpoint(Endpoint):
    url = "/posts/get"
    method = "POST"
    mcp_definition = {
        "name": "get_post",
        "description": "Fetch a post by ID (sync — uses requests)",
        "parameters": {
            "properties": {
                "post_id": {"type": "integer", "description": "Post ID (1-100)"}
            }
        },
    }

    def callback(self, post_id: int) -> dict:
        return PostsService().get_post(post_id)


class ListPostsEndpoint(Endpoint):
    url = "/posts/list"
    method = "POST"
    mcp_definition = {
        "name": "list_posts",
        "description": "List posts with optional userId filter (sync)",
        "parameters": {
            "properties": {
                "user_id": {"type": "integer", "description": "Filter by user (optional)", "default": None}
            }
        },
    }

    def callback(self, user_id: Optional[int] = None) -> List[dict]:
        return PostsService().list_posts(user_id=user_id)


# --- ASYNC: callback uses httpx, runs on the event loop directly ---

class GetPostAsyncEndpoint(Endpoint):
    url = "/posts/get-async"
    method = "POST"
    mcp_definition = {
        "name": "get_post_async",
        "description": "Fetch a post by ID (async — uses httpx)",
        "parameters": {
            "properties": {
                "post_id": {"type": "integer", "description": "Post ID (1-100)"}
            }
        },
    }

    async def callback(self, post_id: int) -> dict:
        return await AsyncPostsService().get_post(post_id)


class GetManyPostsAsyncEndpoint(Endpoint):
    url = "/posts/get-many"
    method = "POST"
    mcp_definition = {
        "name": "get_many_posts",
        "description": "Fetch multiple posts in parallel using asyncio.gather (async)",
        "parameters": {
            "properties": {
                "post_ids": {"type": "array", "items": {"type": "integer"}, "description": "List of post IDs"}
            }
        },
    }

    async def callback(self, post_ids: List[int]) -> List[dict]:
        return await AsyncPostsService().get_many(post_ids)
