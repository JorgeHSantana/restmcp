import hmac
import os
from starlette.responses import JSONResponse


def _valid_token(raw: str) -> bool:
    keys = [k.strip() for k in os.getenv("AUTH_API_KEY", "").split(",") if k.strip()]
    return bool(raw) and any(hmac.compare_digest(raw, k) for k in keys)


class AuthMiddleware:
    """Pure-ASGI Bearer-token middleware (does not buffer SSE).

    Covers both REST and the MCP sub-app mounted via asgi_app(). No-op when
    AUTH_API_KEY is unset.

    `public_paths`: routes exempt from auth, matched by **exact path** (default
    `/health` and `/mcp/tools`). Exact match — not prefix — is intentional:
    exposing `/mcp/tools` (the tool catalog) does NOT expose
    `/mcp/tools/<endpoint>`, which stay protected. Paths under `/.well-known/`
    (MCP OAuth discovery) are always public.
    """

    def __init__(self, app, public_paths=("/health", "/mcp/tools")):
        self.app = app
        self.public = frozenset(public_paths)

    def _is_public(self, path: str) -> bool:
        return path in self.public or path.startswith("/.well-known/")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not os.getenv("AUTH_API_KEY"):
            return await self.app(scope, receive, send)

        if self._is_public(scope.get("path", "")):
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode("utf-8", "ignore")
        token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else None
        if not token or not _valid_token(token):
            resp = JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await resp(scope, receive, send)

        return await self.app(scope, receive, send)
