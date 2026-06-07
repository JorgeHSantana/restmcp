import click
from pythia.cli.new import new_command


@click.group()
def app():
    """pythia — framework for building MCP servers."""
    pass


app.add_command(new_command, name="new")
