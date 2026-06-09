import copy
from abc import ABC, abstractmethod

from restmcp.datasource import DataSource


class Repository(ABC):
    """Data access layer. Wraps a DataSource and exposes a get() method. Subclass names must end with 'Repository'."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Repository"):
            raise TypeError(
                f"Repository subclasses must end with 'Repository' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Repository'."
            )

    def __init__(self, data_source: DataSource = None):
        if data_source is not None:
            resolved = data_source
        else:
            default = getattr(type(self), "data_source", None)
            resolved = copy.copy(default)

        if not resolved:
            raise ValueError(f"{self.__class__.__name__}: data_source is required")
        if not isinstance(resolved, DataSource):
            raise ValueError(
                f"{self.__class__.__name__}: data_source must be a DataSource instance"
            )
        self.data_source = resolved

    @abstractmethod
    def get(self, **kwargs):
        pass
