"""Token buckets: small rate-limiting primitives with an injected clock.

Nothing here reads settings or a module-level clock, so callers decide the numbers and tests drive the time:

- ``TokenBucket``: ``capacity`` tokens, refilled continuously at ``capacity / per_seconds`` tokens per
  second; it starts full. Synchronous on purpose (no ``await`` inside), hence atomic under asyncio.
- ``KeyedTokenBuckets``: one ``TokenBucket`` per key (for example per client), with a hard cap on how many
  keys are tracked; the least recently used key is dropped first. A dropped key comes back with a full
  bucket, which only helps whoever floods the structure with more than ``max_keys`` distinct keys, and
  each of those keys already owns a full bucket anyway.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable

# Absorbs float noise so that a wait of exactly N seconds is not reported as N + 1.
_EPSILON = 1e-9


class TokenBucket:
    def __init__(self, capacity: float, per_seconds: float, clock: Callable[[], float]) -> None:
        if capacity <= 0 or per_seconds <= 0:
            raise ValueError("capacity and per_seconds must be positive")
        self._capacity = float(capacity)
        self._per_seconds = float(per_seconds)
        self._clock = clock
        self._tokens = self._capacity
        self._stamp = clock()

    @property
    def capacity(self) -> float:
        return self._capacity

    def try_acquire(self) -> float | None:
        """Take one token. ``None`` means acquired; otherwise the whole seconds (at least 1) to wait."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return None
        wait = (1.0 - self._tokens) * self._per_seconds / self._capacity
        return float(max(1, math.ceil(wait - _EPSILON)))

    def give_back(self) -> None:
        """Return a token that was taken but never used (the next refill clamps to the capacity)."""
        self._tokens += 1.0

    def reset(self) -> None:
        """Back to full, as a brand-new bucket."""
        self._tokens = self._capacity
        self._stamp = self._clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(now - self._stamp, 0.0)  # a clock that goes backwards refills nothing
        self._tokens = min(self._capacity, self._tokens + elapsed * self._capacity / self._per_seconds)
        self._stamp = now


class KeyedTokenBuckets:
    def __init__(
        self, capacity: float, per_seconds: float, clock: Callable[[], float], max_keys: int
    ) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be at least 1")
        # Validate once here so a bad configuration fails at construction, not on the first client.
        TokenBucket(capacity, per_seconds, clock)
        self._capacity = capacity
        self._per_seconds = per_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._buckets: OrderedDict[str, TokenBucket] = OrderedDict()

    @property
    def capacity(self) -> float:
        return float(self._capacity)

    @property
    def max_keys(self) -> int:
        return self._max_keys

    def __len__(self) -> int:
        return len(self._buckets)

    def try_acquire(self, key: str) -> float | None:
        """Take one token from ``key``'s bucket (created full on first use). Same result as ``TokenBucket``."""
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self._capacity, self._per_seconds, self._clock)
            self._buckets[key] = bucket
            while len(self._buckets) > self._max_keys:
                self._buckets.popitem(last=False)
        else:
            self._buckets.move_to_end(key)
        return bucket.try_acquire()

    def give_back(self, key: str) -> None:
        """Return a token to ``key``; a key that is not tracked (or was dropped) is left alone."""
        bucket = self._buckets.get(key)
        if bucket is not None:
            bucket.give_back()

    def reset(self) -> None:
        self._buckets.clear()
