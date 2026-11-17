"""Caller identity — shows `current_auth` + `required_scope` (0.5.0, #15/#16).

With ``AUTH_API_KEY`` set, the matched key's principal ``{"name", "scopes"}``
is published in the ``restmcp.auth.current_auth`` contextvar and reaches the
callback on BOTH transports — REST and MCP ``tools/call`` — including a plain
``def`` callback like this one, which runs in a worker thread
(``run_callback`` copies the context across the hop; issue #16).

Try it with ``AUTH_API_KEY="painel:sk_read:read,campo:sk_full:read+write"``:

- ``Bearer sk_read``  -> ``{"who": "painel", "scopes": ["read"]}``
- ``Bearer sk_full``  -> ``{"who": "campo",  "scopes": ["read", "write"]}``
- auth disabled       -> ``{"who": null, "scopes": []}`` (no principal)

``required_scope = "read"`` is enforced before the callback on both transports:
REST answers 403 ``ForbiddenError`` for a key without it, an MCP ``tools/call``
answers ``isError`` with the same envelope (``code: "forbidden_scope"``).
"""

from restmcp import Endpoint

from services.identity import IdentityService


class WhoamiEndpoint(Endpoint):
    required_scope = "read"
    url = "/api/whoami"
    method = "GET"

    def callback(self) -> dict:
        """Identify the API key that authenticated this call.

        Returns: {"who": key name or null, "scopes": sorted scope list} —
        both empty when authentication is disabled.
        """
        return IdentityService().describe_caller()
