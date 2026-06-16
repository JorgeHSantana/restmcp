"""Auto-discovery: importing this package imports every endpoint module.

Endpoints register themselves on the Server singleton the moment their class
body runs (`Endpoint.__init_subclass__`), so simply importing the modules is
enough — no manual route list to maintain. Drop a new `*_endpoint` file in here
and it is live on the next start.
"""

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    if not _module.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_module.name}")
