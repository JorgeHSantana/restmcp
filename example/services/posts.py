from typing import List, Optional

from restmcp import Service
from example.repositories.posts import PostsRepository
from example.repositories.posts_async import AsyncPostsRepository


class PostsService(Service):
    repo = PostsRepository()

    def get_post(self, post_id: int) -> dict:
        return self.repo.get(post_id).model_dump()

    def list_posts(self, user_id: Optional[int] = None) -> List[dict]:
        return [p.model_dump() for p in self.repo.list(user_id=user_id)]


class AsyncPostsService(Service):
    repo = AsyncPostsRepository()

    async def get_post(self, post_id: int) -> dict:
        return (await self.repo.get(post_id)).model_dump()

    async def get_many(self, post_ids: List[int]) -> List[dict]:
        return [p.model_dump() for p in await self.repo.get_many(post_ids)]
