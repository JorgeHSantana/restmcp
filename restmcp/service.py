import copy
from abc import ABC

from restmcp.repository import Repository


class Service(ABC):
    """Business logic layer. Auto-discovers and copies Repository class attributes with DI support. Subclass names must end with 'Service'."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Service"):
            raise TypeError(
                f"Service subclasses must end with 'Service' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Service'."
            )
        has_repo = any(
            isinstance(v, Repository)
            for klass in cls.__mro__
            if klass not in (Service, object)
            for v in vars(klass).values()
        )
        if not has_repo:
            raise TypeError(
                f"{cls.__name__}: must define at least one Repository instance "
                f"as a class attribute."
            )

    def __init__(self, **overrides):
        seen = set()
        for klass in type(self).__mro__:
            for name, value in vars(klass).items():
                if name not in seen and isinstance(value, Repository):
                    seen.add(name)
                    setattr(self, name, overrides.get(name, copy.copy(value)))
