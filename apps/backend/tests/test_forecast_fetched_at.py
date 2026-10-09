"""Hora real del pedido a Open-Meteo en las dataclasses de pronóstico (edad del pronóstico).

El "Actualizado" de la web debe mostrar cuándo se obtuvo el pronóstico y no cuándo el servidor armó la
respuesta: una copia del último dato bueno (hasta 6 h) diría "ahora" sobre un dato viejo. Cubre:
- Cada `_fetch` de `services/openmeteo.py` deja `fetched_at` (UTC con zona).
- El códec lo conserva en la ida y vuelta, y una copia guardada ANTES del campo (la forma del esquema
  de producción de hoy) se sigue leyendo, con None = "edad desconocida".
- Una copia servida desde Redis conserva la hora ORIGINAL del pedido, no la de la lectura.
Nada toca la red: respx y Redis en memoria.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.core.dataclass_codec import DataclassCodec
from app.core.persistent_cache import RedisLastGoodStore
from app.services.openmeteo import (
    DailyForecastDataExt,
    HourlyForecastExt,
    get_daily_forecast_ext,
    get_hourly_forecast_ecmwf,
    get_hourly_forecast_ext,
    get_multi_model_daily,
)
from tests.test_dataclass_codec import _daily, _hourly
from tests.test_openmeteo_extended import _make_daily_ext_payload
from tests.test_openmeteo_hourly_ecmwf import _ecmwf_payload
from tests.test_persistent_cache import FakeClock, FakeRedis

OM_URL = "https://api.open-meteo.com/v1/forecast"
LAT, LON = -31.4135, -64.181

_CODEC = DataclassCodec(DailyForecastDataExt, HourlyForecastExt)
_FETCHED = datetime(2026, 10, 8, 12, 15, 30, 250000, tzinfo=timezone.utc)


def _assert_taken_between(value: datetime | None, before: datetime, after: datetime) -> None:
    assert isinstance(value, datetime)
    assert value.tzinfo is not None and value.utcoffset() == timedelta(0)
    assert before <= value <= after


# ---------------------------------------------------------------------------
# Cada _fetch marca la hora del pedido
# ---------------------------------------------------------------------------

class TestFetchersStampTheRequestTime:

    @pytest.mark.asyncio
    async def test_daily_forecast_stamps_fetched_at(self):
        before = datetime.now(timezone.utc)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_make_daily_ext_payload(3)))
            result = await get_daily_forecast_ext(LAT, LON, days=3)
        after = datetime.now(timezone.utc)

        assert isinstance(result, DailyForecastDataExt)
        _assert_taken_between(result.fetched_at, before, after)

    @pytest.mark.asyncio
    async def test_daily_forecast_of_a_single_model_stamps_fetched_at(self):
        before = datetime.now(timezone.utc)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_make_daily_ext_payload(3)))
            result = await get_daily_forecast_ext(LAT, LON, days=3, model="ecmwf_ifs025")
        after = datetime.now(timezone.utc)

        _assert_taken_between(result.fetched_at, before, after)

    @pytest.mark.asyncio
    async def test_every_model_of_the_multi_model_daily_carries_its_own_fetched_at(self):
        before = datetime.now(timezone.utc)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_make_daily_ext_payload(3)))
            result = await get_multi_model_daily(LAT, LON, days=3)
        after = datetime.now(timezone.utc)

        assert set(result.models) == {"gfs_seamless", "ecmwf_ifs025"}
        for daily in result.models.values():
            _assert_taken_between(daily.fetched_at, before, after)

    @pytest.mark.asyncio
    async def test_best_match_hourly_forecast_stamps_fetched_at(self):
        before = datetime.now(timezone.utc)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_ecmwf_payload()))
            result = await get_hourly_forecast_ext(LAT, LON, days=2)
        after = datetime.now(timezone.utc)

        assert isinstance(result, HourlyForecastExt)
        _assert_taken_between(result.fetched_at, before, after)

    @pytest.mark.asyncio
    async def test_ecmwf_hourly_forecast_stamps_fetched_at(self):
        before = datetime.now(timezone.utc)
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_ecmwf_payload()))
            result = await get_hourly_forecast_ecmwf(LAT, LON, days=7)
        after = datetime.now(timezone.utc)

        assert isinstance(result, HourlyForecastExt)
        _assert_taken_between(result.fetched_at, before, after)

    @pytest.mark.asyncio
    async def test_a_cache_hit_keeps_the_original_request_time(self):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_make_daily_ext_payload(3)))
            first = await get_daily_forecast_ext(LAT, LON, days=3)
            second = await get_daily_forecast_ext(LAT, LON, days=3)

        assert second.fetched_at == first.fetched_at


# ---------------------------------------------------------------------------
# Códec: ida y vuelta y copias viejas sin el campo
# ---------------------------------------------------------------------------

def _roundtrip(value):
    type_name, data = _CODEC.encode(value)
    return _CODEC.decode(type_name, json.loads(json.dumps(data)))


class TestCodecKeepsFetchedAt:

    def test_daily_roundtrip_keeps_fetched_at(self):
        value = _daily(fetched_at=_FETCHED)

        restored = _roundtrip(value)

        assert restored.fetched_at == _FETCHED
        assert restored == value

    def test_hourly_roundtrip_keeps_fetched_at(self):
        value = _hourly(fetched_at=_FETCHED)

        restored = _roundtrip(value)

        assert restored.fetched_at == _FETCHED
        assert restored == value

    def test_fetched_at_is_none_by_default(self):
        assert _daily().fetched_at is None
        assert _hourly().fetched_at is None

    @pytest.mark.parametrize("make", [_daily, _hourly], ids=["daily", "hourly"])
    def test_a_copy_written_before_the_field_existed_still_decodes_with_none(self, make):
        type_name, data = _CODEC.encode(make(fetched_at=_FETCHED))
        legacy = json.loads(json.dumps(data))
        assert "fetched_at" in legacy             # el esquema nuevo lo escribe...
        del legacy["fetched_at"]                  # ...y la copia que dejó el código anterior no

        restored = _CODEC.decode(type_name, legacy)

        assert restored.fetched_at is None
        assert restored == make()

    def test_the_encoded_form_is_an_iso_string_with_its_zone(self):
        _type_name, data = _CODEC.encode(_daily(fetched_at=_FETCHED))

        assert data["fetched_at"] == "2026-10-08T12:15:30.250000+00:00"


# ---------------------------------------------------------------------------
# Almacén de Redis: la copia vieja y la nueva
# ---------------------------------------------------------------------------

@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def store(redis: FakeRedis) -> RedisLastGoodStore:
    return RedisLastGoodStore(
        name="om_forecast", codec=_CODEC, ttl_seconds=21600, redis_provider=lambda: redis,
        clock=FakeClock(), write_interval_seconds=0.0, miss_memo_seconds=300.0,
    )


@pytest.mark.asyncio
async def test_a_stored_copy_serves_the_original_request_time(
    store: RedisLastGoodStore, redis: FakeRedis
) -> None:
    await store.save("k1", _daily(fetched_at=_FETCHED))

    loaded = await store.load("k1")

    assert loaded.value.fetched_at == _FETCHED


@pytest.mark.asyncio
async def test_a_stored_copy_written_by_the_previous_code_loads_with_unknown_age(
    store: RedisLastGoodStore, redis: FakeRedis
) -> None:
    await store.save("k1", _daily(fetched_at=_FETCHED))
    (key, text, _ex), = redis.sets
    envelope = json.loads(text)
    del envelope["data"]["fetched_at"]            # forma del esquema que hoy escribe producción
    redis.store[key] = json.dumps(envelope)

    loaded = await store.load("k1")

    assert loaded is not None
    assert loaded.value == _daily()
    assert loaded.value.fetched_at is None
