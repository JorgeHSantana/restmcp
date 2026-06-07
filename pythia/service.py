import copy
from abc import ABC

from pythia.repository import Repository


class Service(ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Service"):
            raise TypeError(
                f"Service subclasses must end with 'Service' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Service'."
            )

    def __init__(self, **overrides):
        seen = set()
        for klass in type(self).__mro__:
            for name, value in vars(klass).items():
                if name not in seen and isinstance(value, Repository):
                    seen.add(name)
                    setattr(self, name, overrides.get(name, copy.copy(value)))
