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
        # Issue #14: a Service holds more than repositories (webhook publisher,
        # clock, pre-built aggregation source). Every declared non-callable,
        # non-underscore class attribute is injectable via the constructor —
        # otherwise tests are forced into monkey patching after construction.
        # Repositories keep the per-instance copy.copy; other attributes stay
        # shared class defaults unless overridden. The at-least-one-Repository
        # rule (__init_subclass__) is unchanged: this widens injection, not
        # the layer discipline.
        seen = set()
        remaining = dict(overrides)
        for klass in type(self).__mro__:
            if klass in (Service, object):
                continue
            for name, value in vars(klass).items():
                if name.startswith("_") or name in seen or callable(value):
                    continue
                seen.add(name)
                if name in remaining:
                    setattr(self, name, remaining.pop(name))
                elif isinstance(value, Repository):
                    setattr(self, name, copy.copy(value))
        if remaining:
            raise TypeError(
                f"{type(self).__name__}: unknown override(s) {sorted(remaining)} — "
                f"known attributes: {sorted(seen)}"
            )
