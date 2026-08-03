import contextvars
import hmac
import os

from starlette.responses import JSONResponse

# Identity of the key that authenticated the CURRENT request:
# {"name": str | None, "scopes": frozenset[str]} — or None (auth disabled /
# not yet authenticated). Set by AuthMiddleware and by the REST dependency;
# readable anywhere below, including sync callbacks (run_callback copies the
# context into the worker thread — issue #16).
current_auth: contextvars.ContextVar = contextvars.ContextVar(
    "restmcp_current_auth", default=None
)

_FULL_SCOPE = frozenset({"read", "write"})


def token_from_authorization(value: str) -> str | None:
    """Single Bearer parser — auth.py and rest.py used to keep two subtly
    different copies (issue #15, side note)."""
    if not value or not value.startswith("Bearer "):
        return None
    return value.split(" ", 1)[1]


def match_token(raw: str) -> dict | None:
    """Identity of the presented key, or None when nothing matches.

    ``AUTH_API_KEY`` entries (comma-separated) accept two forms (issue #15):
    - ``key`` — the historical form; full scope, anonymous;
    - ``name:key:scope`` — named key with ``scope`` as a ``+``-joined set
      (e.g. ``read`` or ``read+write``).

    Returns ``{"name", "scopes"}``; the secret itself is never propagated.
    """
    if not raw:
        return None
    raw_bytes = raw.encode("utf-8")
    for entry in os.getenv("AUTH_API_KEY", "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) == 3:
            name, key, scopes = parts[0], parts[1], frozenset(parts[2].split("+"))
        else:
            name, key, scopes = None, entry, _FULL_SCOPE
        # Compare UTF-8 bytes: compare_digest on str raises TypeError for
        # non-ASCII input, which would turn a bad token into a 500.
        if hmac.compare_digest(raw_bytes, key.encode("utf-8")):
            return {"name": name, "scopes": scopes}
    return None


def _valid_token(raw: str) -> bool:
    """Kept for backward compatibility; prefer match_token."""
    return match_token(raw) is not None


class AuthMiddleware:
    """Pure-ASGI Bearer-token middleware (does not buffer SSE).

    Covers both REST and the MCP sub-app mounted via asgi_app(). No-op when
    AUTH_API_KEY is unset.

    On success the matched principal is published in ``scope["state"]["auth"]``
    (Starlette convention — surfaces as ``request.state.auth``) and in the
    ``current_auth`` contextvar (issue #15). The secret never travels.

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
        token = token_from_authorization(auth)
        principal = match_token(token) if token else None
        if principal is None:
            resp = JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await resp(scope, receive, send)

        scope.setdefault("state", {})["auth"] = principal
        current_auth.set(principal)
        return await self.app(scope, receive, send)
