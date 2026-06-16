import os
import click

TEMPLATE_DIRS = ["datasource", "models", "repositories", "services", "tools", "endpoints"]

MAIN_PY = """\
import os

import uvicorn

import endpoints  # noqa: F401 — importing registers every Endpoint route
from restmcp import Server

# Serves REST at "/" and MCP at "/mcp-protocol/" from one app, with the
# FastMCP lifespan wired in. Set AUTH_API_KEY to require a Bearer token.
app = Server.get_instance().asgi_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
"""

ENDPOINTS_INIT = """\
import importlib
import pkgutil

# Auto-discovery: importing this package imports every endpoint module, which
# registers each Endpoint on the Server the moment its class body runs.
for _info in pkgutil.iter_modules(__path__):
    if not _info.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_info.name}")
"""

PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "restmcp",
    "uvicorn",
]
"""


@click.command()
@click.argument("name")
def new_command(name: str):
    """Create a new MCP server with the restmcp structure."""
    base = os.path.join(os.getcwd(), name)

    if os.path.exists(base):
        click.echo(f"Error: directory '{name}' already exists.", err=True)
        raise SystemExit(1)

    os.makedirs(base)

    for d in TEMPLATE_DIRS:
        os.makedirs(os.path.join(base, d))
        open(os.path.join(base, d, "__init__.py"), "w").close()

    with open(os.path.join(base, "endpoints", "__init__.py"), "w") as f:
        f.write(ENDPOINTS_INIT)

    with open(os.path.join(base, "main.py"), "w") as f:
        f.write(MAIN_PY)

    with open(os.path.join(base, "pyproject.toml"), "w") as f:
        f.write(PYPROJECT.format(name=name))

    click.echo(f"Project '{name}' created successfully.")
    click.echo(f"  cd {name} && pip install -e . && python main.py")
