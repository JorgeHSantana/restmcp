from typing import Any, Self

from pydantic import BaseModel


class Entity(BaseModel):
    """Pydantic model for data returned by a DataSource. Subclass names must end with 'Entity'."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__name__.endswith("Entity"):
            raise TypeError(
                f"Entity subclasses must end with 'Entity' "
                f"(got: '{cls.__name__}'). Rename to '{cls.__name__}Entity'."
            )

    def serialize(self) -> dict[str, Any]:
        """JSON-safe representation (datetime → ISO 8601, Decimal → str, etc.)."""
        return self.model_dump(mode="json")

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> Self:
        """Build the entity from a dict of raw data."""
        return cls(**data)
