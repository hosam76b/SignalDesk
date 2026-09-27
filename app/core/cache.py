"""Small in-process TTL cache for expensive read-only aggregates.

Scope
-----
Deliberately process-local and synchronous. This is not a distributed cache and
not a place to put request-scoped data:

* Values must be cheap to rebuild and safe to share between users. Only
  aggregates that are identical for every operator belong here -- never a row
  filtered by topic or role, unless the key includes that scope.
* Entries are per-process, so with multiple workers each keeps its own copy.
  That is fine for a display cache: it trades a little memory for removing
  repeated aggregate scans.

Expiry is lazy plus a bounded size: a stale entry is still returned by
``get`` only until its deadline passes, and the oldest insertion is evicted once
``maxsize`` is exceeded, so a key space that grows with user input cannot leak.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class TTLCache:
    """Thread-safe bounded cache with per-entry deadlines."""

    def __init__(self, maxsize: int = 128) -> None:
        self._maxsize = max(1, int(maxsize))
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> tuple[bool, Any]:
        """Return ``(hit, value)``; ``value`` is ``None`` when absent or expired."""
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return False, None
            expires_at, value = entry
            if expires_at <= now:
                del self._entries[key]
                self.misses += 1
                return False, None
            self._entries.move_to_end(key)
            self.hits += 1
            return True, value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        ttl = float(ttl_seconds)
        if ttl <= 0:
            # A zero/negative TTL disables caching rather than caching forever.
            self.invalidate(key)
            return
        with self._lock:
            self._entries[key] = (time.monotonic() + ttl, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)

    def get_or_set(self, key: str, ttl_seconds: float, factory: Callable[[], T]) -> T:
        hit, value = self.get(key)
        if hit:
            return value  # type: ignore[return-value]
        value = factory()
        self.set(key, value, ttl_seconds)
        return value  # type: ignore[return-value]

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._entries),
                "maxsize": self._maxsize,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
            }
