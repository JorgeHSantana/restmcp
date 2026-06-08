import asyncio
from typing import List

import httpx
from pythia import DataSource


class AsyncPostsDataSource(DataSource):
    base_url = "https://jsonplaceholder.typicode.com"

    async def get_post(self, post_id: int) -> dict:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{self.base_url}/posts/{post_id}")
            response.raise_for_status()
            return response.json()

    async def get_posts(self, post_ids: List[int]) -> List[dict]:
        async with httpx.AsyncClient(timeout=5) as client:
            tasks = [client.get(f"{self.base_url}/posts/{pid}") for pid in post_ids]
            responses = await asyncio.gather(*tasks)
            return [r.json() for r in responses]
