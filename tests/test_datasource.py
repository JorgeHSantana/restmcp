import pytest
from restmcp.datasource import DataSource


def test_valid_datasource_subclass():
    class MyDataSource(DataSource):
        pass
    assert issubclass(MyDataSource, DataSource)


def test_datasource_suffix_enforced():
    with pytest.raises(TypeError, match="DataSource"):
        class InvalidName(DataSource):
            pass


def test_datasource_is_abstract():
    with pytest.raises(TypeError):
        DataSource()


def test_datasource_can_be_instantiated_via_subclass():
    class ValidDataSource(DataSource):
        def __init__(self):
            self.connected = True

    ds = ValidDataSource()
    assert ds.connected is True
