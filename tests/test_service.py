import pytest
from pythia.service import Service
from pythia.repository import Repository
from pythia.datasource import DataSource


class FakeDataSource(DataSource):
    pass


class FakeRepository(Repository):
    data_source = FakeDataSource()

    def get(self, **kwargs):
        return {"fake": True}


class MockRepository(Repository):
    data_source = FakeDataSource()

    def get(self, **kwargs):
        return {"mock": True}


def test_service_suffix_enforced():
    with pytest.raises(TypeError, match="Service"):
        class Invalid(Service):
            pass


def test_service_instantiation():
    class SimpleService(Service):
        pass

    svc = SimpleService()
    assert svc is not None


def test_service_auto_discovers_repository():
    class DiagnosticService(Service):
        repo = FakeRepository()

    svc = DiagnosticService()
    assert isinstance(svc.repo, FakeRepository)


def test_service_repository_is_copied():
    class DiagnosticService(Service):
        repo = FakeRepository()

    svc1 = DiagnosticService()
    svc2 = DiagnosticService()
    assert svc1.repo is not svc2.repo
    assert svc1.repo is not DiagnosticService.repo


def test_service_injectable_repository():
    class DiagnosticService(Service):
        repo = FakeRepository()

    mock = MockRepository()
    svc = DiagnosticService(repo=mock)
    assert svc.repo is mock


def test_service_multiple_repositories():
    class MultiService(Service):
        repo_a = FakeRepository()
        repo_b = FakeRepository()

    svc = MultiService()
    assert isinstance(svc.repo_a, FakeRepository)
    assert isinstance(svc.repo_b, FakeRepository)
    assert svc.repo_a is not svc.repo_b


def test_service_partial_override():
    class MultiService(Service):
        repo_a = FakeRepository()
        repo_b = FakeRepository()

    mock = MockRepository()
    svc = MultiService(repo_a=mock)
    assert svc.repo_a is mock
    assert isinstance(svc.repo_b, FakeRepository)
    assert svc.repo_b is not MultiService.repo_b


def test_service_without_repositories():
    class PureService(Service):
        def execute(self):
            return {"pure": True}

    svc = PureService()
    assert svc.execute() == {"pure": True}


def test_service_execute_uses_injected_repository():
    class BatteryService(Service):
        repo = FakeRepository()

        def execute(self, client_id: str):
            return self.repo.get(client_id=client_id)

    mock = MockRepository()
    result = BatteryService(repo=mock).execute(client_id="123")
    assert result == {"mock": True}
