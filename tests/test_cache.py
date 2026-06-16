import time
from restmcp import cached_method


class Svc:
    def __init__(self):
        self.calls = 0

    @cached_method(ttl=60)
    def get(self, x):
        self.calls += 1
        return x * 10


def test_caches_by_args():
    s = Svc()
    assert s.get(1) == 10 and s.get(1) == 10
    assert s.calls == 1                 # 2nd call served from cache
    assert s.get(2) == 20               # different arg -> different key
    assert s.calls == 2


def test_ttl_expires():
    class S2:
        def __init__(self): self.calls = 0
        @cached_method(ttl=0.05)
        def get(self):
            self.calls += 1; return 1
    s = S2(); s.get(); time.sleep(0.07); s.get()
    assert s.calls == 2


def test_caches_non_hashable_args():
    """Motivating case from the issue: Repository.get(id_list=[...]). A list is
    NOT hashable — a hash/tuple-based key would raise TypeError here."""
    class S3:
        def __init__(self): self.calls = 0
        @cached_method(ttl=60)
        def get(self, ids):
            self.calls += 1
            return sum(ids)
    s = S3()
    assert s.get([1, 2, 3]) == 6
    assert s.get([1, 2, 3]) == 6        # 2nd from cache, no "unhashable type: 'list'"
    assert s.calls == 1
    assert s.get([1, 2]) == 3           # different list -> different key
    assert s.calls == 2


def test_maxsize_evicts_oldest():
    """The store is bounded: past maxsize, the oldest entry is dropped (FIFO)."""
    class S4:
        def __init__(self): self.calls = 0
        @cached_method(ttl=60, maxsize=2)
        def get(self, x):
            self.calls += 1
            return x
    s = S4()
    s.get(1); s.get(2)          # store: {1, 2}, 2 misses
    assert s.calls == 2
    s.get(2)                    # hit, store unchanged
    assert s.calls == 2
    s.get(3)                    # store full -> evict oldest (1); store: {2, 3}
    assert s.calls == 3
    s.get(1)                    # 1 was evicted -> recompute
    assert s.calls == 4


def test_invalid_maxsize_rejected():
    import pytest
    with pytest.raises(ValueError):
        @cached_method(ttl=1, maxsize=0)
        def _f(self):  # pragma: no cover - never called
            return 1
