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
    prefix = pkg.__name__ + "."
    for module in pkgutil.walk_packages(pkg.__path__, prefix=prefix):
        relative = module.name[len(prefix):]
        if any(part.startswith("_") for part in relative.split(".")):
            continue
        importlib.import_module(module.name)
