"""CheckWX quota accounting: only what CheckWX accepted is counted, and the gate is atomic.

Q1 - The unit goes back ONLY when CheckWX surely did not process the call; otherwise it stays spent.
Q2 - Exhausted quota keeps its contract and is never remembered as a failure.
Q3 - `maybe_notify` runs in the background, once per cycle, and can never delay or break a response.
Q4 - Reservation is one atomic increment-and-compare (bursts never exceed the limit, no lock around I/O).
Q5 - The HTTP router answers with the same shapes as before (plus Retry-After on a remembered 503).
Q6 - Refund hygiene: nothing is given back for a unit that was never counted or whose cycle is gone.
Q7 - Cancelling a flight and a failing counter hand the admission tokens (and the unit, if due) back.
"""
from __future__ import annotations

import asyncio
import gc
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient

from app.core.counter import MemoryCounter, current_cycle
from app.services import checkwx as checkwx_svc
from tests.conftest import FakeCheckWX, FakeClock, checkwx_payload

pytestmark = pytest.mark.usefixtures("checkwx_roomy_bucket")


class YieldingCounter(MemoryCounter):
    """MemoryCounter whose operations yield to the event loop, like a real Upstash round trip."""

    def __init__(self) -> None:
        super().__init__()
        self.incr_delay = 0.0
        self.active_incr = 0
        self.max_active_incr = 0

    async def get(self, cycle: str) -> int:
        await asyncio.sleep(0)
        return await super().get(cycle)

    async def incr(self, cycle: str) -> int:
        self.active_incr += 1
        self.max_active_incr = max(self.max_active_incr, self.active_incr)
        try:
            await asyncio.sleep(self.incr_delay)
        finally:
            self.active_incr -= 1
        return await super().incr(cycle)

    async def decr(self, cycle: str) -> int:
        await asyncio.sleep(0)
        return await super().decr(cycle)


class SpyCounter(MemoryCounter):
    """MemoryCounter that remembers every incr/decr it was asked for, as (operation, cycle)."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str]] = []

    async def incr(self, cycle: str) -> int:
        self.calls.append(("incr", cycle))
        return await super().incr(cycle)

    async def decr(self, cycle: str) -> int:
        self.calls.append(("decr", cycle))
        return await super().decr(cycle)


class DegradedCounter(SpyCounter):
    """Upstash down: incr counts nothing and answers 0 (the fail-open path of RedisCounter)."""

    async def incr(self, cycle: str) -> int:
        self.calls.append(("incr", cycle))
        return 0


class ExplodingCounter(MemoryCounter):
    async def incr(self, cycle: str) -> int:
        raise RuntimeError("counter exploded")


async def _fill(counter: MemoryCounter, units: int) -> str:
    cycle = current_cycle()
    for _ in range(units):
        await counter.incr(cycle)
    return cycle


async def _units(counter: MemoryCounter) -> int:
    return await counter.get(current_cycle())


# ---------------------------------------------------------------------------
# Q1 - exact accounting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "outcome",
    [
        pytest.param(401, id="401"),
        pytest.param(403, id="403"),
        pytest.param(429, id="429-from-checkwx"),
        pytest.param(500, id="500"),
        pytest.param(503, id="503"),
        pytest.param(httpx.ConnectError("down"), id="connect-error"),
        pytest.param(httpx.ConnectTimeout("no route"), id="connect-timeout"),
        pytest.param(httpx.PoolTimeout("no free connection"), id="pool-timeout"),
    ],
)
async def test_q1_the_unit_is_returned_when_checkwx_surely_did_not_process_the_call(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, outcome: object
):
    checkwx_upstream.set("SAEZ", outcome)

    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert checkwx_upstream.count() == 1
    assert await _units(checkwx_counter) == 0


@pytest.mark.parametrize(
    "outcome",
    [
        pytest.param(400, id="400"),
        pytest.param(404, id="404"),
        pytest.param(408, id="408"),
        pytest.param(httpx.ReadTimeout("slow"), id="read-timeout"),
        pytest.param(httpx.ReadError("connection reset"), id="read-error"),
        pytest.param(httpx.RemoteProtocolError("closed without a response"), id="remote-protocol-error"),
    ],
)
async def test_q1_the_unit_stays_spent_when_checkwx_may_have_processed_the_call(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, outcome: object
):
    """CheckWX billing of failed calls is unverified: other 4xx and read timeouts are counted."""
    checkwx_upstream.set("SAEZ", outcome)

    for _ in range(2):
        with pytest.raises(checkwx_svc.CheckWXUnavailableError):
            await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert checkwx_upstream.count() == 1  # remembered as a failure, so the repeat is free
    assert await _units(checkwx_counter) == 1


async def test_q1_the_unit_is_kept_on_a_2xx(checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter):
    await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    assert await _units(checkwx_counter) == 1


@pytest.mark.parametrize("outcome", ["bad_json", "not_an_object"])
async def test_q1_a_2xx_with_an_unusable_body_keeps_the_unit_and_is_remembered(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, outcome: str
):
    """CheckWX accepted the call (2xx), so it is counted; the failure memo stops a unit per repeat."""
    checkwx_upstream.set("SAEZ", outcome)

    for _ in range(3):
        with pytest.raises(checkwx_svc.CheckWXUnavailableError):
            await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert checkwx_upstream.count() == 1
    assert await _units(checkwx_counter) == 1


async def test_q1_an_internal_error_before_the_call_ends_returns_the_unit_and_is_not_remembered(
    checkwx_counter: MemoryCounter, monkeypatch
):
    boom = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(checkwx_svc, "_do_http_fetch", boom)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert await _units(checkwx_counter) == 0
    assert boom.await_count == 2  # a bug is not a remembered upstream failure


async def test_q1_a_burst_of_failing_calls_gives_every_unit_back(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_daily_limit", 5, raising=False)
    checkwx_upstream.default_outcome = 500
    checkwx_upstream.delay = 0.02

    results = await asyncio.gather(
        *(checkwx_svc.fetch_metar(f"C{n:03d}", kind="metar") for n in range(10)), return_exceptions=True
    )

    assert checkwx_upstream.count() == 5
    assert sum(isinstance(r, checkwx_svc.CheckWXUnavailableError) for r in results) == 5
    assert sum(isinstance(r, checkwx_svc.CheckWXQuotaExceededError) for r in results) == 5
    assert await _units(checkwx_counter) == 0


async def test_q1_a_returned_unit_can_be_spent_again(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_daily_limit", 1, raising=False)
    checkwx_upstream.set("SAEZ", 500)
    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert await checkwx_svc.fetch_metar("SACO", kind="metar") == checkwx_payload("metar", "SACO")
    assert await _units(checkwx_counter) == 1


# ---------------------------------------------------------------------------
# Q2 - exhausted quota
# ---------------------------------------------------------------------------

async def test_q2_exhausted_quota_refuses_before_calling_checkwx(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    cycle = await _fill(checkwx_counter, 198)

    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError) as caught:
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert caught.value.cycle == cycle
    assert caught.value.count == 198
    assert checkwx_upstream.count() == 0
    assert await _units(checkwx_counter) == 198  # the refused attempt left no trace


async def test_q2_exhausted_quota_is_not_remembered_as_a_failure(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, checkwx_clock: FakeClock
):
    cycle = await _fill(checkwx_counter, 198)
    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    await checkwx_counter.decr(cycle)  # one unit comes back (for example a failed call elsewhere)
    checkwx_clock.advance(31)  # the short exhaustion memo (test_checkwx_exhaustion_memo.py) is over

    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar") == checkwx_payload("metar", "SAEZ")


@pytest.mark.usefixtures("fresh_rate_limit")
async def test_q2_router_keeps_the_quota_429_contract(async_client: AsyncClient, checkwx_counter: MemoryCounter):
    cycle = await _fill(checkwx_counter, 198)

    with patch("app.core.notifier.sentry_sdk"):
        response = await async_client.get("/api/metar?icao=SAEZ")

    assert response.status_code == 429
    detail = response.json()["detail"]
    assert set(detail) == {"error", "message", "cycle", "limit", "retry_after"}
    assert detail["error"] == "metar_quota_exceeded"
    assert detail["cycle"] == cycle
    assert detail["limit"] == 198
    assert 1 <= detail["retry_after"] <= 86_400
    assert response.headers["Retry-After"] == str(detail["retry_after"])


# ---------------------------------------------------------------------------
# Q3 - notifications
# ---------------------------------------------------------------------------

class _StuckNotifier:
    """Stand-in for maybe_notify that blocks until released, to prove nobody waits for it."""

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()
        self.calls: list[tuple] = []

    async def __call__(self, *args, **_kwargs) -> None:
        self.calls.append(args)
        self.entered.set()
        await self.gate.wait()


async def test_q3_a_stuck_notifier_never_holds_up_the_refusal(checkwx_counter: MemoryCounter, monkeypatch):
    notifier = _StuckNotifier()
    monkeypatch.setattr(checkwx_svc, "maybe_notify", notifier)
    cycle = await _fill(checkwx_counter, 198)

    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
        await asyncio.wait_for(checkwx_svc.fetch_metar("SAEZ", kind="metar"), timeout=1)

    await asyncio.wait_for(notifier.entered.wait(), timeout=1)  # it did start, in the background
    assert not notifier.gate.is_set()
    assert len(checkwx_svc._background) == 1  # and something holds it, or asyncio may collect it mid-run
    notifier.gate.set()
    await checkwx_svc._drain_background_for_tests()
    assert notifier.calls == [(cycle, 198, checkwx_counter, 198)]
    assert len(checkwx_svc._background) == 0  # finished tasks are let go


async def test_q3_a_stuck_notifier_never_holds_up_a_good_response(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    notifier = _StuckNotifier()
    monkeypatch.setattr(checkwx_svc, "maybe_notify", notifier)
    checkwx_upstream.delay = 0.02

    results = await asyncio.wait_for(
        asyncio.gather(*(checkwx_svc.fetch_metar("SAEZ", kind="metar") for _ in range(5))), timeout=1
    )

    assert all(r == checkwx_payload("metar", "SAEZ") for r in results)
    await asyncio.wait_for(notifier.entered.wait(), timeout=1)
    notifier.gate.set()
    await checkwx_svc._drain_background_for_tests()
    assert notifier.calls == [(current_cycle(), 1, checkwx_counter, 198)]  # once, not once per waiter


async def test_q3_exhaustion_is_notified_once_per_cycle(checkwx_counter: MemoryCounter, monkeypatch):
    notify = AsyncMock()
    monkeypatch.setattr(checkwx_svc, "maybe_notify", notify)
    cycle = await _fill(checkwx_counter, 198)

    for n in range(5):
        with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
            await checkwx_svc.fetch_metar(f"D{n:03d}", kind="metar")
    await checkwx_svc._drain_background_for_tests()

    notify.assert_awaited_once_with(cycle, 198, checkwx_counter, 198)


async def test_q3_a_failing_notification_never_changes_the_refusal_and_is_retried(
    checkwx_counter: MemoryCounter, checkwx_clock: FakeClock, monkeypatch
):
    notify = AsyncMock(side_effect=RuntimeError("sentry down"))
    monkeypatch.setattr(checkwx_svc, "maybe_notify", notify)
    await _fill(checkwx_counter, 198)

    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    await checkwx_svc._drain_background_for_tests()
    checkwx_clock.advance(31)  # the exhaustion memo is over: the next refusal is a fresh finding
    with pytest.raises(checkwx_svc.CheckWXQuotaExceededError):
        await checkwx_svc.fetch_metar("SACO", kind="metar")
    await checkwx_svc._drain_background_for_tests()

    assert notify.await_count == 2  # the failed attempt did not mark the cycle as notified


async def test_q3_a_failing_notification_does_not_fail_a_good_fetch(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    monkeypatch.setattr(checkwx_svc, "maybe_notify", AsyncMock(side_effect=RuntimeError("sentry down")))

    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar") == checkwx_payload("metar", "SAEZ")
    await checkwx_svc._drain_background_for_tests()
    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar") == checkwx_payload("metar", "SAEZ")
    assert checkwx_upstream.count() == 1


async def test_q3_a_failing_background_notification_leaves_no_unretrieved_exception(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    reports: list[dict] = []
    asyncio.get_running_loop().set_exception_handler(lambda _loop, context: reports.append(context))
    notify = AsyncMock(side_effect=RuntimeError("sentry down"))
    monkeypatch.setattr(checkwx_svc, "maybe_notify", notify)

    await checkwx_svc.fetch_metar("SAEZ", kind="metar")
    await asyncio.sleep(0.05)  # the background task runs and fails; nobody awaits it
    gc.collect()
    await asyncio.sleep(0)

    assert notify.await_count == 1
    assert [r for r in reports if "never retrieved" in r.get("message", "")] == []


# ---------------------------------------------------------------------------
# Q4 - atomic reservation, no I/O inside a lock
# ---------------------------------------------------------------------------

async def test_q4_a_burst_never_exceeds_the_limit_even_when_the_counter_yields(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_daily_limit", 5, raising=False)
    counter = YieldingCounter()
    checkwx_svc.set_counter(counter)
    checkwx_upstream.delay = 0.02

    results = await asyncio.gather(
        *(checkwx_svc.fetch_metar(f"B{n:03d}", kind="metar") for n in range(5 + 20)),
        return_exceptions=True,
    )

    assert checkwx_upstream.count() == 5
    assert await _units(counter) == 5
    assert sum(isinstance(r, dict) for r in results) == 5
    assert sum(isinstance(r, checkwx_svc.CheckWXQuotaExceededError) for r in results) == 20


async def test_q4_counter_round_trips_are_not_serialised(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    counter = YieldingCounter()
    counter.incr_delay = 0.03
    checkwx_svc.set_counter(counter)

    await asyncio.gather(*(checkwx_svc.fetch_metar(f"E{n:03d}", kind="metar") for n in range(8)))

    assert counter.max_active_incr == 8  # a lock around the reservation would make this 1


# ---------------------------------------------------------------------------
# Q5 - router shapes
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("checkwx_counter", "fresh_rate_limit")
async def test_q5_router_passes_the_payload_through_and_caches_it(
    async_client: AsyncClient, checkwx_upstream: FakeCheckWX
):
    first = await async_client.get("/api/metar?icao=saez")
    second = await async_client.get("/api/metar?icao=SAEZ")

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == checkwx_payload("metar", "SAEZ")
    assert checkwx_upstream.count() == 1


@pytest.mark.usefixtures("checkwx_counter", "fresh_rate_limit")
@pytest.mark.parametrize("outcome", [401, 404, 500, httpx.ReadTimeout("slow")], ids=["401", "404", "500", "timeout"])
async def test_q5_router_maps_every_upstream_failure_to_503(
    async_client: AsyncClient, checkwx_upstream: FakeCheckWX, outcome: object
):
    checkwx_upstream.set("SAEZ", outcome)

    response = await async_client.get("/api/metar?icao=SAEZ")

    assert response.status_code == 503
    assert response.json() == {"detail": "metar_unavailable"}
    assert "Retry-After" not in response.headers


@pytest.mark.usefixtures("checkwx_counter", "fresh_rate_limit")
async def test_q5_router_sends_retry_after_only_on_a_remembered_503(
    async_client: AsyncClient, checkwx_upstream: FakeCheckWX, checkwx_clock: FakeClock
):
    checkwx_upstream.set("SAEZ", 500)

    first = await async_client.get("/api/metar?icao=SAEZ")
    remembered = await async_client.get("/api/metar?icao=SAEZ")
    checkwx_clock.advance(10)
    later = await async_client.get("/api/metar?icao=SAEZ")

    assert first.status_code == remembered.status_code == later.status_code == 503
    assert first.json() == remembered.json() == later.json() == {"detail": "metar_unavailable"}
    assert "Retry-After" not in first.headers
    assert remembered.headers["Retry-After"] == "15"  # the whole failure window is still ahead
    assert later.headers["Retry-After"] == "5"
    assert checkwx_upstream.count() == 1


@pytest.mark.usefixtures("checkwx_counter", "fresh_rate_limit")
async def test_q5_router_keeps_422_and_not_configured_shapes(async_client: AsyncClient, monkeypatch):
    bad_length = await async_client.get("/api/metar?icao=XX")
    bad_chars = await async_client.get("/api/metar?icao=SA-Z")
    bad_type = await async_client.get("/api/metar?icao=SAEZ&type=xyz")
    assert bad_length.status_code == bad_chars.status_code == bad_type.status_code == 422
    assert bad_chars.json() == {"detail": "invalid_icao"}

    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_api_key", "", raising=False)
    not_configured = await async_client.get("/api/metar?icao=SAEZ")
    assert not_configured.status_code == 503
    assert not_configured.json() == {"detail": "checkwx_not_configured"}


# ---------------------------------------------------------------------------
# Q6 - refund hygiene
# ---------------------------------------------------------------------------

async def test_q6_a_unit_that_was_never_counted_is_not_given_back(checkwx_upstream: FakeCheckWX):
    """Degraded Upstash: incr answered 0. A decr now would eat a unit someone else spent."""
    counter = DegradedCounter()
    checkwx_svc.set_counter(counter)
    checkwx_upstream.set("SAEZ", 500)

    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert [op for op, _ in counter.calls] == ["incr"]


async def test_q6_a_degraded_counter_still_serves_good_fetches(checkwx_upstream: FakeCheckWX):
    checkwx_svc.set_counter(DegradedCounter())

    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar") == checkwx_payload("metar", "SAEZ")


async def test_q6_the_refund_goes_to_the_cycle_of_the_reservation(checkwx_upstream: FakeCheckWX, monkeypatch):
    counter = SpyCounter()
    checkwx_svc.set_counter(counter)
    monkeypatch.setattr(checkwx_svc, "current_cycle", lambda: "2026-10-08")
    checkwx_upstream.set("SAEZ", 500)

    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar")

    assert counter.calls == [("incr", "2026-10-08"), ("decr", "2026-10-08")]


async def test_q6_midnight_straddle_skips_the_refund(checkwx_upstream: FakeCheckWX, monkeypatch):
    """Reserved before 00:00 UTC, failed after: the old key may be gone, a decr would recreate it at -1."""
    counter = SpyCounter()
    checkwx_svc.set_counter(counter)
    today = {"cycle": "2026-10-08"}
    monkeypatch.setattr(checkwx_svc, "current_cycle", lambda: today["cycle"])
    checkwx_upstream.delay = 0.03
    checkwx_upstream.set("SAEZ", 500)

    pending = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar"))
    await asyncio.sleep(0.01)  # the unit is reserved and the request is in flight
    today["cycle"] = "2026-10-09"  # midnight passes
    with pytest.raises(checkwx_svc.CheckWXUnavailableError):
        await pending

    assert counter.calls == [("incr", "2026-10-08")]  # no decr, neither on the old day nor on the new one
    assert await counter.get("2026-10-09") == 0


# ---------------------------------------------------------------------------
# Q7 - cancellation and a failing counter
# ---------------------------------------------------------------------------

def _flight(kind: str, icao: str) -> asyncio.Task:
    return checkwx_svc._inflight[(kind, icao)]


async def test_q7_cancelling_the_flight_while_the_request_is_out_keeps_the_unit(
    checkwx_upstream: FakeCheckWX, checkwx_counter: MemoryCounter
):
    """The request was sent, so CheckWX may have accepted it: conservative accounting keeps the unit."""
    checkwx_upstream.delay = 0.5
    caller = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar"))
    await asyncio.sleep(0.02)

    _flight("metar", "SAEZ").cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.sleep(0)

    assert await _units(checkwx_counter) == 1
    assert checkwx_svc._inflight == {}
    assert checkwx_upstream.active == 0


async def test_q7_cancelling_the_flight_before_the_request_is_out_returns_the_tokens(
    checkwx_upstream: FakeCheckWX, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", 1, raising=False)
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_client_per_minute", 1, raising=False)
    counter = YieldingCounter()
    counter.incr_delay = 0.5
    checkwx_svc.set_counter(counter)

    caller = asyncio.create_task(checkwx_svc.fetch_metar("SAEZ", kind="metar", client="c1"))
    await asyncio.sleep(0.02)  # the flight is waiting on the counter
    _flight("metar", "SAEZ").cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    counter.incr_delay = 0.0

    assert checkwx_upstream.count() == 0
    # Both one-token buckets (global and the client's) are intact: this call is admitted.
    assert await checkwx_svc.fetch_metar("SACO", kind="metar", client="c1") == checkwx_payload("metar", "SACO")


async def test_q7_an_incr_that_raises_returns_the_tokens_and_is_not_remembered(
    checkwx_upstream: FakeCheckWX, monkeypatch
):
    import app.core.config as cfg
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_minute", 1, raising=False)
    monkeypatch.setattr(cfg.settings, "checkwx_new_calls_per_client_per_minute", 1, raising=False)
    checkwx_svc.set_counter(ExplodingCounter())

    with pytest.raises(RuntimeError, match="counter exploded"):
        await checkwx_svc.fetch_metar("SAEZ", kind="metar", client="c1")

    checkwx_svc.set_counter(MemoryCounter())
    # Same station, same client, one-token buckets: admitted again, so neither token was lost.
    assert await checkwx_svc.fetch_metar("SAEZ", kind="metar", client="c1") == checkwx_payload("metar", "SAEZ")
