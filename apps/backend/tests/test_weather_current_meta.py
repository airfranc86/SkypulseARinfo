"""Tests de aggregate_current: SMN desactivado por defecto, cache_hit real y observed_at (FRA-319).

El feed `map_items/weather` del SMN está congelado desde 2022 (sin campo `date`), así que el
"ahora" nunca podía usar el SMN. Por defecto la llamada está apagada (`settings.smn_enabled`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core.config import Settings
from app.services.weather_aggregator import aggregate_current
from tests.conftest import OPENMETEO_SAMPLE_PAYLOAD

SMN_URL = "https://ws.smn.gob.ar/map_items/weather"
OM_URL = "https://api.open-meteo.com/v1/forecast"
CORDOBA = (-31.4135, -64.181)

# `current.time` del payload de muestra: 14:00 hora Argentina (UTC-3) = 17:00 UTC.
OM_SAMPLE_OBSERVED_AT = datetime(2024, 1, 15, 17, 0, tzinfo=timezone.utc)

# Feed congelado real: sin `date`, solo `updated` de 2022.
FROZEN_SMN_PAYLOAD = [
    {
        "name": "CÓRDOBA AEROPUERTO",
        "lat": -31.323,
        "lon": -64.208,
        "updated": 1658800000,
        "weather": {"temp": "22", "humidity": "55", "wind_speed": "15", "pressure": "1013"},
    },
]


def _fresh_smn_payload(age_minutes: int = 30) -> tuple[list[dict], datetime]:
    """Estación cercana a Córdoba con observación reciente (SMN publica en hora local UTC-3)."""
    observed_at = (datetime.now(timezone.utc) - timedelta(minutes=age_minutes)).replace(
        second=0, microsecond=0
    )
    payload = [
        {
            "name": "CÓRDOBA AEROPUERTO",
            "lat": -31.323,
            "lon": -64.208,
            "date": (observed_at - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"),
            "weather": {"temp": "22", "humidity": "55", "wind_speed": "15", "pressure": "1013"},
        },
    ]
    return payload, observed_at


# ---------------------------------------------------------------------------
# SMN desactivado por defecto
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_smn_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SMN_ENABLED", raising=False)

    assert Settings(_env_file=None).smn_enabled is False


@pytest.mark.unit
def test_smn_enabled_can_be_set_from_the_environment(monkeypatch):
    monkeypatch.setenv("SMN_ENABLED", "true")

    assert Settings(_env_file=None).smn_enabled is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_disabled_smn_makes_no_smn_http_call():
    with respx.mock(assert_all_called=False) as mock:
        smn_route = mock.get(SMN_URL).mock(return_value=httpx.Response(200, json=FROZEN_SMN_PAYLOAD))
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))

        result = await aggregate_current(*CORDOBA)

    assert smn_route.call_count == 0
    assert result.meta.source == "openmeteo"
    assert result.meta.reason == "smn_disabled"
    assert result.meta.station is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disabled_smn_never_awaits_get_nearest_observation():
    with (
        patch(
            "app.services.weather_aggregator.smn.get_nearest_observation",
            new_callable=AsyncMock,
        ) as mock_smn,
        respx.mock(assert_all_called=False) as mock,
    ):
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))

        result = await aggregate_current(*CORDOBA)

    mock_smn.assert_not_awaited()
    assert result.meta.reason == "smn_disabled"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_disabled_smn_reason_reaches_the_router_payload(async_client: AsyncClient):
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))

        response = await async_client.get("/api/weather/current?lat=-31.4135&lon=-64.181")

    assert response.status_code == 200
    meta = response.json()["meta"]
    assert meta["source"] == "openmeteo"
    assert meta["reason"] == "smn_disabled"
    assert meta["observed_at"] is not None


# ---------------------------------------------------------------------------
# SMN activado — regresión del comportamiento verificado (feed congelado)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_enabled_smn_with_frozen_feed_is_still_stale(smn_enabled):
    with respx.mock(assert_all_called=False) as mock:
        smn_route = mock.get(SMN_URL).mock(
            return_value=httpx.Response(200, json=FROZEN_SMN_PAYLOAD)
        )
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))

        result = await aggregate_current(*CORDOBA)

    assert smn_route.call_count == 1
    assert result.meta.source == "openmeteo"
    assert result.meta.reason == "smn_stale"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_enabled_smn_with_fresh_station_uses_smn(smn_enabled):
    payload, observed_at = _fresh_smn_payload()

    with respx.mock(assert_all_called=False) as mock:
        mock.get(SMN_URL).mock(return_value=httpx.Response(200, json=payload))
        om_route = mock.get(OM_URL).mock(
            return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)
        )

        result = await aggregate_current(*CORDOBA)

    assert om_route.call_count == 0
    assert result.meta.source == "smn"
    assert result.meta.reason == "smn_nearby_fresh"
    assert result.meta.observed_at == observed_at


# ---------------------------------------------------------------------------
# cache_hit real
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_openmeteo_cache_hit_is_false_then_true():
    with respx.mock(assert_all_called=False) as mock:
        om_route = mock.get(OM_URL).mock(
            return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)
        )

        first = await aggregate_current(*CORDOBA)
        second = await aggregate_current(*CORDOBA)

    assert om_route.call_count == 1
    assert first.meta.cache_hit is False
    assert second.meta.cache_hit is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_smn_cache_hit_is_false_then_true(smn_enabled):
    payload, _ = _fresh_smn_payload()

    with respx.mock(assert_all_called=False) as mock:
        smn_route = mock.get(SMN_URL).mock(return_value=httpx.Response(200, json=payload))

        first = await aggregate_current(*CORDOBA)
        second = await aggregate_current(*CORDOBA)

    assert smn_route.call_count == 1
    assert first.meta.source == second.meta.source == "smn"
    assert first.meta.cache_hit is False
    assert second.meta.cache_hit is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_stale_while_error_serve_counts_as_a_cache_hit():
    """TTL fresco vencido + fetch fallido: se sirve el último dato bueno, que viene del caché."""
    import app.services.openmeteo as om_module

    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))
        await aggregate_current(*CORDOBA)

    om_module._CACHE_CURRENT._cache.clear()  # vence el TTL fresco; sigue la copia stale

    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(side_effect=httpx.ConnectError("rate limited"))
        result = await aggregate_current(*CORDOBA)

    assert result.meta.source == "openmeteo"
    assert result.meta.cache_hit is True


# ---------------------------------------------------------------------------
# observed_at
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_openmeteo_current_time_is_exposed_as_utc_observed_at():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))

        result = await aggregate_current(*CORDOBA)

    assert result.meta.observed_at == OM_SAMPLE_OBSERVED_AT
    assert result.meta.observed_at.utcoffset() == timedelta(0)
    # La semántica de `stale` no cambia: mide la edad de NUESTRO dato, no la observación.
    assert result.meta.stale is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_openmeteo_without_current_time_leaves_observed_at_none():
    payload = {
        **OPENMETEO_SAMPLE_PAYLOAD,
        "current": {k: v for k, v in OPENMETEO_SAMPLE_PAYLOAD["current"].items() if k != "time"},
    }

    with respx.mock(assert_all_called=False) as mock:
        mock.get(OM_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await aggregate_current(*CORDOBA)

    assert result.meta.source == "openmeteo"
    assert result.meta.observed_at is None
