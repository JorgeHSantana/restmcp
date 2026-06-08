from typing import List, Optional

from pythia import Repository
from example.datasource.posts_sync import SyncPostsDataSource
from example.models.post import PostEntity


class PostsRepository(Repository):
    data_source = SyncPostsDataSource()

    def get(self, post_id: int) -> PostEntity:
        raw = self.data_source.get_post(post_id)
        return PostEntity(**raw)

    def list(self, user_id: Optional[int] = None) -> List[PostEntity]:
        raws = self.data_source.get_posts(user_id=user_id)
        return [PostEntity(**r) for r in raws]
