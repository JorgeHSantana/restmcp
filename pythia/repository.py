from abc import ABC, abstractmethod
from pythia.datasource import DataSource


class Repository(ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Repository"):
            raise TypeError(
                f"Subclasses de Repository devem terminar com 'Repository' "
                f"(encontrado: '{cls.__name__}'). Renomeie para '{cls.__name__}Repository'."
            )

    def __init__(self):
        data_bank = getattr(self, "data_bank", None)
        if not data_bank:
            raise ValueError(f"{self.__class__.__name__}: data_bank is required")
        if not isinstance(data_bank, DataSource):
            raise ValueError(
                f"{self.__class__.__name__}: data_bank must be a DataSource instance"
            )

    @abstractmethod
    def get(self, **kwargs):
        pass
