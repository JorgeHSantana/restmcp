import time
import threading
import functools
from typing import Callable


def _make_key(cls: type, args: tuple, kwargs: dict) -> tuple:
    """Cache key stable and safe for non-hashable args (list/dict).

    Uses repr instead of tuple/hash: Repository.get(id_list=[...]) passes a
    list, which is not hashable — a key based on tuple/hash would raise
    TypeError: unhashable type: 'list'. sorted(kwargs.items()) sorts by key
    (unique str), never comparing values, so it is always safe.
    """
    return (cls.__qualname__, repr(args), repr(sorted(kwargs.items())))


def cached_method(ttl: float) -> Callable:
    """Cache a method's return value by (class, args, kwargs) with TTL.

    Thread-safe (double-checked locking). Key uses repr — tolerant of
    non-hashable args (list, dict) — safe for filtered methods like
    Repository.get(id_list=...).

    The store is per-function-definition (shared across instances of the same
    class for the same args). Expired entries are not evicted — they are
    ignored on read. See PR notes for eviction and aliasing trade-offs.
    """
    def decorator(fn):
        store: dict = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            key = _make_key(self.__class__, args, kwargs)
            now = time.time()
            hit = store.get(key)
            if hit is not None and now - hit[1] < ttl:
                return hit[0]
            with lock:
                hit = store.get(key)
                if hit is not None and now - hit[1] < ttl:
                    return hit[0]
                value = fn(self, *args, **kwargs)
                store[key] = (value, time.time())
                return value
        return wrapper
    return decorator
