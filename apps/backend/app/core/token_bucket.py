"""Token buckets: small rate-limiting primitives with an injected clock.

Nothing here reads settings or a module-level clock, so callers decide the numbers and tests drive the time:

- ``TokenBucket``: ``capacity`` tokens, refilled continuously at ``capacity / per_seconds`` tokens per
  second; it starts full. Synchronous on purpose (no ``await`` inside), hence atomic under asyncio.
- ``KeyedTokenBuckets``: one ``TokenBucket`` per key (for example per client), with a hard cap on how many
  keys are tracked; the least recently used key is dropped first. A dropped key comes back with a full
  bucket, which only helps whoever floods the structure with more than ``max_keys`` distinct keys, and
  each of those keys already owns a full bucket anyway.
- ``ClientAndGlobalBudget``: a ``KeyedTokenBuckets`` share per client plus one global ``TokenBucket``; a call
  must fit in both.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable, Mapping

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


# Why ``ClientAndGlobalBudget.try_acquire`` refused. Plain strings so callers can count and log them as is.
REFUSED_BY_CLIENT = "client"
REFUSED_BY_GLOBAL = "global"


class ClientAndGlobalBudget:
    """Admission for a call that must fit in the caller's own share AND in one bucket shared by everybody.

    ``try_acquire(client)`` takes one token from ``client``'s bucket and then one from the global bucket:

    - A client over its share is refused WITHOUT touching the global bucket, so one flooder cannot drain
      the tokens of everybody else by trying again and again.
    - If the global bucket refuses, the client's token is handed back: nobody pays for a call that did not
      go out.

    Both buckets refill continuously (``capacity`` tokens per ``per_seconds``) and start full. The number of
    tracked clients is capped (``KeyedTokenBuckets``). Synchronous like the buckets it is made of, so the
    two checks and the spending are atomic under asyncio.

    ``dedicated_capacities`` gives chosen keys their own share size (for example a key that many people share).
    Those keys live outside the capped LRU structure, so a flood of other keys can never evict them; they are
    still subject to the global bucket.
    """

    def __init__(
        self,
        per_client_capacity: float,
        global_capacity: float,
        per_seconds: float,
        clock: Callable[[], float],
        max_clients: int,
        dedicated_capacities: Mapping[str, float] | None = None,
    ) -> None:
        self._clients = KeyedTokenBuckets(per_client_capacity, per_seconds, clock, max_keys=max_clients)
        self._global = TokenBucket(global_capacity, per_seconds, clock)
        self._dedicated = {
            key: TokenBucket(capacity, per_seconds, clock)
            for key, capacity in (dedicated_capacities or {}).items()
        }

    @property
    def per_client_capacity(self) -> float:
        return self._clients.capacity

    @property
    def global_capacity(self) -> float:
        return self._global.capacity

    @property
    def max_clients(self) -> int:
        return self._clients.max_keys

    @property
    def tracked_clients(self) -> int:
        return len(self._clients)

    def try_acquire(self, client: str) -> str | None:
        """``None`` if admitted; otherwise ``REFUSED_BY_CLIENT`` or ``REFUSED_BY_GLOBAL``."""
        dedicated = self._dedicated.get(client)
        taken = dedicated.try_acquire() if dedicated is not None else self._clients.try_acquire(client)
        if taken is not None:
            return REFUSED_BY_CLIENT
        if self._global.try_acquire() is not None:
            if dedicated is not None:
                dedicated.give_back()
            else:
                self._clients.give_back(client)
            return REFUSED_BY_GLOBAL
        return None

    def give_back(self, client: str) -> None:
        """Return the client's token and the global one for a call that was admitted but then refused elsewhere."""
        dedicated = self._dedicated.get(client)
        if dedicated is not None:
            dedicated.give_back()
        else:
            self._clients.give_back(client)
        self._global.give_back()

    def reset(self) -> None:
        """Every client and the global bucket back to full, as brand new."""
        self._clients.reset()
        self._global.reset()
        for bucket in self._dedicated.values():
            bucket.reset()
