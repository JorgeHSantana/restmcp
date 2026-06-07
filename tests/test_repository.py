import pytest
from pythia.repository import Repository
from pythia.datasource import DataSource


class FakeDataSource(DataSource):
    pass


class ClientRepository(Repository):
    data_bank = FakeDataSource()

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
            data_bank = FakeDataSource()
            def get(self, **kwargs):
                pass


def test_repository_requires_data_bank():
    class NoDataBankRepository(Repository):
        def get(self, **kwargs):
            pass

    with pytest.raises(ValueError, match="data_bank"):
        NoDataBankRepository()


def test_repository_requires_datasource_instance():
    class BadDataBankRepository(Repository):
        data_bank = "nao_e_datasource"
        def get(self, **kwargs):
            pass

    with pytest.raises(ValueError, match="DataSource"):
        BadDataBankRepository()


def test_repository_get_is_abstract():
    class AbstractRepository(Repository):
        data_bank = FakeDataSource()

    with pytest.raises(TypeError):
        AbstractRepository()
