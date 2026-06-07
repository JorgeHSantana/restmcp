from pydantic import BaseModel


class Entity(BaseModel):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Entity"):
            raise TypeError(
                f"Subclasses de Entity devem terminar com 'Entity' "
                f"(encontrado: '{cls.__name__}'). Renomeie para '{cls.__name__}Entity'."
            )
