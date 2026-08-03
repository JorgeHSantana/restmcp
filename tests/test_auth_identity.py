"""Issue #15 — key identity and per-key scopes.

``AUTH_API_KEY`` entries gain an optional ``name:key:scope`` form (``scope`` =
``read+write``); a bare ``key`` keeps working with full scope, so existing
deployments are untouched. The matched principal ``{"name", "scopes"}`` is
published in ``scope["state"]["auth"]`` (Starlette convention) and in the
``current_auth`` contextvar — which, after issue #16, survives into sync
callbacks. Step 2: ``required_scope`` on an Endpoint is enforced before the
callback (403), REST path; MCP callers authenticate the whole surface and
write tools are hidden from them via ``expose = "rest"``.
"""
from starlette.testclient import TestClient

from restmcp import Endpoint, Server
from restmcp.auth import current_auth, match_token


def test_match_token_named_and_bare(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "painel:sk_read_1:read, sk_full_2")
    assert match_token("sk_read_1") == {"name": "painel", "scopes": frozenset({"read"})}
    assert match_token("sk_full_2") == {"name": None,
                                        "scopes": frozenset({"read", "write"})}
    assert match_token("sk_wrong") is None
    assert match_token("") is None


def _register_pair(server):
    class ReadThingEndpoint(Endpoint):
        required_scope = "read"
        mcp_definition = {"name": "read_thing", "description": "lê",
                          "parameters": {"properties": {}}}
        url = "/api/read_thing"
        method = "GET"

        def callback(self):
            principal = current_auth.get()
            return {"who": principal["name"] if principal else None}

    class WriteThingEndpoint(Endpoint):
        required_scope = "write"
        mcp_definition = {"name": "write_thing", "description": "escreve",
                          "parameters": {"properties": {}}}
        url = "/api/write_thing"
        method = "POST"

        def callback(self):
            return {"ok": True}


def test_scopes_enforced_and_identity_reaches_sync_callback(monkeypatch):
    monkeypatch.setenv("AUTH_API_KEY", "painel:sk_read_1:read, campo:sk_write_2:read+write")
    server = Server.get_instance()
    _register_pair(server)
    with TestClient(server.app) as c:
        read_headers = {"Authorization": "Bearer sk_read_1"}
        write_headers = {"Authorization": "Bearer sk_write_2"}
        # identity flows into a SYNC callback via contextvar (issue #16 hop)
        assert c.get("/api/read_thing", headers=read_headers).json()["result"] == {
            "who": "painel"}
        # read-only key cannot write
        r = c.post("/api/write_thing", json={}, headers=read_headers)
        assert r.status_code == 403
        assert r.json()["error_type"] == "ForbiddenError"
        # full-scope key can
        assert c.post("/api/write_thing", json={},
                      headers=write_headers).status_code == 200
        # wrong key is still authentication (401), not authorization
        assert c.get("/api/read_thing",
                     headers={"Authorization": "Bearer nope"}).status_code == 401


def test_auth_disabled_skips_scope_check(monkeypatch):
    monkeypatch.delenv("AUTH_API_KEY", raising=False)
    server = Server.get_instance()
    _register_pair(server)
    with TestClient(server.app) as c:
        assert c.post("/api/write_thing", json={}).status_code == 200
        assert c.get("/api/read_thing").json()["result"] == {"who": None}
