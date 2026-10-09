"""TokenBucket and KeyedTokenBuckets: pure rate primitives with an injected clock.

T1 - A bucket starts full, spends one token per acquire and says how long to wait when empty.
T2 - It refills continuously, never beyond its capacity, and never from a clock that goes backwards.
T3 - give_back / reset.
T4 - No reads of settings or of the real clock inside the class.
T5 - KeyedTokenBuckets: independent keys, bounded, least recently used key dropped first.
T6 - ClientAndGlobalBudget: one token from the caller's own share AND one from a shared bucket.
"""
from __future__ import annotations

import time

import pytest

from app.core.token_bucket import (
    REFUSED_BY_CLIENT,
    REFUSED_BY_GLOBAL,
    ClientAndGlobalBudget,
    KeyedTokenBuckets,
    TokenBucket,
)
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


# ---------------------------------------------------------------------------
# T6 - a client share AND a global bucket
# ---------------------------------------------------------------------------

def _budget(clock: FakeClock, *, share: float = 3, overall: float = 6, max_clients: int = 100):
    return ClientAndGlobalBudget(
        per_client_capacity=share,
        global_capacity=overall,
        per_seconds=60,
        clock=clock,
        max_clients=max_clients,
    )


def test_t6_the_reasons_are_stable_strings():
    assert REFUSED_BY_CLIENT == "client"
    assert REFUSED_BY_GLOBAL == "global"


def test_t6_admits_until_the_clients_share_is_spent_then_says_client(clock: FakeClock):
    budget = _budget(clock, share=3, overall=6)

    assert [budget.try_acquire("a") for _ in range(3)] == [None, None, None]
    assert budget.try_acquire("a") == REFUSED_BY_CLIENT


def test_t6_a_client_over_its_share_does_not_spend_global_tokens(clock: FakeClock):
    budget = _budget(clock, share=3, overall=6)
    for _ in range(3):
        budget.try_acquire("a")

    refusals = [budget.try_acquire("a") for _ in range(10)]  # a keeps trying

    assert set(refusals) == {REFUSED_BY_CLIENT}
    assert [budget.try_acquire("b") for _ in range(3)] == [None, None, None]  # b still has 3 global tokens


def test_t6_the_global_bucket_is_shared_by_every_client(clock: FakeClock):
    budget = _budget(clock, share=5, overall=6)
    assert [budget.try_acquire("a") for _ in range(5)] == [None] * 5

    assert budget.try_acquire("b") is None  # the sixth and last global token
    assert budget.try_acquire("b") == REFUSED_BY_GLOBAL
    assert budget.try_acquire("c") == REFUSED_BY_GLOBAL


def test_t6_a_global_refusal_gives_the_clients_token_back(clock: FakeClock):
    budget = _budget(clock, share=2, overall=3)
    budget.try_acquire("a")
    budget.try_acquire("a")  # a: share spent, 1 global token left
    assert budget.try_acquire("b") is None  # global spent, b has 1 token left
    assert budget.try_acquire("b") == REFUSED_BY_GLOBAL  # refused by global: b's token must come back

    clock.advance(20)  # one global token is back (3 per 60 s); b's share refilled by 2/60 * 20

    assert budget.try_acquire("b") is None  # b's share was never charged for the refused call
    assert budget.try_acquire("c") == REFUSED_BY_GLOBAL  # and that call spent the one global token


def test_t6_both_buckets_refill_with_the_clock(clock: FakeClock):
    budget = _budget(clock, share=3, overall=6)
    for _ in range(3):
        budget.try_acquire("a")
    assert budget.try_acquire("a") == REFUSED_BY_CLIENT

    clock.advance(19)  # 3 per 60 s is one token per 20 s: not yet
    assert budget.try_acquire("a") == REFUSED_BY_CLIENT
    clock.advance(2)
    assert budget.try_acquire("a") is None
    assert budget.try_acquire("a") == REFUSED_BY_CLIENT


def test_t6_the_number_of_tracked_clients_is_bounded(clock: FakeClock):
    budget = _budget(clock, share=1, overall=1_000, max_clients=3)

    for key in ("a", "b", "c", "d", "e"):
        budget.try_acquire(key)

    assert budget.tracked_clients == 3
    assert budget.max_clients == 3


def test_t6_reset_gives_everybody_a_full_share_and_a_full_global_bucket(clock: FakeClock):
    budget = _budget(clock, share=1, overall=2)
    budget.try_acquire("a")
    budget.try_acquire("b")
    assert budget.try_acquire("c") == REFUSED_BY_GLOBAL

    budget.reset()

    assert budget.tracked_clients == 0
    assert budget.try_acquire("a") is None
    assert budget.try_acquire("b") is None


def test_t6_exposes_the_capacities_it_was_built_with(clock: FakeClock):
    budget = _budget(clock, share=3, overall=6)

    assert budget.per_client_capacity == 3.0
    assert budget.global_capacity == 6.0


@pytest.mark.parametrize(
    "share, overall, max_clients",
    [(0, 6, 10), (3, 0, 10), (-1, 6, 10), (3, 6, 0)],
)
def test_t6_rejects_nonsense_parameters(clock: FakeClock, share: float, overall: float, max_clients: int):
    with pytest.raises(ValueError):
        _budget(clock, share=share, overall=overall, max_clients=max_clients)


# ---------------------------------------------------------------------------
# T7 - clients with a dedicated (larger) share
# ---------------------------------------------------------------------------

def _dedicated_budget(clock: FakeClock, *, overall: float = 10):
    return ClientAndGlobalBudget(
        per_client_capacity=2,
        global_capacity=overall,
        per_seconds=60,
        clock=clock,
        max_clients=100,
        dedicated_capacities={"shared": 5},
    )


def test_t7_a_dedicated_key_gets_its_own_capacity_and_the_rest_keep_the_normal_one(clock: FakeClock):
    budget = _dedicated_budget(clock)

    assert [budget.try_acquire("shared") for _ in range(5)] == [None] * 5
    assert budget.try_acquire("shared") == REFUSED_BY_CLIENT
    assert [budget.try_acquire("alice") for _ in range(2)] == [None, None]
    assert budget.try_acquire("alice") == REFUSED_BY_CLIENT


def test_t7_a_dedicated_key_is_still_bounded_by_the_global_bucket(clock: FakeClock):
    budget = _dedicated_budget(clock, overall=6)
    assert [budget.try_acquire("shared") for _ in range(5)] == [None] * 5

    assert budget.try_acquire("alice") is None  # the sixth and last global token
    assert budget.try_acquire("shared") == REFUSED_BY_CLIENT  # its own share is spent first
    assert budget.try_acquire("bob") == REFUSED_BY_GLOBAL


def test_t7_a_global_refusal_gives_the_dedicated_token_back(clock: FakeClock):
    budget = _dedicated_budget(clock, overall=5)
    assert budget.try_acquire("alice") is None  # global: 4 left
    assert [budget.try_acquire("shared") for _ in range(4)] == [None] * 4  # global spent, 1 token of 5 left
    assert budget.try_acquire("shared") == REFUSED_BY_GLOBAL  # must hand its token back

    clock.advance(12)  # one global token (5 per 60 s) and one token of the dedicated share

    assert budget.try_acquire("shared") is None
    assert budget.try_acquire("shared") == REFUSED_BY_GLOBAL  # it still had a token: the refusal is the global's


def test_t7_dedicated_keys_do_not_count_as_tracked_clients_and_survive_eviction(clock: FakeClock):
    budget = ClientAndGlobalBudget(
        per_client_capacity=1, global_capacity=100, per_seconds=60, clock=clock, max_clients=2,
        dedicated_capacities={"shared": 3},
    )
    budget.try_acquire("shared")
    for key in ("a", "b", "c", "d"):
        budget.try_acquire(key)

    assert budget.tracked_clients == 2
    assert [budget.try_acquire("shared") for _ in range(2)] == [None, None]  # kept its spent bucket
    assert budget.try_acquire("shared") == REFUSED_BY_CLIENT


def test_t7_reset_refills_the_dedicated_bucket(clock: FakeClock):
    budget = _dedicated_budget(clock)
    for _ in range(5):
        budget.try_acquire("shared")

    budget.reset()

    assert [budget.try_acquire("shared") for _ in range(5)] == [None] * 5


def test_t7_rejects_a_nonsense_dedicated_capacity(clock: FakeClock):
    with pytest.raises(ValueError):
        ClientAndGlobalBudget(
            per_client_capacity=2, global_capacity=10, per_seconds=60, clock=clock, max_clients=10,
            dedicated_capacities={"shared": 0},
        )
