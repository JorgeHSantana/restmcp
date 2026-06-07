from abc import ABC


class DataSource(ABC):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("DataSource"):
            raise TypeError(
                f"DataSource subclasses must end with 'DataSource' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}DataSource'."
            )

    def __new__(cls, *args, **kwargs):
        if cls is DataSource:
            raise TypeError("DataSource is abstract and cannot be instantiated directly.")
        return super().__new__(cls)
