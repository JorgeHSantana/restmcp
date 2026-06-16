import click
from restmcp.cli.new import new_command


@click.group()
def app():
    """restmcp — framework for building MCP servers."""
    pass


app.add_command(new_command, name="new")
