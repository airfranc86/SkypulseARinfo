"""Último dato bueno persistente: el adaptador de Redis y su integración con `SingleFlightCache`.

Nada de esto toca la red: Redis es un doble en memoria y el reloj es inyectado.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.core.cache import CacheOutcome, Persisted, SingleFlightCache
from app.core.dataclass_codec import DataclassCodec
from app.core.config import Settings
from app.core.persistent_cache import SCHEMA_VERSION, RedisLastGoodStore
from app.core.upstash import UpstashUnavailableError
from app.services.openmeteo import DailyForecastDataExt, OpenMeteoCurrent

_CODEC = DataclassCodec(OpenMeteoCurrent, DailyForecastDataExt)
_SECRETO = "SECRETO-ABC-123"


def _current(temp: float = 23.5) -> OpenMeteoCurrent:
    return OpenMeteoCurrent(
        temp_c=temp, feels_like_c=22.1, humidity=52.0, wind_speed_kmh=18.0, wind_dir_deg=270.0,
        pressure_hpa=1014.2, precip_1h_mm=0.0, cloud_cover=10.0, weather_code=0, description=None,
        fetched_at=datetime(2026, 10, 8, 15, 30, tzinfo=timezone.utc),
        observed_at=datetime(2026, 10, 8, 15, 15, tzinfo=timezone.utc), wind_gust_kmh=31.0,
    )


class FakeRedis:
    """Lo mínimo de `UpstashRedis` que usa el adaptador: `read` y `set`."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.reads: list[str] = []
        self.sets: list[tuple[str, str, int | None]] = []
        self.read_error: Exception | None = None
        self.set_error: Exception | None = None
        self.read_delay = 0.0
        self.set_delay = 0.0

    async def read(self, key: str) -> str | None:
        self.reads.append(key)
        if self.read_delay:
            await asyncio.sleep(self.read_delay)
        if self.read_error is not None:
            raise self.read_error
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.sets.append((key, value, ex))
        if self.set_delay:
            await asyncio.sleep(self.set_delay)
        if self.set_error is not None:
            raise self.set_error
        self.store[key] = value
        self.ttls[key] = ex


class FakeClock:
    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(redis: FakeRedis, clock: FakeClock) -> RedisLastGoodStore:
    return RedisLastGoodStore(
        name="om_current", codec=_CODEC, ttl_seconds=10800, redis_provider=lambda: redis,
        clock=clock, write_interval_seconds=1800.0, miss_memo_seconds=300.0,
    )


# ---------------------------------------------------------------------------
# Adaptador de Redis
# ---------------------------------------------------------------------------

async def test_save_then_load_roundtrip(store: RedisLastGoodStore, redis: FakeRedis) -> None:
    await store.save("k1", _current())
    assert (await store.load("k1")).value == _current()
    assert len(redis.sets) == 1


async def test_save_uses_a_prefixed_hashed_key_and_the_configured_ttl(
    store: RedisLastGoodStore, redis: FakeRedis
) -> None:
    long_key = json.dumps({"latitude": -34.6, "daily": "x," * 200}, sort_keys=True)
    await store.save(long_key, _current())
    (key, _value, ex), = redis.sets
    assert key.startswith(f"skypulse:om_last_good:v{SCHEMA_VERSION}:om_current:")
    assert len(key) < 100            # el hash acota la clave aunque el parámetro sea largo
    assert "latitude" not in key
    assert ex == 10800


async def test_stored_payload_is_plain_json_with_version_type_and_timestamp(
    store: RedisLastGoodStore, redis: FakeRedis
) -> None:
    await store.save("k1", _current())
    (_key, text, _ex), = redis.sets
    envelope = json.loads(text)
    assert envelope["v"] == SCHEMA_VERSION
    assert envelope["type"] == "OpenMeteoCurrent"
    assert isinstance(envelope["data"], dict)
    datetime.fromisoformat(envelope["saved_at"])


async def test_writes_are_throttled_per_key(
    store: RedisLastGoodStore, redis: FakeRedis, clock: FakeClock
) -> None:
    await store.save("k1", _current(20.0))
    await store.save("k1", _current(21.0))      # dentro de la ventana: no se escribe
    await store.save("k2", _current(22.0))      # otra clave: tiene su propia ventana
    assert len(redis.sets) == 2
    clock.now += 1799.0
    await store.save("k1", _current(23.0))
    assert len(redis.sets) == 2
    clock.now += 2.0
    await store.save("k1", _current(24.0))
    assert len(redis.sets) == 3
    assert (await store.load("k1")).value.temp_c == 24.0


async def test_a_failed_write_also_consumes_the_window(
    store: RedisLastGoodStore, redis: FakeRedis
) -> None:
    redis.set_error = UpstashUnavailableError("down")
    await store.save("k1", _current())          # falla en silencio
    await store.save("k1", _current())          # no insiste en la misma ventana
    assert len(redis.sets) == 1


async def test_write_failure_is_swallowed_and_logged_without_the_payload(
    store: RedisLastGoodStore, redis: FakeRedis, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    redis.set_error = RuntimeError(_SECRETO)
    await store.save("k1", _current())
    assert "om_current" in caplog.text
    assert _SECRETO not in caplog.text
    assert "temp_c" not in caplog.text


async def test_load_misses_return_none(store: RedisLastGoodStore) -> None:
    assert await store.load("nunca-guardada") is None


async def test_load_failure_degrades_to_none(
    store: RedisLastGoodStore, redis: FakeRedis, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    redis.read_error = RuntimeError(_SECRETO)
    assert await store.load("k1") is None
    assert _SECRETO not in caplog.text


async def test_disabled_without_a_redis_handle(clock: FakeClock) -> None:
    disabled = RedisLastGoodStore(
        name="om_current", codec=_CODEC, ttl_seconds=60, redis_provider=lambda: None, clock=clock
    )
    await disabled.save("k1", _current())
    assert await disabled.load("k1") is None


async def test_handle_is_resolved_lazily_on_every_call(clock: FakeClock) -> None:
    holder: dict[str, FakeRedis | None] = {"redis": None}
    lazy = RedisLastGoodStore(
        name="om_current", codec=_CODEC, ttl_seconds=60, redis_provider=lambda: holder["redis"],
        clock=clock, write_interval_seconds=0.0,
    )
    await lazy.save("k1", _current())           # todavía no hay Redis: no pasa nada
    holder["redis"] = FakeRedis()               # el lifespan lo configura después del import
    await lazy.save("k1", _current())
    assert (await lazy.load("k1")).value == _current()


async def _plant(redis: FakeRedis, store: RedisLastGoodStore, text: str) -> None:
    await store.save("k1", _current())
    (key, _value, _ex), = redis.sets
    redis.store[key] = text


@pytest.mark.parametrize(
    "text",
    [
        "esto no es json {",
        "[1, 2, 3]",
        '{"v": 1}',
        '{"v": 1, "type": "OpenMeteoCurrent"}',
        '{"v": 1, "type": "os.system", "saved_at": "2026-10-08T15:30:00+00:00", "data": {}}',
        '{"v": 1, "type": "OpenMeteoCurrent", "saved_at": "2026-10-08T15:30:00+00:00", "data": {"temp_c": "x"}}',
        '{"v": true, "type": "OpenMeteoCurrent", "saved_at": "2026-10-08T15:30:00+00:00", "data": {}}',
        "gASVBAAAAAAAAACMAnBvlC4=",  # un pickle en base64 no se interpreta: es basura
    ],
    ids=["not-json", "not-an-object", "no-type", "no-data", "unknown-type", "bad-field",
         "bool-version", "pickle-like"],
)
async def test_undecodable_values_are_treated_as_absent(
    store: RedisLastGoodStore, redis: FakeRedis, caplog: pytest.LogCaptureFixture, text: str
) -> None:
    caplog.set_level(logging.DEBUG)
    await _plant(redis, store, text)
    assert await store.load("k1") is None
    assert "om_current" in caplog.text
    assert text not in caplog.text            # el contenido no va al log


async def test_a_value_from_another_schema_version_is_discarded(
    store: RedisLastGoodStore, redis: FakeRedis, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await store.save("k1", _current())
    (key, text, _ex), = redis.sets
    envelope = json.loads(text)
    envelope["v"] = SCHEMA_VERSION + 1
    redis.store[key] = json.dumps(envelope)
    assert await store.load("k1") is None
    assert "version" in caplog.text.lower()


async def test_a_miss_is_remembered_to_spare_the_command_budget(
    store: RedisLastGoodStore, redis: FakeRedis, clock: FakeClock
) -> None:
    assert await store.load("k1") is None
    assert await store.load("k1") is None       # misma clave dentro de la ventana: sin comando
    assert len(redis.reads) == 1
    assert await store.load("otra") is None
    assert len(redis.reads) == 2
    clock.now += 301.0
    assert await store.load("k1") is None
    assert len(redis.reads) == 3


async def test_a_read_error_is_remembered_like_a_miss(
    store: RedisLastGoodStore, redis: FakeRedis
) -> None:
    redis.read_error = UpstashUnavailableError("down")
    assert await store.load("k1") is None
    assert await store.load("k1") is None
    assert len(redis.reads) == 1


async def test_a_save_clears_the_remembered_miss(
    store: RedisLastGoodStore, redis: FakeRedis
) -> None:
    assert await store.load("k1") is None
    await store.save("k1", _current())
    assert (await store.load("k1")).value == _current()


def test_reset_clears_throttle_and_miss_memory(store: RedisLastGoodStore) -> None:
    store._last_write["x"] = 1.0
    store._misses["x"] = 1.0
    store.reset()
    assert not store._last_write and not store._misses


# ---------------------------------------------------------------------------
# Integración con SingleFlightCache
# ---------------------------------------------------------------------------

class FakeBackend:
    def __init__(self, stored: dict[str, object] | None = None) -> None:
        self.stored = dict(stored or {})
        self.loads: list[str] = []
        self.saves: list[tuple[str, object]] = []
        self.load_error: Exception | None = None
        self.save_error: Exception | None = None
        self.save_gate: asyncio.Event | None = None
        self.save_entered = False
        self.save_cancelled = False
        self.load_delay = 0.0

    async def load(self, key: str):
        self.loads.append(key)
        if self.load_delay:
            await asyncio.sleep(self.load_delay)
        if self.load_error is not None:
            raise self.load_error
        return self.stored.get(key)

    async def save(self, key: str, value) -> None:
        self.save_entered = True
        if self.save_gate is not None:
            try:
                await self.save_gate.wait()
            except asyncio.CancelledError:
                self.save_cancelled = True
                raise
        if self.save_error is not None:
            raise self.save_error
        self.saves.append((key, value))
        self.stored[key] = value


def _cache(backend: FakeBackend | None, **kwargs) -> SingleFlightCache:
    return SingleFlightCache(maxsize=8, ttl=60, name="t", persistence=backend, **kwargs)


async def _ok(value):
    return value


def _failing_none():
    async def fetch():
        return None
    return fetch


def _raising(exc: Exception | None = None):
    async def fetch():
        raise exc or RuntimeError("boom")
    return fetch


async def test_without_a_backend_behaviour_is_unchanged() -> None:
    cache = _cache(None)
    assert await cache.get_or_fetch("k", lambda: _ok("v1")) == "v1"
    cache._cache.clear()
    cache._stale_cache.clear()
    assert await cache.get_or_fetch("k2", _failing_none()) is None
    with pytest.raises(RuntimeError):
        await cache.get_or_fetch("k3", _raising())


async def test_a_successful_fetch_is_saved_in_the_background() -> None:
    backend = FakeBackend()
    cache = _cache(backend)
    assert await cache.get_or_fetch("k", lambda: _ok("v1")) == "v1"
    await cache.flush_persistence()
    assert backend.saves == [("k", "v1")]
    assert backend.loads == []                 # nunca se lee ante un éxito


async def test_a_memory_hit_does_not_save_again() -> None:
    backend = FakeBackend()
    cache = _cache(backend)
    await cache.get_or_fetch("k", lambda: _ok("v1"))
    await cache.get_or_fetch("k", lambda: _ok("v2"))
    await cache.flush_persistence()
    assert backend.saves == [("k", "v1")]


async def test_the_response_does_not_wait_for_the_write() -> None:
    backend = FakeBackend()
    backend.save_gate = asyncio.Event()        # la escritura queda colgada
    cache = _cache(backend)
    result = await asyncio.wait_for(cache.get_or_fetch("k", lambda: _ok("v1")), timeout=1.0)
    assert result == "v1"
    backend.save_gate.set()
    await cache.flush_persistence()
    assert backend.saves == [("k", "v1")]


async def test_a_hanging_write_is_cancelled_after_the_timeout() -> None:
    backend = FakeBackend()
    backend.save_gate = asyncio.Event()        # nunca se libera
    cache = _cache(backend, persistence_timeout=0.05)
    await cache.get_or_fetch("k", lambda: _ok("v1"))
    tasks = list(cache._background_saves)
    started = asyncio.get_running_loop().time()
    await asyncio.wait_for(cache.flush_persistence(), timeout=1.0)   # sin wait_for en la caché, se cuelga
    assert asyncio.get_running_loop().time() - started < 0.5
    assert backend.save_entered and backend.save_cancelled
    assert tasks and all(t.done() for t in tasks)
    assert backend.saves == []


async def test_write_errors_never_reach_the_caller(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    backend = FakeBackend()
    backend.save_error = RuntimeError(_SECRETO)
    cache = _cache(backend)
    assert await cache.get_or_fetch("k", lambda: _ok("v1")) == "v1"
    tasks = list(cache._background_saves)
    await cache.flush_persistence()
    assert tasks and all(t.exception() is None for t in tasks)   # la tarea terminó sin excepción
    assert _SECRETO not in caplog.text


async def test_failed_fetch_without_memory_copy_reads_the_persisted_value() -> None:
    backend = FakeBackend({"k": "persistido"})
    cache = _cache(backend)
    outcome = CacheOutcome()
    assert await cache.get_or_fetch("k", _failing_none(), outcome=outcome) == "persistido"
    assert outcome.hit is True
    assert backend.loads == ["k"]


async def test_raising_fetch_without_memory_copy_reads_the_persisted_value() -> None:
    backend = FakeBackend({"k": "persistido"})
    cache = _cache(backend)
    outcome = CacheOutcome()
    assert await cache.get_or_fetch("k", _raising(), outcome=outcome) == "persistido"
    assert outcome.hit is True


async def test_the_persisted_value_is_put_back_into_the_memory_stale_cache() -> None:
    backend = FakeBackend({"k": "persistido"})
    cache = _cache(backend)
    assert await cache.get_or_fetch("k", _failing_none()) == "persistido"
    # Mientras dure la ventana de fallo se sirve de memoria, sin volver a Redis.
    outcome = CacheOutcome()
    assert await cache.get_or_fetch("k", _failing_none(), outcome=outcome) == "persistido"
    assert outcome.hit is True
    assert backend.loads == ["k"]
    # Pasada la ventana de fallo, un nuevo fallo usa la copia de memoria: tampoco lee Redis.
    cache._failure_cache.clear()
    assert await cache.get_or_fetch("k", _failing_none()) == "persistido"
    assert backend.loads == ["k"]


async def test_a_value_read_from_the_backend_is_not_written_back() -> None:
    backend = FakeBackend({"k": "persistido"})
    cache = _cache(backend)
    await cache.get_or_fetch("k", _failing_none())
    await cache.flush_persistence()
    assert backend.saves == []


async def test_memory_stale_copy_wins_and_the_backend_is_not_read() -> None:
    backend = FakeBackend({"k": "persistido"})
    cache = _cache(backend)
    await cache.get_or_fetch("k", lambda: _ok("en-memoria"))
    cache._cache.clear()
    cache._failure_cache.clear()
    assert await cache.get_or_fetch("k", _failing_none()) == "en-memoria"
    cache._cache.clear()
    cache._failure_cache.clear()
    assert await cache.get_or_fetch("k", _raising()) == "en-memoria"
    assert backend.loads == []


async def test_nothing_persisted_keeps_the_old_failure_behaviour() -> None:
    backend = FakeBackend()
    cache = _cache(backend)
    assert await cache.get_or_fetch("k", _failing_none()) is None
    cache._failure_cache.clear()
    with pytest.raises(RuntimeError):
        await cache.get_or_fetch("k", _raising())
    assert backend.loads == ["k", "k"]


async def test_read_errors_degrade_to_no_copy(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    backend = FakeBackend({"k": "persistido"})
    backend.load_error = RuntimeError(_SECRETO)
    cache = _cache(backend)
    assert await cache.get_or_fetch("k", _failing_none()) is None
    cache._failure_cache.clear()
    with pytest.raises(RuntimeError, match="boom"):
        await cache.get_or_fetch("k", _raising())
    assert _SECRETO not in caplog.text


async def test_a_slow_read_is_cut_by_the_timeout() -> None:
    backend = FakeBackend({"k": "persistido"})
    backend.load_delay = 5.0
    cache = _cache(backend, persistence_timeout=0.05)
    started = asyncio.get_running_loop().time()
    assert await cache.get_or_fetch("k", _failing_none()) is None
    assert asyncio.get_running_loop().time() - started < 1.0


async def test_concurrent_waiters_receive_the_persisted_value() -> None:
    backend = FakeBackend({"k": "persistido"})
    cache = _cache(backend)

    async def slow_fail():
        await asyncio.sleep(0.05)
        return None

    outcomes = [CacheOutcome() for _ in range(4)]
    results = await asyncio.gather(
        *[cache.get_or_fetch("k", slow_fail, outcome=o) for o in outcomes]
    )
    assert results == ["persistido"] * 4
    assert all(o.hit for o in outcomes)
    assert backend.loads == ["k"]              # una sola lectura para todos


async def test_persist_false_skips_both_directions() -> None:
    backend = FakeBackend({"k": "persistido"})
    cache = _cache(backend)
    assert await cache.get_or_fetch("k", _failing_none(), persist=False) is None
    assert await cache.get_or_fetch("otra", lambda: _ok("v"), persist=False) == "v"
    await cache.flush_persistence()
    assert backend.loads == [] and backend.saves == []


async def test_clear_does_not_touch_the_backend() -> None:
    backend = FakeBackend()
    cache = _cache(backend)
    await cache.get_or_fetch("k", lambda: _ok("v1"))
    await cache.flush_persistence()
    cache.clear()
    assert backend.stored == {"k": "v1"}


# ---------------------------------------------------------------------------
# Presupuesto de comandos, disyuntor, decodificación defensiva y edad de la copia
# ---------------------------------------------------------------------------

class FakeWall:
    """Reloj de pared (para `saved_at`), distinto del reloj monotónico de los límites."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def wall() -> FakeWall:
    return FakeWall()


def _store(redis: FakeRedis, clock: FakeClock, wall: FakeWall | None = None, **overrides) -> RedisLastGoodStore:
    params = dict(
        name="om_current", codec=_CODEC, ttl_seconds=10800, redis_provider=lambda: redis, clock=clock,
        write_interval_seconds=1800.0, miss_memo_seconds=300.0,
    )
    if wall is not None:
        params["wall_clock"] = wall
    params.update(overrides)
    return RedisLastGoodStore(**params)


def test_default_budgets_and_ttls() -> None:
    fields = Settings.model_fields
    assert fields["openmeteo_last_good_ttl_forecast_seconds"].default == 21600   # 6 h
    assert fields["openmeteo_last_good_ttl_current_seconds"].default == 10800    # 3 h
    assert fields["openmeteo_last_good_writes_per_minute"].default == 60


# -- Escrituras: presupuesto global y ventanas acotadas ---------------------------------------

async def test_a_process_wide_budget_caps_writes_across_keys(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock, max_writes_per_minute=3)
    for i in range(5):
        await store.save(f"k{i}", _current())
    assert len(redis.sets) == 3


async def test_the_write_budget_refills_over_time(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock, max_writes_per_minute=3)     # un token cada 20 s
    for i in range(4):
        await store.save(f"k{i}", _current())
    assert len(redis.sets) == 3
    clock.now += 20.0
    await store.save("k3", _current())
    assert len(redis.sets) == 4
    await store.save("k4", _current())                        # sin token otra vez
    assert len(redis.sets) == 4


async def test_a_budget_skip_does_not_consume_the_key_window(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock, max_writes_per_minute=1)
    await store.save("a", _current())
    await store.save("b", _current())                         # sin presupuesto: se omite
    clock.now += 60.0
    await store.save("b", _current())                         # su ventana por clave seguía libre
    assert len(redis.sets) == 2


async def test_budget_skips_are_silent_debug_logs(
    redis: FakeRedis, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    store = _store(redis, clock, max_writes_per_minute=1)
    await store.save("a", _current())
    await store.save("b", _current())
    skips = [r for r in caplog.records if "write_budget" in r.getMessage()]
    assert skips and all(r.levelno == logging.DEBUG for r in skips)


async def test_write_windows_are_bounded_dropping_expired_ones_first(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock, max_tracked_keys=4, max_writes_per_minute=1000)
    for key in "abcd":
        await store.save(key, _current())
    clock.now += 1801.0
    await store.save("e", _current())
    assert list(store._last_write) == [store._redis_key("e")]


async def test_write_windows_evict_the_oldest_when_all_are_fresh(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock, max_tracked_keys=4, max_writes_per_minute=1000)
    for key in "abcd":
        await store.save(key, _current())
        clock.now += 1.0
    await store.save("e", _current())
    assert len(store._last_write) == 4
    assert store._redis_key("a") not in store._last_write
    assert store._redis_key("e") in store._last_write


async def test_a_nan_value_is_never_written(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock)
    await store.save("k1", _current(temp=float("nan")))       # no se puede leer de vuelta: ni se escribe
    assert redis.sets == []


async def test_a_hanging_write_is_cut_by_the_store_timeout(redis: FakeRedis, clock: FakeClock) -> None:
    redis.set_delay = 5.0
    store = _store(redis, clock, redis_timeout_seconds=0.02)
    await asyncio.wait_for(store.save("k1", _current()), timeout=1.0)
    assert redis.store == {}


# -- Lecturas: misses acotados, disyuntor y tiempo de espera ----------------------------------

async def test_remembered_misses_evict_the_oldest_not_everything(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock, max_tracked_keys=3)
    for key in "abcd":
        assert await store.load(key) is None
    assert len(redis.reads) == 4
    for key in "dcb":                                         # los tres más nuevos siguen recordados
        assert await store.load(key) is None
    assert len(redis.reads) == 4
    assert await store.load("a") is None                      # la más vieja fue desalojada
    assert len(redis.reads) == 5


async def test_expired_misses_are_dropped_before_evicting_fresh_ones(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock, max_tracked_keys=3)
    for key in "abc":
        await store.load(key)
    clock.now += 301.0
    await store.load("d")
    assert list(store._misses) == [store._redis_key("d")]


async def test_breaker_opens_after_consecutive_read_errors(redis: FakeRedis, clock: FakeClock) -> None:
    redis.read_error = UpstashUnavailableError("caído")
    store = _store(redis, clock)
    for key in "abc":
        assert await store.load(key) is None
    assert len(redis.reads) == 3
    assert await store.load("d") is None                      # disyuntor abierto: sin comando
    assert len(redis.reads) == 3
    clock.now += 61.0
    redis.read_error = None
    assert await store.load("d") is None                      # pasados 60 s vuelve a probar
    assert len(redis.reads) == 4


async def test_a_successful_read_resets_the_failure_count(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock)
    redis.read_error = UpstashUnavailableError("caído")
    await store.load("a")
    await store.load("b")
    redis.read_error = None
    await store.load("c")                                     # Redis respondió (sin copia): se reinicia la cuenta
    redis.read_error = UpstashUnavailableError("caído")
    await store.load("d")
    await store.load("e")
    await store.load("f")                                     # solo 2 errores seguidos antes de esta
    assert len(redis.reads) == 6


async def test_timeouts_count_towards_the_breaker(redis: FakeRedis, clock: FakeClock) -> None:
    redis.read_delay = 5.0
    store = _store(redis, clock, redis_timeout_seconds=0.02)
    for key in "abc":
        assert await store.load(key) is None
    redis.read_delay = 0.0
    assert await store.load("d") is None
    assert len(redis.reads) == 3                              # el cuarto no llegó a Redis


async def test_a_timed_out_read_is_remembered_as_a_miss(redis: FakeRedis, clock: FakeClock) -> None:
    redis.read_delay = 5.0
    store = _store(redis, clock, redis_timeout_seconds=0.02)
    assert await store.load("k") is None
    redis.read_delay = 0.0
    assert await store.load("k") is None
    assert len(redis.reads) == 1


# -- Decodificación defensiva -----------------------------------------------------------------

async def test_deeply_nested_json_is_a_remembered_miss(redis: FakeRedis, clock: FakeClock) -> None:
    store = _store(redis, clock)
    redis.store[store._redis_key("k1")] = "[" * 100_000 + "]" * 100_000
    assert await store.load("k1") is None
    assert await store.load("k1") is None
    assert len(redis.reads) == 1


async def test_oversized_raw_values_are_rejected_before_parsing(
    redis: FakeRedis, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(redis, clock)
    parsed: list[int] = []
    real_loads = json.loads
    monkeypatch.setattr("app.core.persistent_cache.json.loads", lambda *a, **k: parsed.append(1) or real_loads(*a, **k))
    redis.store[store._redis_key("big")] = '"' + "a" * 2_000_001 + '"'
    assert await store.load("big") is None
    assert parsed == []
    redis.store[store._redis_key("edge")] = "x" * 2_000_000   # en el límite sí se intenta (y no es JSON)
    assert await store.load("edge") is None
    assert parsed == [1]


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
async def test_non_finite_numbers_are_rejected(redis: FakeRedis, clock: FakeClock, constant: str) -> None:
    store = _store(redis, clock)
    await store.save("k1", _current())
    (key, text, _ex), = redis.sets
    tampered = text.replace('"temp_c":23.5', f'"temp_c":{constant}')
    assert tampered != text
    redis.store[key] = tampered
    assert await store.load("k1") is None


# -- Edad de la copia -------------------------------------------------------------------------

async def test_a_loaded_copy_reports_its_remaining_redis_life(
    redis: FakeRedis, clock: FakeClock, wall: FakeWall
) -> None:
    store = _store(redis, clock, wall)
    await store.save("k1", _current())
    wall.advance(3600.0)
    loaded = await store.load("k1")
    assert loaded.value == _current()
    assert loaded.remaining_seconds == pytest.approx(10800.0 - 3600.0)


async def test_a_copy_older_than_the_ttl_is_rejected_and_remembered(
    redis: FakeRedis, clock: FakeClock, wall: FakeWall, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    store = _store(redis, clock, wall)
    await store.save("k1", _current())
    wall.advance(10801.0)
    assert await store.load("k1") is None
    assert "expired" in caplog.text
    assert await store.load("k1") is None
    assert len(redis.reads) == 1


@pytest.mark.parametrize("saved_at", [None, "ayer", "2026-10-08T12:00:00", 12345, "2026-10-08T13:00:00+00:00"],
                         ids=["missing", "garbage", "naive", "number", "future"])
async def test_unusable_saved_at_is_rejected(
    redis: FakeRedis, clock: FakeClock, wall: FakeWall, saved_at
) -> None:
    store = _store(redis, clock, wall)
    await store.save("k1", _current())
    (key, text, _ex), = redis.sets
    envelope = json.loads(text)
    if saved_at is None:
        del envelope["saved_at"]
    else:
        envelope["saved_at"] = saved_at
    redis.store[key] = json.dumps(envelope)
    assert await store.load("k1") is None


async def test_a_small_clock_skew_into_the_future_is_tolerated(
    redis: FakeRedis, clock: FakeClock, wall: FakeWall
) -> None:
    store = _store(redis, clock, wall)
    await store.save("k1", _current())
    wall.advance(-30.0)                                       # otro proceso con el reloj adelantado
    loaded = await store.load("k1")
    assert loaded is not None and loaded.remaining_seconds == pytest.approx(10800.0)


# -- SingleFlightCache: vida acotada de la copia recuperada y costo de una lectura lenta -------

async def test_a_recovered_copy_cannot_outlive_its_remaining_redis_life() -> None:
    clock = FakeClock()
    backend = FakeBackend({"k": Persisted("persistido", 30.0)})
    cache = _cache(backend, clock=clock)
    assert await cache.get_or_fetch("k", _failing_none()) == "persistido"
    clock.now += 10.0
    cache._failure_cache.clear()
    assert await cache.get_or_fetch("k", _failing_none()) == "persistido"
    assert backend.loads == ["k"]                              # todavía vive en memoria
    clock.now += 21.0                                          # 31 s > 30 s de vida que le quedaban
    cache._failure_cache.clear()
    backend.stored.clear()                                     # y Redis ya la perdió
    assert await cache.get_or_fetch("k", _failing_none()) is None
    assert backend.loads == ["k", "k"]


async def test_the_recovered_lifetime_also_applies_on_the_raising_path() -> None:
    clock = FakeClock()
    backend = FakeBackend({"k": Persisted("persistido", 30.0)})
    cache = _cache(backend, clock=clock)
    assert await cache.get_or_fetch("k", _raising()) == "persistido"
    clock.now += 31.0
    cache._failure_cache.clear()
    backend.stored.clear()
    with pytest.raises(RuntimeError):
        await cache.get_or_fetch("k", _raising())


async def test_a_fresh_success_lifts_the_recovered_deadline() -> None:
    clock = FakeClock()
    backend = FakeBackend({"k": Persisted("persistido", 30.0)})
    cache = _cache(backend, clock=clock)
    await cache.get_or_fetch("k", _failing_none())
    cache._failure_cache.clear()
    assert await cache.get_or_fetch("k", lambda: _ok("nuevo")) == "nuevo"
    clock.now += 500.0
    cache._cache.clear()
    cache._failure_cache.clear()
    assert await cache.get_or_fetch("k", _failing_none()) == "nuevo"   # copia fresca: sin vencimiento
    assert backend.loads == ["k"]


async def test_a_copy_without_remaining_life_is_not_used() -> None:
    backend = FakeBackend({"k": Persisted("persistido", 0.0)})
    cache = _cache(backend)
    assert await cache.get_or_fetch("k", _failing_none()) is None


async def test_a_slow_read_costs_its_timeout_once_per_failure_window() -> None:
    backend = FakeBackend({"k": "persistido"})
    backend.load_delay = 5.0
    cache = _cache(backend, persistence_timeout=0.05)
    for _ in range(3):
        assert await cache.get_or_fetch("k", _failing_none()) is None
    assert backend.loads == ["k"]                              # la ventana de fallo de 15 s absorbe las repeticiones
    cache._failure_cache.clear()                               # pasaron los 15 s
    assert await cache.get_or_fetch("k", _failing_none()) is None
    assert backend.loads == ["k", "k"]
