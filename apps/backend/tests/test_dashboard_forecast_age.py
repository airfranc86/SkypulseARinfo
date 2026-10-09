"""`forecast_fetched_at` del dashboard: la edad real del pronóstico que alimenta la respuesta.

Es la hora MÁS VIEJA de los pedidos a Open-Meteo que alimentan la respuesta (cada modelo diario presente,
la serie horaria best_match y la de ECMWF): un solo dato viejo hace viejo al pronóstico entero. Es un
campo aditivo; `fetched_at` sigue siendo la hora en que el servidor arma la respuesta. Sin ninguna fecha
(copias guardadas antes del campo) queda None = edad desconocida. Nada toca la red.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.openmeteo import MultiModelDailyData, merge_hourly_ecmwf, oldest_forecast_fetched_at
from tests.test_dashboard import _make_current_response, _make_hourly, _make_multi_model

HOURLY_FN = "app.routers.weather.get_hourly_forecast_ext"
ECMWF_FN = "app.routers.weather.get_hourly_forecast_ecmwf"
DASHBOARD_URL = "/api/weather/dashboard?lat=-31.4&lon=-64.2"

NOW = datetime.now(timezone.utc)


def _ago(**kwargs) -> datetime:
    return NOW - timedelta(**kwargs)


def _multi(*, gfs: datetime | None, ecmwf: datetime | None, icon: datetime | None = None) -> MultiModelDailyData:
    base = _make_multi_model()
    daily = next(iter(base.models.values()))
    models = {
        "gfs_seamless": dataclasses.replace(daily, fetched_at=gfs),
        "ecmwf_ifs025": dataclasses.replace(daily, fetched_at=ecmwf),
    }
    if icon is not None:
        models["icon_seamless"] = dataclasses.replace(daily, fetched_at=icon)
    return dataclasses.replace(base, models=models)


def _hourly(fetched_at: datetime | None):
    return dataclasses.replace(_make_hourly(), fetched_at=fetched_at)


async def _dashboard(client: AsyncClient, *, daily, hourly, ecmwf) -> dict:
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=daily),
        patch(HOURLY_FN, new_callable=AsyncMock, return_value=hourly),
        patch(ECMWF_FN, new_callable=AsyncMock, return_value=ecmwf),
    ):
        response = await client.get(DASHBOARD_URL)
    assert response.status_code == 200
    return response.json()


def _parsed(body: dict) -> datetime | None:
    raw = body["forecast_fetched_at"]
    return None if raw is None else datetime.fromisoformat(raw)


# ---------------------------------------------------------------------------
# oldest_forecast_fetched_at (pura)
# ---------------------------------------------------------------------------

class TestOldestForecastFetchedAt:

    def test_picks_the_oldest_date(self):
        old, mid, new = _ago(hours=5), _ago(hours=3), _ago(minutes=5)

        assert oldest_forecast_fetched_at(new, old, mid) == old

    def test_ignores_missing_dates(self):
        only = _ago(hours=1)

        assert oldest_forecast_fetched_at(None, only, None) == only

    def test_is_none_when_no_series_has_a_date(self):
        assert oldest_forecast_fetched_at(None, None) is None
        assert oldest_forecast_fetched_at() is None

    def test_a_naive_date_is_read_as_utc_and_compared_without_error(self):
        aware = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
        naive_older = datetime(2026, 10, 8, 9, 0)

        result = oldest_forecast_fetched_at(aware, naive_older)

        assert result == naive_older.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDashboardForecastFetchedAt:

    @pytest.mark.asyncio
    async def test_it_is_the_oldest_of_the_daily_models(self, async_client: AsyncClient):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(minutes=10), ecmwf=_ago(hours=4)),
            hourly=_hourly(_ago(minutes=5)),
            ecmwf=_hourly(_ago(minutes=5)),
        )

        assert _parsed(body) == _ago(hours=4)

    @pytest.mark.asyncio
    async def test_it_can_be_the_best_match_hourly_series(self, async_client: AsyncClient):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(minutes=10), ecmwf=_ago(minutes=20)),
            hourly=_hourly(_ago(hours=3)),
            ecmwf=_hourly(_ago(minutes=5)),
        )

        assert _parsed(body) == _ago(hours=3)

    @pytest.mark.asyncio
    async def test_it_can_be_the_ecmwf_hourly_series(self, async_client: AsyncClient):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(minutes=10), ecmwf=_ago(minutes=20)),
            hourly=_hourly(_ago(minutes=5)),
            ecmwf=_hourly(_ago(hours=2, minutes=30)),
        )

        assert _parsed(body) == _ago(hours=2, minutes=30)

    @pytest.mark.asyncio
    async def test_a_model_present_in_the_response_counts_even_if_it_is_not_gfs_or_ecmwf(
        self, async_client: AsyncClient
    ):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(minutes=10), ecmwf=_ago(minutes=20), icon=_ago(hours=6)),
            hourly=_hourly(_ago(minutes=5)),
            ecmwf=None,
        )

        assert _parsed(body) == _ago(hours=6)

    @pytest.mark.asyncio
    async def test_a_failed_ecmwf_hourly_series_does_not_count_nor_break_it(self, async_client: AsyncClient):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(minutes=10), ecmwf=_ago(minutes=20)),
            hourly=_hourly(_ago(minutes=30)),
            ecmwf=None,
        )

        assert _parsed(body) == _ago(minutes=30)

    @pytest.mark.asyncio
    async def test_series_without_a_date_are_skipped(self, async_client: AsyncClient):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=None, ecmwf=_ago(hours=1)),
            hourly=_hourly(None),
            ecmwf=_hourly(None),
        )

        assert _parsed(body) == _ago(hours=1)

    @pytest.mark.asyncio
    async def test_it_is_none_when_nothing_carries_a_date(self, async_client: AsyncClient):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=None, ecmwf=None),
            hourly=_hourly(None),
            ecmwf=_hourly(None),
        )

        assert body["forecast_fetched_at"] is None

    @pytest.mark.asyncio
    async def test_without_any_hourly_series_it_uses_the_daily_models(self, async_client: AsyncClient):
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(hours=2), ecmwf=_ago(hours=1)),
            hourly=None,
            ecmwf=None,
        )

        assert _parsed(body) == _ago(hours=2)

    @pytest.mark.asyncio
    async def test_an_ecmwf_hourly_series_that_is_not_overlaid_does_not_count(self, async_client: AsyncClient):
        # Sin la serie best_match no hay tira horaria: ECMWF no alimenta nada, su edad no cuenta.
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(hours=2), ecmwf=_ago(hours=1)),
            hourly=None,
            ecmwf=_hourly(_ago(hours=9)),
        )

        assert _parsed(body) == _ago(hours=2)

    @pytest.mark.asyncio
    async def test_fetched_at_stays_the_time_the_response_was_built(self, async_client: AsyncClient):
        before = datetime.now(timezone.utc)
        body = await _dashboard(
            async_client,
            daily=_multi(gfs=_ago(hours=5), ecmwf=_ago(hours=5)),
            hourly=_hourly(_ago(hours=5)),
            ecmwf=_hourly(_ago(hours=5)),
        )
        after = datetime.now(timezone.utc)

        built = datetime.fromisoformat(body["fetched_at"])
        assert before <= built <= after
        assert _parsed(body) < built - timedelta(hours=4)


# ---------------------------------------------------------------------------
# merge_hourly_ecmwf propaga la fecha más vieja
# ---------------------------------------------------------------------------

class TestMergedSeriesCarriesTheOldestDate:

    def test_the_merged_series_takes_the_oldest_of_both(self):
        old, new = _ago(hours=4), _ago(minutes=3)

        assert merge_hourly_ecmwf(_hourly(new), _hourly(old)).fetched_at == old
        assert merge_hourly_ecmwf(_hourly(old), _hourly(new)).fetched_at == old

    def test_without_ecmwf_it_keeps_the_base_date(self):
        base_date = _ago(hours=1)

        assert merge_hourly_ecmwf(_hourly(base_date), None).fetched_at == base_date

    def test_a_series_without_a_date_does_not_hide_the_other_one(self):
        known = _ago(hours=2)

        assert merge_hourly_ecmwf(_hourly(None), _hourly(known)).fetched_at == known
        assert merge_hourly_ecmwf(_hourly(known), _hourly(None)).fetched_at == known
        assert merge_hourly_ecmwf(_hourly(None), _hourly(None)).fetched_at is None

    def test_it_does_not_mutate_its_inputs(self):
        base, ecmwf = _hourly(_ago(minutes=1)), _hourly(_ago(hours=3))
        base_date, ecmwf_date = base.fetched_at, ecmwf.fetched_at

        merge_hourly_ecmwf(base, ecmwf)

        assert (base.fetched_at, ecmwf.fetched_at) == (base_date, ecmwf_date)
