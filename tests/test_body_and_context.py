"""Issues #13 and #16 — malformed JSON must be a 400, and sync callbacks must
see the caller's contextvars.

#13: the broad ``except`` around ``request.json()`` swallowed JSONDecodeError,
so a malformed body was silently treated as empty — with defaults filling in,
a truncated upload could "succeed" as something else entirely. Absent body
stays tolerated (query-string-only calls are legitimate); malformed body is a
client error and must say so.

#16: ``loop.run_in_executor`` submits without copying the task context, so
identity/correlation contextvars set by middleware died on the thread hop.
``asyncio.to_thread`` exists precisely to copy the context.
"""
import asyncio
import contextvars

from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.endpoint import run_callback


def _register_echo(server):
    class EchoEndpoint(Endpoint):
        mcp_definition = {"name": "echo", "description": "eco",
                          "parameters": {"properties": {
                              "note": {"type": "string", "default": "n/a"}}}}
        url = "/api/echo"
        method = "POST"

        def callback(self, note="n/a"):
            return {"note": note}

    return EchoEndpoint


def test_malformed_json_is_400_not_empty_body(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()
    _register_echo(server)
    with TestClient(server.app) as c:
        r = c.post("/api/echo", content=b'{"note": "trunca',
                   headers={"content-type": "application/json"})
        assert r.status_code == 400
        assert r.json()["error_type"] == "ValidationError"


def test_absent_body_still_tolerated(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()
    _register_echo(server)
    with TestClient(server.app) as c:
        # no body at all -> defaults apply (query-string-only call)
        assert c.post("/api/echo").json()["result"] == {"note": "n/a"}
        # empty body -> same
        assert c.post("/api/echo", content=b"").json()["result"] == {"note": "n/a"}


def test_sync_callback_sees_caller_contextvars():
    ctx_var = contextvars.ContextVar("request_id", default=None)

    def sync_callback():
        return {"request_id": ctx_var.get()}

    async def scenario():
        ctx_var.set("req-123")
        return await run_callback(sync_callback)

    assert asyncio.run(scenario()) == {"request_id": "req-123"}
