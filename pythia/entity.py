from pydantic import BaseModel


class Entity(BaseModel):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Entity"):
            raise TypeError(
                f"Entity subclasses must end with 'Entity' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Entity'."
            )
