import os
import pytest
from click.testing import CliRunner
from restmcp.cli import app


@pytest.fixture
def runner():
    return CliRunner()


def test_new_creates_directory(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, ["new", "meu-server"])
        assert result.exit_code == 0
        assert os.path.isdir("meu-server")


def test_new_creates_expected_dirs(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        for d in ["datasource", "models", "repositories", "services", "tools", "endpoints"]:
            assert os.path.isdir(f"meu-server/{d}"), f"Missing dir: {d}"


def test_new_creates_init_files(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        for d in ["datasource", "models", "repositories", "services", "tools", "endpoints"]:
            assert os.path.isfile(f"meu-server/{d}/__init__.py"), f"Missing __init__.py in {d}"


def test_new_creates_main_py(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        assert os.path.isfile("meu-server/main.py")
        content = open("meu-server/main.py").read()
        assert "Server" in content
        assert "import endpoints" in content
        assert "asgi_app" in content


def test_new_creates_pyproject_toml(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(app, ["new", "meu-server"])
        assert os.path.isfile("meu-server/pyproject.toml")
        content = open("meu-server/pyproject.toml").read()
        assert "meu-server" in content
        assert '"restmcp"' in content      # depends on the real package, not "pythia"
        assert '"pythia"' not in content


def test_new_fails_if_directory_exists(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        os.makedirs("meu-server")
        result = runner.invoke(app, ["new", "meu-server"])
        assert result.exit_code != 0
