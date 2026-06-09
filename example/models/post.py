from restmcp import Entity


class PostEntity(Entity):
    id: int
    title: str
    body: str
    userId: int
