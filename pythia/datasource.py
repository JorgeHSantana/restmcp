from abc import ABC


class DataSource(ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("DataSource"):
            raise TypeError(
                f"Subclasses de DataSource devem terminar com 'DataSource' "
                f"(encontrado: '{cls.__name__}'). Renomeie para '{cls.__name__}DataSource'."
            )

    def __new__(cls, *args, **kwargs):
        if cls is DataSource:
            raise TypeError("DataSource is abstract and cannot be instantiated directly.")
        return super().__new__(cls)
