"""Telemetry diagnostics server — REST + MCP from one codebase.

Run it:
    cd examples/telemetry
    pip install -r requirements.txt
    python main.py

Then:
    curl http://localhost:8000/health
    curl http://localhost:8000/mcp/tools
    curl -X POST http://localhost:8000/api/check-battery -H 'content-type: application/json' -d '{}'

MCP clients connect to  http://localhost:8000/mcp-protocol
See README.md for auth and the full request catalog.
"""

import os

import uvicorn

# Importing the package runs every endpoint module, which registers each
# Endpoint on the Server singleton at class-definition time.
import endpoints  # noqa: F401  (import has the side effect of registering routes)
from restmcp import Server


def build_app():
    server = Server.get_instance()
    # asgi_app() mounts REST at "/" and MCP at mcp_path on ONE app, and wires the
    # FastMCP lifespan into the parent (mounting MCP manually raises
    # "Task group is not initialized"). If AUTH_API_KEY is set, it also wraps
    # everything in the auth middleware (/health and /mcp/tools stay public).
    return server.asgi_app(mcp_path="/mcp-protocol")


# Module-level `app` so `uvicorn main:app` works too.
app = build_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    if os.getenv("AUTH_API_KEY"):
        print("auth: ON (send 'Authorization: Bearer <key>')")
    else:
        print("auth: OFF (set AUTH_API_KEY to require a token)")
    uvicorn.run(app, host="0.0.0.0", port=port)
