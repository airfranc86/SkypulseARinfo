"""Pausa ante el 429 (corte de circuito): módulo puro, con la hora inyectable."""
from __future__ import annotations

import math
import time

import pytest

from app.core.rate_limit_pause import RateLimitPause


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def pause(clock: FakeClock) -> RateLimitPause:
    return RateLimitPause(clock=clock, default_seconds=120.0, max_retry_after=600.0, probe_window=15.0)


def test_requests_are_allowed_until_a_429_is_seen(pause: RateLimitPause) -> None:
    assert pause.allow_request() is True
    assert pause.allow_request() is True
    assert pause.remaining() == 0.0


def test_trip_blocks_for_the_default_duration(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip()
    assert pause.remaining() == pytest.approx(120.0)
    clock.advance(119.0)
    assert pause.allow_request() is False
    assert pause.remaining() == pytest.approx(1.0)


def test_after_the_pause_exactly_one_probe_goes_through(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(120.0)
    assert pause.allow_request() is True    # el pedido de prueba
    assert pause.allow_request() is False   # los demás esperan el resultado de la prueba
    assert pause.allow_request() is False


def test_a_successful_probe_reopens_traffic(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(120.0)
    assert pause.allow_request() is True
    pause.record_success()
    assert pause.allow_request() is True
    assert pause.allow_request() is True


def test_a_failed_probe_with_429_pauses_again(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(120.0)
    assert pause.allow_request() is True
    pause.trip()
    assert pause.allow_request() is False
    assert pause.remaining() == pytest.approx(120.0)
    clock.advance(120.0)
    assert pause.allow_request() is True


def test_a_probe_that_never_reports_back_does_not_block_forever(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(120.0)
    assert pause.allow_request() is True    # prueba que se cae sin avisar (timeout, cancelación)
    clock.advance(14.0)
    assert pause.allow_request() is False
    clock.advance(2.0)
    assert pause.allow_request() is True    # vencida la ventana, sale otra prueba


def test_retry_after_is_honoured_when_reasonable(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip(retry_after=30.0)
    assert pause.remaining() == pytest.approx(30.0)
    clock.advance(29.0)
    assert pause.allow_request() is False
    clock.advance(1.0)
    assert pause.allow_request() is True


def test_retry_after_at_the_cap_is_accepted(pause: RateLimitPause) -> None:
    pause.trip(retry_after=600.0)
    assert pause.remaining() == pytest.approx(600.0)


@pytest.mark.parametrize("short", [0.5, 1.0, 9.99])
def test_a_tiny_retry_after_is_floored_at_ten_seconds(pause: RateLimitPause, short: float) -> None:
    pause.trip(retry_after=short)
    assert pause.remaining() == pytest.approx(10.0)


def test_retry_after_exactly_at_the_floor_is_kept(pause: RateLimitPause) -> None:
    pause.trip(retry_after=10.0)
    assert pause.remaining() == pytest.approx(10.0)


@pytest.mark.parametrize("bad", [None, 0.0, -5.0, math.nan, math.inf, 601.0, 86400.0])
def test_unusable_retry_after_falls_back_to_the_default(pause: RateLimitPause, bad) -> None:
    pause.trip(retry_after=bad)
    assert pause.remaining() == pytest.approx(120.0)


def test_a_shorter_trip_never_shortens_a_running_pause(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip(retry_after=300.0)
    clock.advance(10.0)
    pause.trip(retry_after=20.0)
    assert pause.remaining() == pytest.approx(290.0)


def test_reset_clears_the_state_and_restores_the_clock(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip()
    pause.reset()
    assert pause.allow_request() is True
    assert pause.remaining() == 0.0


def test_reset_restores_the_clock_given_at_construction(clock: FakeClock) -> None:
    pause = RateLimitPause()
    pause.clock = clock
    pause.reset()
    assert pause.clock is time.monotonic


def test_success_without_a_pause_is_harmless(pause: RateLimitPause) -> None:
    pause.record_success()
    assert pause.allow_request() is True


def test_every_trip_starts_a_new_generation(pause: RateLimitPause) -> None:
    first = pause.generation
    pause.trip()
    assert pause.generation == first + 1
    pause.trip(retry_after=30.0)
    assert pause.generation == first + 2


def test_a_request_started_before_the_last_trip_cannot_close_the_pause(pause: RateLimitPause) -> None:
    started_before = pause.generation
    pause.trip()                                  # llegó un 429 mientras ese pedido seguía en vuelo
    pause.record_success(started_before)          # y el pedido viejo termina bien
    assert pause.remaining() == pytest.approx(120.0)
    assert pause.allow_request() is False


def test_the_probe_started_after_the_trip_closes_the_pause(pause: RateLimitPause, clock: FakeClock) -> None:
    pause.trip()
    clock.advance(120.0)
    assert pause.allow_request() is True
    probe_generation = pause.generation
    pause.record_success(probe_generation)
    assert pause.remaining() == 0.0
    assert pause.allow_request() is True


def test_an_old_request_finishing_during_the_probe_does_not_close_the_pause(
    pause: RateLimitPause, clock: FakeClock
) -> None:
    straggler = pause.generation
    pause.trip()
    clock.advance(120.0)
    assert pause.allow_request() is True          # sale la prueba
    pause.record_success(straggler)               # termina un pedido anterior al 429
    assert pause.allow_request() is False         # la prueba sigue en vuelo, la pausa sigue
