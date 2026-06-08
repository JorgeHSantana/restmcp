from typing import List, Optional

from pythia import Endpoint
from example.services.posts import AsyncPostsService, PostsService


# --- SYNC: callback usa requests, roda em thread pool automaticamente ---

class GetPostEndpoint(Endpoint):
    url = "/posts/get"
    method = "POST"
    mcp_definition = {
        "name": "get_post",
        "description": "Busca um post pelo ID (sync — usa requests)",
        "parameters": {
            "properties": {
                "post_id": {"type": "integer", "description": "ID do post (1-100)"}
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
        "description": "Lista posts, com filtro opcional por userId (sync)",
        "parameters": {
            "properties": {
                "user_id": {"type": "integer", "description": "Filtrar por usuário (opcional)", "default": None}
            }
        },
    }

    def callback(self, user_id: Optional[int] = None) -> List[dict]:
        return PostsService().list_posts(user_id=user_id)


# --- ASYNC: callback usa httpx, roda no event loop diretamente ---

class GetPostAsyncEndpoint(Endpoint):
    url = "/posts/get-async"
    method = "POST"
    mcp_definition = {
        "name": "get_post_async",
        "description": "Busca um post pelo ID (async — usa httpx)",
        "parameters": {
            "properties": {
                "post_id": {"type": "integer", "description": "ID do post (1-100)"}
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
        "description": "Busca vários posts em paralelo com asyncio.gather (async)",
        "parameters": {
            "properties": {
                "post_ids": {"type": "array", "items": {"type": "integer"}, "description": "Lista de IDs"}
            }
        },
    }

    async def callback(self, post_ids: List[int]) -> List[dict]:
        return await AsyncPostsService().get_many(post_ids)
