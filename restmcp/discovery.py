import importlib
import pkgutil


def autodiscover(package: str) -> None:
    """Import every public module in ``package`` (recursively) so its Endpoints register.

    Endpoints register themselves on the ``Server`` singleton the moment their
    class body runs (``Endpoint.__init_subclass__``); importing the module is
    what triggers that. Call this once on your endpoints package and every file
    in it — including files inside subpackages — goes live: drop in a new
    ``*.py`` and it is picked up on the next start, with no list to maintain.

    This replaces the hand-written import loop that used to live in the
    generated ``endpoints/__init__.py``: that file can now be empty.

    Modules or subpackages whose name starts with ``_`` are skipped.
    """
    pkg = importlib.import_module(package)
    if not hasattr(pkg, "__path__"):
        raise ValueError(f"{package!r} is not a package (has no __path__)")

    # Walk manually rather than with pkgutil.walk_packages: walk_packages
    # imports every subpackage (running its __init__) to descend into it,
    # which would execute _private subpackages before we could skip them.
    # Pruning `_`-prefixed names here keeps them from ever being imported.
    def _walk(search_paths, prefix: str) -> None:
        for module in pkgutil.iter_modules(search_paths):
            if module.name.startswith("_"):
                continue
            full_name = f"{prefix}{module.name}"
            mod = importlib.import_module(full_name)
            if module.ispkg:
                _walk(mod.__path__, f"{full_name}.")

    _walk(pkg.__path__, pkg.__name__ + ".")
