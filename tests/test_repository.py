import pytest
from pythia.repository import Repository
from pythia.datasource import DataSource


class FakeDataSource(DataSource):
    pass


class ClientRepository(Repository):
    data_source = FakeDataSource()

    def get(self, **kwargs):
        return {"id": 1}


def test_valid_repository():
    repo = ClientRepository()
    assert repo is not None


def test_repository_get_returns_data():
    repo = ClientRepository()
    assert repo.get() == {"id": 1}


def test_repository_suffix_enforced():
    with pytest.raises(TypeError, match="Repository"):
        class InvalidName(Repository):
            data_source = FakeDataSource()
            def get(self, **kwargs):
                pass


def test_repository_requires_data_source():
    class NoDataSourceRepository(Repository):
        def get(self, **kwargs):
            pass

    with pytest.raises(ValueError, match="data_source"):
        NoDataSourceRepository()


def test_repository_requires_datasource_instance():
    class BadDataSourceRepository(Repository):
        data_source = "not_a_datasource"
        def get(self, **kwargs):
            pass

    with pytest.raises(ValueError, match="DataSource"):
        BadDataSourceRepository()


def test_repository_get_is_abstract():
    class AbstractRepository(Repository):
        data_source = FakeDataSource()

    with pytest.raises(TypeError):
        AbstractRepository()


def test_repository_injectable_data_source():
    class MockDataSource(DataSource):
        def fetch(self):
            return {"mock": True}

    class ClientRepository(Repository):
        data_source = FakeDataSource()
        def get(self, **kwargs):
            return self.data_source.fetch()

    mock = MockDataSource()
    repo = ClientRepository(data_source=mock)
    assert repo.data_source is mock


def test_repository_default_data_source_is_copied():
    class ClientRepository(Repository):
        data_source = FakeDataSource()
        def get(self, **kwargs):
            pass

    repo1 = ClientRepository()
    repo2 = ClientRepository()
    assert repo1.data_source is not repo2.data_source
    assert repo1.data_source is not ClientRepository.data_source
