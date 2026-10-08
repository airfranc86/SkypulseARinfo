"""La etiqueta de luz del arco del día (day_arc.daylight_label) con el reloj congelado.

Mientras es de día muestra la luz que QUEDA hasta la puesta, no la duración del día: "Quedan 8h 23m de luz".
El resto de las ramas ("Sale en", "Amanece en", "Hoy: ...") se fijan acá tal como estaban.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.rate_limit import limiter
from app.services.openmeteo import MultiModelDailyData
from tests.helpers_caracterizacion_aeronautica import freeze_clock
from tests.test_dashboard import _dashboard_mocks, _make_multi_model

AR_OFFSET = timedelta(hours=-3)
DAY = "2026-10-08"


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    """The dashboard is limited to 30 requests per minute for the whole session: do not eat other tests' share."""
    limiter.reset()
    yield
    limiter.reset()


def _ar(hour: int, minute: int = 0) -> datetime:
    """A local Argentina clock time of DAY (UTC-3), as the UTC instant the router reads."""
    local = datetime.fromisoformat(f"{DAY}T{hour:02d}:{minute:02d}:00")
    return (local - AR_OFFSET).replace(tzinfo=timezone.utc)


def _multi_with_sun(sunrise: str, sunset: str, daylight_seconds: float) -> MultiModelDailyData:
    base = _make_multi_model()
    models = {
        name: replace(
            daily,
            sunrise=[f"{DAY}T{sunrise}"] + list(daily.sunrise[1:]),
            sunset=[f"{DAY}T{sunset}"] + list(daily.sunset[1:]),
            daylight_seconds=[daylight_seconds] * len(daily.daylight_seconds),
        )
        for name, daily in base.models.items()
    }
    return replace(base, models=models)


async def _label(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    now: datetime,
    *,
    sunrise: str = "06:45",
    sunset: str = "19:23",
    daylight_seconds: float = 45480.0,  # 12h 38m
    tomorrow_sunrise: str | None = None,
) -> str:
    freeze_clock(monkeypatch, now, "app.routers.weather")
    daily = _multi_with_sun(sunrise, sunset, daylight_seconds)
    if tomorrow_sunrise is not None:
        for model in daily.models.values():
            model.sunrise[1] = f"2026-10-09T{tomorrow_sunrise}"
    with _dashboard_mocks(daily=daily):
        response = await client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")
    assert response.status_code == 200
    return response.json()["day_arc"]["daylight_label"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daytime_label_says_how_much_light_is_left(async_client: AsyncClient, monkeypatch):
    """11:00 with sunset at 19:23: 8h 23m are left (the day lasts 12h 38m, which is another number)."""
    label = await _label(async_client, monkeypatch, _ar(11, 0))
    assert label == "Quedan 8h 23m de luz"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daytime_label_under_an_hour_shows_only_minutes(async_client: AsyncClient, monkeypatch):
    """Same pattern as "Sale en 45m": no "0h" when less than an hour is left."""
    label = await _label(async_client, monkeypatch, _ar(18, 38))
    assert label == "Quedan 45m de luz"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_daytime_label_pads_the_minutes_after_an_hour(async_client: AsyncClient, monkeypatch):
    label = await _label(async_client, monkeypatch, _ar(17, 18))
    assert label == "Quedan 2h 05m de luz"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_before_sunrise_label_is_unchanged(async_client: AsyncClient, monkeypatch):
    assert await _label(async_client, monkeypatch, _ar(5, 15)) == "Sale en 1h 30m"
    assert await _label(async_client, monkeypatch, _ar(6, 30)) == "Sale en 15m"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_after_sunset_label_counts_down_to_dawn(async_client: AsyncClient, monkeypatch):
    label = await _label(async_client, monkeypatch, _ar(21, 0), tomorrow_sunrise="06:44")
    assert label == "Amanece en 9h 44m"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_after_sunset_without_tomorrow_shows_the_day_length(async_client: AsyncClient, monkeypatch):
    """The same-day sunrise at index 1 is already past: the label falls back to "Hoy: <day length>"."""
    label = await _label(async_client, monkeypatch, _ar(21, 0))
    assert label == "Hoy: 12h 38m de luz"
