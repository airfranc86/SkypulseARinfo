"""Tests para el cliente Open-Meteo."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import respx
import httpx

import app.services.openmeteo as om_module
from app.core import usage_counter
from app.core.cache import CacheOutcome
from app.services.openmeteo import get_current
from tests.conftest import OPENMETEO_SAMPLE_PAYLOAD


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_returns_dataclass():
    """Debe parsear el payload de Open-Meteo y devolver el dataclass."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)
        )
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.temp_c == pytest.approx(23.5)
    assert result.feels_like_c == pytest.approx(22.1)
    assert result.humidity == pytest.approx(52.0)
    assert result.wind_speed_kmh == pytest.approx(18.0)
    assert result.wind_dir_deg == pytest.approx(270.0)
    assert result.pressure_hpa == pytest.approx(1014.2)
    assert result.precip_1h_mm == pytest.approx(0.0)
    assert result.cloud_cover == pytest.approx(10.0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_returns_none_on_timeout():
    with respx.mock() as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        result = await get_current(-34.6, -58.4)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_returns_none_on_5xx():
    with respx.mock() as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(500)
        )
        result = await get_current(-34.6, -58.4)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_uses_best_match_by_default():
    """Sin parámetro 'models' → Open-Meteo usa best_match automáticamente.
    ecmwf_ifs04 fue removido porque tiene delay de publicación y devuelve nulls
    para el slot actual, lo que dispara all_sources_unavailable en producción."""
    captured_request = None

    with respx.mock(assert_all_called=False) as mock:
        def capture(request: httpx.Request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)

        mock.get("https://api.open-meteo.com/v1/forecast").mock(side_effect=capture)
        await get_current(-31.4, -64.2)

    assert captured_request is not None
    params = dict(httpx.URL(str(captured_request.url)).params)
    assert "models" not in params, "No debe forzar modelo: Open-Meteo elige best_match"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_sends_wind_speed_in_kmh():
    """El request debe solicitar wind_speed_unit=kmh."""
    captured_request = None

    with respx.mock(assert_all_called=False) as mock:
        def capture(request: httpx.Request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)

        mock.get("https://api.open-meteo.com/v1/forecast").mock(side_effect=capture)
        await get_current(-31.4, -64.2)

    assert captured_request is not None
    params = dict(httpx.URL(str(captured_request.url)).params)
    assert params.get("wind_speed_unit") == "kmh"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_requests_and_parses_wind_gusts():
    """FRA-320: `wind_gusts_10m` se pide en `current` y llega como `wind_gust_kmh`."""
    import copy
    payload = copy.deepcopy(OPENMETEO_SAMPLE_PAYLOAD)
    payload["current"]["wind_gusts_10m"] = 31.7

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await get_current(-31.4, -64.2)

    assert "wind_gusts_10m" in route.calls.last.request.url.params["current"].split(",")
    assert result is not None
    assert result.wind_gust_kmh == pytest.approx(31.7)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_leaves_wind_gust_none_when_missing():
    """Sin `wind_gusts_10m` en la respuesta (caché vieja, otro modelo) la ráfaga queda en None."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)
        )
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.wind_gust_kmh is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_normalizes_wind_dir_360_to_0():
    """Regresión: Open-Meteo devuelve 360.0 (Norte) que el schema rechazaba con lt=360.
    Debe normalizarse a 0.0 antes de llegar al schema."""
    import copy
    payload = copy.deepcopy(OPENMETEO_SAMPLE_PAYLOAD)
    payload["current"]["wind_direction_10m"] = 360.0

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.wind_dir_deg == pytest.approx(0.0), (
        "360° debe normalizarse a 0° (Norte meteorológico)"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_records_open_meteo_usage(monkeypatch):
    """Cada fetch real a Open-Meteo debe registrar uso vía usage_counter.record('open_meteo')."""
    from unittest.mock import MagicMock

    mock_record = MagicMock()
    monkeypatch.setattr(usage_counter, "record", mock_record)

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)
        )
        await get_current(-31.4, -64.2)

    mock_record.assert_called_once_with("open_meteo")


# ---------------------------------------------------------------------------
# observed_at — hora de observación que reporta Open-Meteo (FRA-319)
# ---------------------------------------------------------------------------

_OM_URL = "https://api.open-meteo.com/v1/forecast"


def _payload_with_time(value: object) -> dict:
    """Copia del payload de muestra con `current.time` reemplazado (o ausente si value es None)."""
    current = {k: v for k, v in OPENMETEO_SAMPLE_PAYLOAD["current"].items() if k != "time"}
    if value is not None:
        current["time"] = value
    return {**OPENMETEO_SAMPLE_PAYLOAD, "current": current}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_parses_current_time_as_utc_observed_at():
    """current.time viene en hora Argentina (UTC-3) sin sufijo: 14:00 local = 17:00 UTC."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.observed_at == datetime(2024, 1, 15, 17, 0, tzinfo=timezone.utc)
    assert result.observed_at.utcoffset() == timedelta(0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_current_respects_an_explicit_offset_in_current_time():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_OM_URL).mock(
            return_value=httpx.Response(200, json=_payload_with_time("2024-01-15T14:00:00+00:00"))
        )
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.observed_at == datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("bad_time", [None, "", "no-es-una-fecha", 12345])
async def test_get_current_leaves_observed_at_none_when_time_is_unusable(bad_time: object):
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_OM_URL).mock(return_value=httpx.Response(200, json=_payload_with_time(bad_time)))
        result = await get_current(-31.4, -64.2)

    assert result is not None
    assert result.temp_c == pytest.approx(23.5)
    assert result.observed_at is None


# ---------------------------------------------------------------------------
# cache_outcome — procedencia real del dato (FRA-319)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_outcome_reports_miss_then_hit():
    first_outcome, second_outcome = CacheOutcome(), CacheOutcome()

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(_OM_URL).mock(
            return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)
        )
        first = await get_current(-31.4, -64.2, cache_outcome=first_outcome)
        second = await get_current(-31.4, -64.2, cache_outcome=second_outcome)

    assert route.call_count == 1
    assert first_outcome.hit is False
    assert second_outcome.hit is True
    assert second is first  # el objeto cacheado no se copia ni se muta


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_outcome_counts_stale_while_error_as_a_hit():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))
        await get_current(-31.4, -64.2)

    om_module._CACHE_CURRENT._cache.clear()  # vence el TTL fresco; queda la copia stale
    outcome = CacheOutcome()

    with respx.mock(assert_all_called=False) as mock:
        mock.get(_OM_URL).mock(side_effect=httpx.ConnectError("rate limited"))
        result = await get_current(-31.4, -64.2, cache_outcome=outcome)

    assert result is not None
    assert outcome.hit is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_outcome_is_a_miss_for_concurrent_waiters_of_a_fresh_fetch():
    """Quienes esperan el fetch en vuelo reciben un dato recién traído, no uno cacheado."""
    outcomes = [CacheOutcome() for _ in range(3)]

    with respx.mock(assert_all_called=False) as mock:
        async def slow_handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.05)
            return httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD)

        route = mock.get(_OM_URL).mock(side_effect=slow_handler)
        await asyncio.gather(*[get_current(-31.4, -64.2, cache_outcome=o) for o in outcomes])

    assert route.call_count == 1
    assert [o.hit for o in outcomes] == [False, False, False]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_outcome_is_optional():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_OM_URL).mock(return_value=httpx.Response(200, json=OPENMETEO_SAMPLE_PAYLOAD))
        result = await get_current(-31.4, -64.2)

    assert result is not None
