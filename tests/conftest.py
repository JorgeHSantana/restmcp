import pytest

@pytest.fixture(autouse=True)
def reset_server():
    from restmcp.server import Server
    Server._reset()
    yield
    Server._reset()
