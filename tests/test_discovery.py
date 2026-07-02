import sys
import textwrap

import pytest

from restmcp import autodiscover


def _make_pkg(tmp_path, name, modules):
    """Write a package `name` with the given {module: source} and put it on sys.path."""
    pkg_dir = tmp_path / name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    for mod_name, src in modules.items():
        (pkg_dir / f"{mod_name}.py").write_text(textwrap.dedent(src))
    sys.path.insert(0, str(tmp_path))
    return pkg_dir


def test_autodiscover_imports_public_modules(tmp_path, monkeypatch):
    _make_pkg(
        tmp_path,
        "eps_public",
        {
            "alpha": "imported = True\nMARK_ALPHA = object()",
            "beta": "MARK_BETA = object()",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    autodiscover("eps_public")

    assert "eps_public.alpha" in sys.modules
    assert "eps_public.beta" in sys.modules


def test_autodiscover_skips_underscore_modules(tmp_path, monkeypatch):
    _make_pkg(
        tmp_path,
        "eps_private",
        {
            "visible": "X = 1",
            "_hidden": "raise RuntimeError('this module must not be imported')",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    autodiscover("eps_private")  # must not raise

    assert "eps_private.visible" in sys.modules
    assert "eps_private._hidden" not in sys.modules


def test_autodiscover_rejects_non_package():
    with pytest.raises(ValueError):
        autodiscover("os.path")  # a module, not a package


def test_autodiscover_recurses_into_subpackages(tmp_path, monkeypatch):
    import sys

    from restmcp.discovery import autodiscover

    pkg = tmp_path / "eps_recursion_pkg"
    sub = pkg / "admin"
    sub.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (sub / "__init__.py").write_text("")
    (sub / "nested_mod.py").write_text("LOADED = True\n")
    (sub / "_private_mod.py").write_text("raise AssertionError('must be skipped')\n")

    monkeypatch.syspath_prepend(str(tmp_path))
    autodiscover("eps_recursion_pkg")

    assert "eps_recursion_pkg.admin.nested_mod" in sys.modules
    assert "eps_recursion_pkg.admin._private_mod" not in sys.modules
