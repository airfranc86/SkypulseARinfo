"""TokenBucket and KeyedTokenBuckets: pure rate primitives with an injected clock.

T1 - A bucket starts full, spends one token per acquire and says how long to wait when empty.
T2 - It refills continuously, never beyond its capacity, and never from a clock that goes backwards.
T3 - give_back / reset.
T4 - No reads of settings or of the real clock inside the class.
T5 - KeyedTokenBuckets: independent keys, bounded, least recently used key dropped first.
"""
from __future__ import annotations

import time

import pytest

from app.core.token_bucket import KeyedTokenBuckets, TokenBucket
from tests.conftest import FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(start=0.0)


def _drain(bucket: TokenBucket, times: int) -> None:
    for _ in range(times):
        assert bucket.try_acquire() is None


# ---------------------------------------------------------------------------
# T1 - acquire
# ---------------------------------------------------------------------------

def test_t1_starts_full_and_spends_one_token_per_acquire(clock: FakeClock):
    bucket = TokenBucket(capacity=3, per_seconds=60, clock=clock)

    _drain(bucket, 3)

    assert bucket.try_acquire() == 20.0  # one token every 20 s


def test_t1_the_wait_is_rounded_up_and_at_least_one_second(clock: FakeClock):
    bucket = TokenBucket(capacity=6, per_seconds=60, clock=clock)
    _drain(bucket, 6)

    clock.advance(9)
    assert bucket.try_acquire() == 1.0  # 0.9 token so far: 1 s to go
    clock.advance(0.95)
    assert bucket.try_acquire() == 1.0  # 0.05 s to go still reads as 1 s, never 0


def test_t1_a_fractional_wait_is_rounded_up_not_down(clock: FakeClock):
    bucket = TokenBucket(capacity=6, per_seconds=60, clock=clock)
    _drain(bucket, 6)

    clock.advance(8.5)  # 0.85 token: 1.5 s to go

    assert bucket.try_acquire() == 2.0


# ---------------------------------------------------------------------------
# T2 - refill
# ---------------------------------------------------------------------------

def test_t2_refills_continuously(clock: FakeClock):
    bucket = TokenBucket(capacity=6, per_seconds=60, clock=clock)
    _drain(bucket, 6)

    clock.advance(10)

    assert bucket.try_acquire() is None
    assert bucket.try_acquire() is not None


def test_t2_never_holds_more_than_its_capacity(clock: FakeClock):
    bucket = TokenBucket(capacity=3, per_seconds=60, clock=clock)
    _drain(bucket, 1)

    clock.advance(1_000_000)

    _drain(bucket, 3)
    assert bucket.try_acquire() is not None


def test_t2_a_clock_that_goes_backwards_neither_refills_nor_breaks(clock: FakeClock):
    clock.now = 100.0
    bucket = TokenBucket(capacity=2, per_seconds=60, clock=clock)
    _drain(bucket, 2)

    clock.now = 10.0  # backwards
    assert bucket.try_acquire() is not None

    clock.advance(30)  # from the new reading: one token (2 per 60 s)
    assert bucket.try_acquire() is None


# ---------------------------------------------------------------------------
# T3 - give_back / reset
# ---------------------------------------------------------------------------

def test_t3_give_back_returns_a_token_but_not_beyond_capacity(clock: FakeClock):
    bucket = TokenBucket(capacity=2, per_seconds=60, clock=clock)
    _drain(bucket, 2)

    bucket.give_back()
    assert bucket.try_acquire() is None
    assert bucket.try_acquire() is not None

    bucket.reset()
    bucket.give_back()
    bucket.give_back()
    _drain(bucket, 2)
    assert bucket.try_acquire() is not None


def test_t3_reset_makes_the_bucket_full_again(clock: FakeClock):
    bucket = TokenBucket(capacity=4, per_seconds=60, clock=clock)
    _drain(bucket, 4)

    bucket.reset()

    _drain(bucket, 4)


@pytest.mark.parametrize("capacity, per_seconds", [(0, 60), (-1, 60), (3, 0), (3, -5)])
def test_t3_rejects_nonsense_parameters(clock: FakeClock, capacity: float, per_seconds: float):
    with pytest.raises(ValueError):
        TokenBucket(capacity=capacity, per_seconds=per_seconds, clock=clock)


# ---------------------------------------------------------------------------
# T4 - no hidden inputs
# ---------------------------------------------------------------------------

def test_t4_only_the_injected_clock_is_read(monkeypatch, clock: FakeClock):
    def forbidden() -> float:
        raise AssertionError("TokenBucket read the real clock")

    # A context, so the forbidden clock is gone before any other fixture tears down (they read the clock).
    with monkeypatch.context() as patched:
        patched.setattr(time, "monotonic", forbidden)
        patched.setattr(time, "time", forbidden)
        bucket = TokenBucket(capacity=2, per_seconds=60, clock=clock)

        _drain(bucket, 2)
        clock.advance(30)
        assert bucket.try_acquire() is None


# ---------------------------------------------------------------------------
# T5 - keyed buckets
# ---------------------------------------------------------------------------

def test_t5_keys_are_independent(clock: FakeClock):
    buckets = KeyedTokenBuckets(capacity=2, per_seconds=60, clock=clock, max_keys=10)

    assert buckets.try_acquire("a") is None
    assert buckets.try_acquire("a") is None
    assert buckets.try_acquire("a") == 30.0
    assert buckets.try_acquire("b") is None  # b has its own share


def test_t5_give_back_only_touches_the_given_key(clock: FakeClock):
    buckets = KeyedTokenBuckets(capacity=1, per_seconds=60, clock=clock, max_keys=10)
    buckets.try_acquire("a")
    buckets.try_acquire("b")

    buckets.give_back("a")
    buckets.give_back("never-seen")  # unknown key: nothing happens, nothing is created

    assert buckets.try_acquire("a") is None
    assert buckets.try_acquire("b") is not None
    assert len(buckets) == 2


def test_t5_the_number_of_tracked_keys_is_bounded(clock: FakeClock):
    buckets = KeyedTokenBuckets(capacity=1, per_seconds=60, clock=clock, max_keys=3)

    for key in ("a", "b", "c", "d", "e"):
        buckets.try_acquire(key)

    assert len(buckets) == 3


def test_t5_the_least_recently_used_key_is_dropped_first(clock: FakeClock):
    buckets = KeyedTokenBuckets(capacity=1, per_seconds=60, clock=clock, max_keys=3)
    for key in ("a", "b", "c"):
        buckets.try_acquire(key)

    assert buckets.try_acquire("a") is not None  # touching "a" makes "b" the least recent
    buckets.try_acquire("d")  # evicts "b"

    assert buckets.try_acquire("a") is not None  # "a" kept its spent bucket
    assert buckets.try_acquire("b") is None  # "b" was dropped: it starts full again


def test_t5_reset_forgets_every_key(clock: FakeClock):
    buckets = KeyedTokenBuckets(capacity=1, per_seconds=60, clock=clock, max_keys=3)
    buckets.try_acquire("a")

    buckets.reset()

    assert len(buckets) == 0
    assert buckets.try_acquire("a") is None
