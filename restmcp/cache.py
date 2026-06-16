import functools
import threading
import time
from collections import OrderedDict
from typing import Callable


def _make_key(cls: type, args: tuple, kwargs: dict) -> tuple:
    """Build a cache key that is safe for non-hashable args (list/dict).

    Uses repr instead of the raw values: Repository.get(id_list=[...]) passes a
    list, which is unhashable — a tuple/hash-based key would raise
    "TypeError: unhashable type: 'list'". sorted(kwargs.items()) sorts by key
    (unique str), never comparing values, so it is always safe.

    Caveat: the key is derived from repr(), so it identifies arguments by their
    textual representation, not their identity. This is correct for the intended
    use — JSON-ish arguments (str, int, float, bool, None, and lists/dicts of
    those). Do NOT cache methods whose arguments are objects without a
    value-based __repr__ (two distinct objects with the same default
    "<Foo at 0x...>"-style repr would collide; conversely, repr including the
    address would never hit). Cache plain data, not rich objects.
    """
    return (cls.__qualname__, repr(args), repr(sorted(kwargs.items())))


def cached_method(ttl: float, maxsize: int = 128) -> Callable:
    """Cache a method's return value by (class, args, kwargs) with a TTL.

    Thread-safe (double-checked locking on the write path; the read fast-path is
    a single dict lookup). The store is bounded and self-cleaning:

    - **TTL:** entries older than `ttl` seconds are ignored on read and purged
      on the next write.
    - **maxsize:** at most `maxsize` live entries per decorated method; when the
      limit is exceeded, the oldest-inserted entry is evicted (FIFO). This caps
      memory in long-running processes — the original unbounded store grew
      forever for methods called with many distinct arguments.

    The store is per-function-definition (shared across instances of the same
    class for equal arguments). Keys are built via repr — see `_make_key` for
    the (intentional) limitation: cache plain-data arguments, not rich objects.

    Uses a monotonic clock, so it is immune to wall-clock adjustments.
    """
    if maxsize < 1:
        raise ValueError("maxsize must be >= 1")

    def decorator(fn):
        store: "OrderedDict[tuple, tuple]" = OrderedDict()  # key -> (value, expires_at)
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            key = _make_key(self.__class__, args, kwargs)
            hit = store.get(key)
            if hit is not None and hit[1] > time.monotonic():
                return hit[0]
            with lock:
                hit = store.get(key)
                if hit is not None and hit[1] > time.monotonic():
                    return hit[0]
                value = fn(self, *args, **kwargs)
                store[key] = (value, time.monotonic() + ttl)
                store.move_to_end(key)
                _evict(store, maxsize)
                return value

        return wrapper

    return decorator


def _evict(store: "OrderedDict[tuple, tuple]", maxsize: int) -> None:
    """Purge expired entries, then enforce maxsize by dropping oldest first.

    Called only under the write lock, so mutating the OrderedDict is safe.
    """
    now = time.monotonic()
    expired = [k for k, (_, exp) in store.items() if exp <= now]
    for k in expired:
        del store[k]
    while len(store) > maxsize:
        store.popitem(last=False)
