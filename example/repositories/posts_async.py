from typing import List

from restmcp import Repository
from example.datasource.posts_async import AsyncPostsDataSource
from example.models.post import PostEntity


class AsyncPostsRepository(Repository):
    data_source = AsyncPostsDataSource()

    async def get(self, post_id: int) -> PostEntity:
        raw = await self.data_source.get_post(post_id)
        return PostEntity(**raw)

    async def get_many(self, post_ids: List[int]) -> List[PostEntity]:
        raws = await self.data_source.get_posts(post_ids)
        return [PostEntity(**r) for r in raws]
