import os
import click

TEMPLATE_DIRS = ["datasource", "models", "repositories", "services", "tools", "urls"]

MAIN_PY = """\
from pythia import Server
import urls  # auto-discovery

server = Server.get_instance()

if __name__ == "__main__":
    server.start()
"""

URLS_INIT = """\
import importlib
import pkgutil

for _info in pkgutil.iter_modules(__path__):
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
    "pythia",
]
"""


@click.command()
@click.argument("name")
def new_command(name: str):
    """Create a new MCP server with the pythia structure."""
    base = os.path.join(os.getcwd(), name)

    if os.path.exists(base):
        click.echo(f"Error: directory '{name}' already exists.", err=True)
        raise SystemExit(1)

    os.makedirs(base)

    for d in TEMPLATE_DIRS:
        os.makedirs(os.path.join(base, d))
        open(os.path.join(base, d, "__init__.py"), "w").close()

    with open(os.path.join(base, "urls", "__init__.py"), "w") as f:
        f.write(URLS_INIT)

    with open(os.path.join(base, "main.py"), "w") as f:
        f.write(MAIN_PY)

    with open(os.path.join(base, "pyproject.toml"), "w") as f:
        f.write(PYPROJECT.format(name=name))

    click.echo(f"Project '{name}' created successfully.")
    click.echo(f"  cd {name} && pip install -e . && python main.py")
