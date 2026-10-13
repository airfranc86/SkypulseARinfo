"""Phase 2c-1: values derived from other requests (`fetch_derived` / `fetch_derived_or_raise`), and the raising form
of `fetch_series` that their `compute` calls.

A derived value (the multi-model consensus) makes no request of its own: it is cached under a synthetic key at one
cache level, and the series it is computed from keep their own entries. A refusal of one of those series reaches the
caller as `FetchRefused` so a degraded value is never cached. The fake source comes from
`tests/openmeteo_fake_source.py`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

import app.services.openmeteo as om_module
import app.services.openmeteo_source as source_module
from app.core.cache import CacheOutcome, FetchRefused
from app.services.openmeteo_source import (
    CacheLevel,
    CacheNotBoundError,
    SeriesRequest,
    cache_key,
    fetch_derived,
    fetch_derived_or_raise,
    fetch_series,
    fetch_series_or_raise,
)
from tests._om_payloads import _DAILY_EXT_PAYLOAD
from tests.openmeteo_fake_source import (  # noqa: F401  (fixtures are used by name)
    LAT,
    LON,
    clock,
    install,
    own_caches,
)
from tests.openmeteo_fake_source import parse_value as _parse_value
from tests.openmeteo_fake_source import series_request as _request


# ---------------------------------------------------------------------------
# fetch_derived: a value computed from other cached requests
# ---------------------------------------------------------------------------

DERIVED_KEY = {"latitude": LAT, "longitude": LON, "forecast_days": 7, "models": "a,b"}


class Compute:
    """A `compute` that counts its calls and answers in order (the last answer repeats); an exception instance is raised."""

    def __init__(self, *answers: object) -> None:
        self._answers = list(answers) or [None]
        self.calls = 0

    async def __call__(self) -> Any:
        answer = self._answers[min(self.calls, len(self._answers) - 1)]
        self.calls += 1
        if isinstance(answer, BaseException):
            raise answer
        return answer


async def test_a_derived_value_is_computed_once_and_then_served_from_its_cache() -> None:
    compute = Compute({"v": 1})
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) == {"v": 1}
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) == {"v": 1}
    assert compute.calls == 1


async def test_a_derived_value_lives_in_the_cache_of_the_level_asked(own_caches) -> None:
    await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, Compute({"v": 1}))
    held = {level: list(cache._cache) for level, cache in own_caches.caches.items()}
    assert held == {CacheLevel.CURRENT: [], CacheLevel.FORECAST: [cache_key(DERIVED_KEY)], CacheLevel.NOWCAST: []}


async def test_the_derived_key_rounds_the_coordinates_like_a_series_key() -> None:
    compute = Compute({"v": 1})
    await fetch_derived({**DERIVED_KEY, "latitude": -31.404}, CacheLevel.FORECAST, compute)
    await fetch_derived({**DERIVED_KEY, "latitude": -31.396}, CacheLevel.FORECAST, compute)   # same 2-decimal cell
    assert compute.calls == 1
    await fetch_derived({**DERIVED_KEY, "forecast_days": 5}, CacheLevel.FORECAST, compute)    # another input: another entry
    assert compute.calls == 2


async def test_a_derived_value_is_not_persisted_unless_asked(own_caches) -> None:
    await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, Compute({"v": 1}))
    await fetch_derived({**DERIVED_KEY, "models": "kept"}, CacheLevel.FORECAST, Compute({"v": 2}), persist=True)
    await own_caches.caches[CacheLevel.FORECAST].flush_persistence()
    assert own_caches.backend.saved == [cache_key({**DERIVED_KEY, "models": "kept"})]


async def test_the_or_raise_form_does_not_persist_by_default_either(own_caches) -> None:
    await fetch_derived_or_raise(DERIVED_KEY, CacheLevel.FORECAST, Compute({"v": 1}))
    await own_caches.caches[CacheLevel.FORECAST].flush_persistence()
    assert own_caches.backend.saved == []


async def test_an_unpersisted_derived_value_does_not_read_the_backend_when_compute_has_nothing(own_caches) -> None:
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, Compute(None)) is None
    assert own_caches.backend.loaded == []


async def test_the_outcome_says_whether_the_derived_value_came_from_the_cache() -> None:
    compute = Compute({"v": 1})
    first, second = CacheOutcome(), CacheOutcome()
    await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute, outcome=first)
    await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute, outcome=second)
    assert (first.hit, second.hit) == (False, True)


async def test_concurrent_identical_derived_calls_share_one_compute() -> None:
    async def slow() -> dict:
        await asyncio.sleep(0.01)
        slow.calls += 1                                                  # type: ignore[attr-defined]
        return {"v": 1}

    slow.calls = 0                                                       # type: ignore[attr-defined]
    results = await asyncio.gather(*(fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, slow) for _ in range(5)))
    assert results == [{"v": 1}] * 5
    assert slow.calls == 1                                               # type: ignore[attr-defined]


async def test_a_derived_none_is_remembered_for_the_failure_window() -> None:
    compute = Compute(None, {"v": 1})
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) is None
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) is None
    assert compute.calls == 1


async def test_a_stale_derived_copy_is_served_when_compute_has_nothing_after_the_ttl(clock) -> None:
    compute = Compute({"v": 1}, None)
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) == {"v": 1}
    clock.advance(1801)
    outcome = CacheOutcome()
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute, outcome=outcome) == {"v": 1}
    assert compute.calls == 2 and outcome.hit is True


# --- a refusal is not a failure ---------------------------------------------------------------------------------

async def test_a_derived_refusal_is_none_for_that_call_only_and_is_not_remembered() -> None:
    compute = Compute(FetchRefused("budget"), {"v": 1})
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) is None
    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) == {"v": 1}      # nothing was negative-cached
    assert compute.calls == 2


async def test_the_or_raise_form_lets_the_refusal_through_and_does_not_remember_it() -> None:
    compute = Compute(FetchRefused("budget"), {"v": 1})
    with pytest.raises(FetchRefused):
        await fetch_derived_or_raise(DERIVED_KEY, CacheLevel.FORECAST, compute)
    assert await fetch_derived_or_raise(DERIVED_KEY, CacheLevel.FORECAST, compute) == {"v": 1}
    assert compute.calls == 2


async def test_a_derived_refusal_serves_the_stale_copy_when_there_is_one(clock) -> None:
    compute = Compute({"v": 1}, FetchRefused("budget"))
    await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute)
    clock.advance(1801)
    outcome = CacheOutcome()
    assert await fetch_derived_or_raise(DERIVED_KEY, CacheLevel.FORECAST, compute, outcome=outcome) == {"v": 1}
    assert outcome.hit is True


async def test_concurrent_derived_calls_all_get_the_refusal_of_the_one_compute() -> None:
    async def refuse() -> dict:
        await asyncio.sleep(0.01)
        refuse.calls += 1                                                # type: ignore[attr-defined]
        raise FetchRefused("budget")

    refuse.calls = 0                                                     # type: ignore[attr-defined]
    results = await asyncio.gather(*(fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, refuse) for _ in range(3)))
    assert results == [None, None, None]
    assert refuse.calls == 1                                             # type: ignore[attr-defined]


async def test_an_error_of_compute_that_is_not_a_refusal_is_not_swallowed() -> None:
    with pytest.raises(RuntimeError, match="bug"):
        await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, Compute(RuntimeError("bug")))


# --- the key and the level --------------------------------------------------------------------------------------

def test_a_derived_key_cannot_look_like_the_query_of_a_series() -> None:
    wire_like = _request().params()                                      # every SeriesRequest has a `timezone`
    with pytest.raises(ValueError, match="derived"):
        asyncio.run(fetch_derived(wire_like, CacheLevel.CURRENT, Compute({"v": 1})))


async def test_a_derived_key_never_collides_with_a_series_key(install, own_caches) -> None:
    install({"value": 1})
    request = _request(CacheLevel.FORECAST)
    await fetch_series(request, _parse_value)
    await fetch_derived({"latitude": LAT, "longitude": LON, "current": "temperature_2m"}, CacheLevel.FORECAST, Compute({"v": 1}))
    assert len(own_caches.caches[CacheLevel.FORECAST]._cache) == 2


async def test_an_unbound_level_fails_clearly_and_computes_nothing(monkeypatch) -> None:
    monkeypatch.setattr(source_module, "_caches", {})
    compute = Compute({"v": 1})
    with pytest.raises(CacheNotBoundError, match="FORECAST"):
        await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute)
    assert compute.calls == 0


# --- the real use: a value computed from two cached series ------------------------------------------------------

def _two_models(key: dict) -> Any:
    """A `compute` that asks the same two series a consensus asks, with `fetch_series_or_raise` inside."""

    async def compute() -> dict | None:
        requests = [
            SeriesRequest(lat=LAT, lon=LON, level=CacheLevel.FORECAST, daily=("precipitation_sum",), models=m)
            for m in ("a", "b")
        ]
        results = await asyncio.gather(
            *(fetch_series_or_raise(r, _parse_value) for r in requests), return_exceptions=True
        )
        if any(isinstance(r, FetchRefused) for r in results):
            raise FetchRefused("one model was refused")
        return {"models": [r for r in results if isinstance(r, dict)]}

    return compute


async def test_a_consensus_with_a_refused_series_is_not_cached_but_the_series_that_came_back_is(install) -> None:
    def respond(params: dict) -> object:
        return FetchRefused("budget") if params["models"] == "b" and not respond.b_ok else {"value": params["models"]}  # type: ignore[attr-defined]

    respond.b_ok = False                                                 # type: ignore[attr-defined]
    fake = install(respond=respond)
    compute = _two_models(DERIVED_KEY)

    assert await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute) is None
    assert sorted(c.params["models"] for c in fake.calls) == ["a", "b"]

    respond.b_ok = True                                                  # type: ignore[attr-defined]
    result = await fetch_derived(DERIVED_KEY, CacheLevel.FORECAST, compute)
    assert result == {"models": [{"value": "a"}, {"value": "b"}]}        # not the one-model consensus
    assert sorted(c.params["models"] for c in fake.calls) == ["a", "b", "b"]   # "a" was served from its own entry

# --- the real consensus (2c-2): `get_multi_model_daily` asks each model with `fetch_series_or_raise` -----------------

_GFS, _ECMWF = "gfs_seamless", "ecmwf_ifs025"


def _consensus_key() -> str:
    return cache_key({"latitude": LAT, "longitude": LON, "forecast_days": 7, "models": f"{_GFS},{_ECMWF}"})


def _model_key(model: str) -> str:
    return cache_key(om_module._daily_request(LAT, LON, 7, model).params())


async def test_the_consensus_with_one_model_refused_is_none_for_that_call_and_is_not_remembered(install) -> None:
    refused = {"model": _ECMWF}

    def respond(params: dict) -> object:
        return FetchRefused("budget") if params["models"] == refused["model"] else _DAILY_EXT_PAYLOAD

    fake = install(respond=respond)
    cache = om_module._CACHE_FORECAST

    assert await om_module.get_multi_model_daily(LAT, LON) is None           # no degraded consensus for this call
    assert sorted(c.params["models"] for c in fake.calls) == [_ECMWF, _GFS]
    assert list(cache._cache) == [_model_key(_GFS)]                          # the model that answered keeps its entry
    assert _consensus_key() not in cache._cache and list(cache._failure_cache) == []   # nothing else was remembered

    refused["model"] = ""                                                    # the budget is back
    result = await om_module.get_multi_model_daily(LAT, LON)
    assert result is not None and sorted(result.models) == [_ECMWF, _GFS]
    assert sorted(c.params["models"] for c in fake.calls) == [_ECMWF, _ECMWF, _GFS]   # only the refused one again
    assert _consensus_key() in cache._cache


async def test_the_consensus_with_every_model_refused_is_none_and_is_not_remembered(install) -> None:
    fake = install(FetchRefused("budget"), FetchRefused("budget"), _DAILY_EXT_PAYLOAD)
    assert await om_module.get_multi_model_daily(LAT, LON) is None
    assert list(om_module._CACHE_FORECAST._cache) == [] and list(om_module._CACHE_FORECAST._failure_cache) == []
    result = await om_module.get_multi_model_daily(LAT, LON)
    assert result is not None and sorted(result.models) == [_ECMWF, _GFS]
    assert len(fake.calls) == 4


async def test_a_model_whose_payload_cannot_be_read_is_left_out_of_the_consensus(install) -> None:
    install(respond=lambda params: {"daily": None} if params["models"] == _GFS else _DAILY_EXT_PAYLOAD)
    result = await om_module.get_multi_model_daily(LAT, LON)
    assert result is not None and list(result.models) == [_ECMWF]


def _boom_on_gfs(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Patch the daily parser so a payload marked "boom" raises an IndexError (a bug no parse guard expects)."""
    real = om_module._parse_daily

    def parse(data: dict) -> Any:
        if "boom" in data:
            raise IndexError("parser bug")
        return real(data)

    monkeypatch.setattr(om_module, "_parse_daily", parse)
    return lambda params: {"boom": 1} if params["models"] == _GFS else _DAILY_EXT_PAYLOAD


@pytest.mark.parametrize(
    "error", [IndexError("parser bug"), asyncio.CancelledError()], ids=["IndexError", "CancelledError"]
)
async def test_an_unexpected_error_of_one_model_is_logged_with_its_traceback_and_the_other_model_still_answers(
    error, install, caplog
) -> None:
    install(respond=lambda params: error if params["models"] == _GFS else _DAILY_EXT_PAYLOAD)
    with caplog.at_level(logging.ERROR):
        result = await om_module.get_multi_model_daily(LAT, LON)
    assert result is not None and list(result.models) == [_ECMWF]            # the other model still answers
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert _GFS in record.getMessage() and _ECMWF not in record.getMessage()
    assert record.exc_info is not None and type(record.exc_info[1]) is type(error)
    if not isinstance(error, asyncio.CancelledError):                        # a cancelled task has no traceback
        assert record.exc_info[1] is error and record.exc_info[2] is not None


async def test_an_unexpected_parse_bug_of_one_model_is_logged_and_the_consensus_is_still_cached(
    install, caplog, monkeypatch
) -> None:
    install(respond=_boom_on_gfs(monkeypatch))
    with caplog.at_level(logging.ERROR):
        result = await om_module.get_multi_model_daily(LAT, LON)
    assert result is not None and list(result.models) == [_ECMWF]
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert _GFS in record.getMessage() and isinstance(record.exc_info[1], IndexError)
    assert record.exc_info[2] is not None                                    # with a traceback
    assert _consensus_key() in om_module._CACHE_FORECAST._cache             # what is cached is unchanged


async def test_a_refused_model_is_not_logged_as_an_error(install, caplog) -> None:
    install(respond=lambda params: FetchRefused("budget") if params["models"] == _ECMWF else _DAILY_EXT_PAYLOAD)
    with caplog.at_level(logging.ERROR):
        assert await om_module.get_multi_model_daily(LAT, LON) is None
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


# --- the raising form of `fetch_series`: what a `compute` calls ------------------------------------------------

async def test_fetch_series_or_raise_lets_a_refusal_through_and_does_not_remember_it(install) -> None:
    fake = install(FetchRefused("budget"), {"value": 1})
    with pytest.raises(FetchRefused):
        await fetch_series_or_raise(_request(), _parse_value)
    assert await fetch_series_or_raise(_request(), _parse_value) == {"value": 1}
    assert len(fake.calls) == 2


async def test_fetch_series_or_raise_serves_the_stale_copy_on_a_refusal(install, clock) -> None:
    install({"value": 1}, FetchRefused("budget"))
    await fetch_series_or_raise(_request(), _parse_value)
    clock.advance(601)
    outcome = CacheOutcome()
    assert await fetch_series_or_raise(_request(), _parse_value, outcome=outcome) == {"value": 1}
    assert outcome.hit is True


async def test_fetch_series_or_raise_is_none_for_failures_and_parse_errors_like_fetch_series(install) -> None:
    install(None)
    assert await fetch_series_or_raise(_request(lat=1.0), _parse_value) is None
    install({"value": 1})
    assert await fetch_series_or_raise(_request(lat=2.0), lambda p: p["nope"]) is None


async def test_fetch_series_or_raise_takes_the_same_options_as_fetch_series(install, own_caches, caplog) -> None:
    fake = install({"value": 1})
    outcome = CacheOutcome()
    kwargs = dict(outcome=outcome, failure_message="f %s", parse_error_message="p %s", log_args=("x",))
    assert await fetch_series_or_raise(_request(persist=False), _parse_value, **kwargs) == {"value": 1}
    await own_caches.caches[CacheLevel.CURRENT].flush_persistence()
    assert own_caches.backend.saved == []
    assert (fake.calls[0].failure_message, fake.calls[0].log_args) == ("f %s", ("x",))
    assert outcome.hit is False


async def test_the_wrapper_and_the_raising_variant_differ_only_in_the_refusal(install) -> None:
    install(FetchRefused("budget"))
    assert await fetch_series(_request(lat=1.0), _parse_value) is None
    with pytest.raises(FetchRefused):
        await fetch_series_or_raise(_request(lat=2.0), _parse_value)
