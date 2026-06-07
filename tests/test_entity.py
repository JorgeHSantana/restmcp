import pytest
from pythia.entity import Entity


def test_valid_entity_subclass():
    class PersonEntity(Entity):
        name: str
        age: int

    p = PersonEntity(name="Jorge", age=30)
    assert p.name == "Jorge"
    assert p.age == 30


def test_entity_suffix_enforced():
    with pytest.raises(TypeError, match="Entity"):
        class InvalidName(Entity):
            name: str


def test_entity_is_pydantic():
    class ProductEntity(Entity):
        price: float

    with pytest.raises(Exception):
        ProductEntity(price="nao_e_numero")


def test_entity_serializes_to_dict():
    class ItemEntity(Entity):
        id: int
        label: str

    item = ItemEntity(id=1, label="test")
    data = item.model_dump()
    assert data == {"id": 1, "label": "test"}
