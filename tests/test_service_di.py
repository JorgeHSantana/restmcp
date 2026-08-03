"""Issue #14 — Service DI beyond Repository.

A Service holds more than read-side repositories: webhook publishers, clocks,
pre-built aggregation sources. None of those were injectable (constructor
raised TypeError), forcing monkey-patch-after-construction in tests. Now any
declared non-callable, non-underscore class attribute can be overridden via
the constructor; Repositories keep their per-instance copy.copy; the
at-least-one-Repository discipline stays.
"""
import pytest

from restmcp import DataSource, Repository, Service


class _StubDataSource(DataSource):
    def fetch(self):
        return {}


class _ThingRepository(Repository):
    data_source = _StubDataSource()

    def get(self):
        return []


class _WebhookPublisher:          # NOT a Repository — an outbound port
    def publish(self, event):
        return ("real", event)


class ReportService(Service):
    things = _ThingRepository()
    webhook = _WebhookPublisher()
    page_size = 50                # plain config attribute

    def snapshot(self):
        return {"webhook": type(self.webhook).__name__, "page_size": self.page_size}


def test_non_repository_attribute_is_injectable():
    class FakeWebhook:
        def publish(self, event):
            return ("fake", event)

    svc = ReportService(webhook=FakeWebhook(), page_size=5)
    assert svc.snapshot() == {"webhook": "FakeWebhook", "page_size": 5}


def test_defaults_still_apply_and_repos_are_copied():
    a, b = ReportService(), ReportService()
    assert a.snapshot()["webhook"] == "_WebhookPublisher"
    assert a.things is not b.things            # per-instance copy (unchanged)
    assert a.webhook is b.webhook is ReportService.webhook  # shared default


def test_unknown_override_still_fails_loud():
    with pytest.raises(TypeError, match="unknown override"):
        ReportService(nope=1)


def test_at_least_one_repository_still_required():
    with pytest.raises(TypeError, match="Repository"):
        class NoRepoService(Service):
            webhook = _WebhookPublisher()
