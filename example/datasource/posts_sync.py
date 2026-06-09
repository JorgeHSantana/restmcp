from typing import List, Optional

import requests
from restmcp import DataSource


class SyncPostsDataSource(DataSource):
    base_url = "https://jsonplaceholder.typicode.com"

    def get_post(self, post_id: int) -> dict:
        response = requests.get(f"{self.base_url}/posts/{post_id}", timeout=5)
        response.raise_for_status()
        return response.json()

    def get_posts(self, user_id: Optional[int] = None) -> List[dict]:
        params = {"userId": user_id} if user_id else {}
        response = requests.get(f"{self.base_url}/posts", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
