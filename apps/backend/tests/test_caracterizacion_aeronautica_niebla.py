"""Characterization of GET /api/niebla: the response content, frozen as literal JSON.

AWC (METAR and TAF) is mocked with respx; the Open-Meteo functions are patched the same way the
sibling niebla tests do. The clock of `app.services.metar` is frozen, so the METAR ages, the TAF
slots and their hour labels are deterministic. These tests pin CONTENT only: no cache TTLs,
lookback windows, timeouts or number of AWC requests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.services.metar import AWC_METAR_BASE, AWC_TAF_BASE
from app.services.openmeteo import FogInferenceSlot, VisibilityData
from tests.helpers_caracterizacion_aeronautica import (
    FROZEN_NOW,
    awc_metar,
    freeze_clock,
    load_taf,
    minutes_before,
    reset_aeronautical_state,
)

pytestmark = pytest.mark.integration

ROSARIO = (-32.95, -60.65)   # SAAR, 13.1 km
QUILMES = (-34.72, -58.25)   # SABE, 23.5 km: beyond the 20 km limit
SALTA = (-24.8, -65.4)       # SASA, 10.7 km

# Open-Meteo "now" is 3 km, distinguishable from every METAR value used below.
OPEN_METEO = VisibilityData(
    current_m=3000.0,
    weather_code=1,
    fog_level=2,
    fog_label="Neblina o bruma",
    fog_color="#f0a020",
    hourly_m=[10000.0, 4000.0, 800.0],
    hourly_labels=["13:00", "14:00", "15:00"],
)
OPEN_METEO_HOURLY = [
    {"hour_label": "13:00", "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a"},
    {"hour_label": "14:00", "visibility_m": 4000.0, "fog_level": 2, "fog_label": "Neblina o bruma", "fog_color": "#f0a020"},
    {"hour_label": "15:00", "visibility_m": 800.0, "fog_level": 3, "fog_label": "Niebla", "fog_color": "#e03535"},
]
INFERENCE = [FogInferenceSlot("13:00", None), FogInferenceSlot("14:00", 800.0), FogInferenceSlot("15:00", 6000.0)]
INFERENCE_HOURLY = [
    {"hour_label": "13:00", "visibility_m": None, "fog_level": 0, "fog_label": "Sin datos", "fog_color": "#90aabb"},
    {"hour_label": "14:00", "visibility_m": 800.0, "fog_level": 3, "fog_label": "Niebla", "fog_color": "#e03535"},
    {"hour_label": "15:00", "visibility_m": 6000.0, "fog_level": 1, "fog_label": "Buena", "fog_color": "#5aaad8"},
]

# Body when the METAR of Rosario is used and Open-Meteo supplies the hourly series.
METAR_ROSARIO_CAVOK = {
    "visibility_m": 10000.0,
    "fog_level": 0,
    "fog_label": "Despejada",
    "fog_color": "#3ecf7a",
    "weather_code": 1,
    "hourly": OPEN_METEO_HOURLY,
    "source": "metar",
    "metar_station": "SAAR",
    "metar_station_name": "Rosario",
    "metar_distance_km": 13.1,
    "hourly_source": "openmeteo",
}
# Body when the METAR of Rosario is NOT used: Open-Meteo answers "now", the station is still reported.
OPEN_METEO_ROSARIO = {
    "visibility_m": 3000.0,
    "fog_level": 2,
    "fog_label": "Neblina o bruma",
    "fog_color": "#f0a020",
    "weather_code": 1,
    "hourly": OPEN_METEO_HOURLY,
    "source": "openmeteo",
    "metar_station": "SAAR",
    "metar_station_name": "Rosario",
    "metar_distance_km": 13.1,
    "hourly_source": "openmeteo",
}


@pytest.fixture(autouse=True)
def _state(monkeypatch):
    reset_aeronautical_state()
    freeze_clock(monkeypatch, FROZEN_NOW, "app.services.metar")
    yield
    reset_aeronautical_state()


@pytest.fixture
def open_meteo(monkeypatch):
    """Open-Meteo sources: visibility/weather code present, fog inference off. Tests override as needed."""
    monkeypatch.setattr("app.routers.niebla.get_visibility_forecast", AsyncMock(return_value=OPEN_METEO))
    monkeypatch.setattr("app.routers.niebla.get_fog_inference_forecast", AsyncMock(return_value=None))


def metar_response(visib: object, icao: str = "SAAR", minutes_old: float = 10, **fields: object) -> httpx.Response:
    return httpx.Response(200, json=awc_metar(minutes_before(FROZEN_NOW, minutes_old), icao, visib=visib, **fields))


async def get_niebla(
    client: AsyncClient,
    location: tuple[float, float],
    metar: httpx.Response,
    taf: httpx.Response | None = None,
) -> httpx.Response:
    """GET /api/niebla with AWC mocked: `metar` for the METAR, `taf` for the TAF (default: no TAF)."""
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(return_value=metar)
        router.get(AWC_TAF_BASE).mock(return_value=taf or httpx.Response(200, json=[]))
        return await client.get("/api/niebla", params={"lat": location[0], "lon": location[1]})


# ---------------------------------------------------------------------------
# "Now" from the METAR
# ---------------------------------------------------------------------------

async def test_cavok_metar_is_10_km_and_reports_the_station(async_client: AsyncClient, open_meteo) -> None:
    response = await get_niebla(async_client, ROSARIO, metar_response("6+"))

    assert response.status_code == 200
    assert response.json() == METAR_ROSARIO_CAVOK


@pytest.mark.parametrize(
    ("visib", "visibility_m", "level", "label", "color"),
    [
        ("6+", 10000.0, 0, "Despejada", "#3ecf7a"),
        ("P6SM", 10000.0, 0, "Despejada", "#3ecf7a"),
        (10, 10000.0, 0, "Despejada", "#3ecf7a"),
        (5, 8046.72, 1, "Buena", "#5aaad8"),
        (3, 4828.032, 2, "Neblina o bruma", "#f0a020"),
        ("1/2", 804.672, 3, "Niebla", "#e03535"),
        (0.25, 402.336, 3, "Niebla", "#e03535"),
    ],
)
async def test_metar_visibility_scale(
    async_client: AsyncClient, open_meteo, visib, visibility_m, level, label, color
) -> None:
    response = await get_niebla(async_client, ROSARIO, metar_response(visib, wxString="FG"))

    body = response.json()
    assert response.status_code == 200
    assert body["source"] == "metar"
    assert body["metar_station"] == "SAAR"
    assert (body["visibility_m"], body["fog_level"], body["fog_label"], body["fog_color"]) == (
        visibility_m, level, label, color,
    )


@pytest.mark.parametrize("minutes_old", [0, 89, 90])
async def test_metar_up_to_90_minutes_old_is_used(async_client: AsyncClient, open_meteo, minutes_old) -> None:
    response = await get_niebla(async_client, ROSARIO, metar_response("6+", minutes_old=minutes_old))

    assert response.status_code == 200
    assert response.json() == METAR_ROSARIO_CAVOK


# ---------------------------------------------------------------------------
# Fallback to Open-Meteo "now": the station and distance are still reported
# ---------------------------------------------------------------------------

async def test_metar_older_than_90_minutes_falls_back_to_open_meteo(async_client: AsyncClient, open_meteo) -> None:
    response = await get_niebla(async_client, ROSARIO, metar_response("6+", minutes_old=91))

    assert response.status_code == 200
    assert response.json() == OPEN_METEO_ROSARIO


async def test_airport_beyond_20_km_falls_back_to_open_meteo(async_client: AsyncClient, open_meteo) -> None:
    response = await get_niebla(async_client, QUILMES, metar_response("6+", icao="SABE"))

    assert response.status_code == 200
    assert response.json() == {
        "visibility_m": 3000.0,
        "fog_level": 2,
        "fog_label": "Neblina o bruma",
        "fog_color": "#f0a020",
        "weather_code": 1,
        "hourly": OPEN_METEO_HOURLY,
        "source": "openmeteo",
        "metar_station": "SABE",
        "metar_station_name": "Aeroparque",
        "metar_distance_km": 23.5,
        "hourly_source": "openmeteo",
    }


@pytest.mark.parametrize(
    "metar",
    [
        httpx.Response(200, json=[]),
        httpx.Response(500, text="boom"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=[{"icaoId": "SAAR", "visib": "6+"}]),
        httpx.Response(200, json=awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", visib="abc")),
    ],
    ids=["empty", "http-500", "invalid-json", "no-obs-time", "unparseable-visibility"],
)
async def test_missing_or_unusable_metar_falls_back_to_open_meteo(
    async_client: AsyncClient, open_meteo, metar: httpx.Response
) -> None:
    response = await get_niebla(async_client, ROSARIO, metar)

    assert response.status_code == 200
    assert response.json() == OPEN_METEO_ROSARIO


async def test_metar_without_visibility_field_falls_back_to_open_meteo(async_client: AsyncClient, open_meteo) -> None:
    no_visib = httpx.Response(200, json=awc_metar(minutes_before(FROZEN_NOW, 10), "SAAR", temp=20))

    response = await get_niebla(async_client, ROSARIO, no_visib)

    assert response.status_code == 200
    assert response.json() == OPEN_METEO_ROSARIO


async def test_awc_connection_error_falls_back_to_open_meteo(async_client: AsyncClient, open_meteo) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_METAR_BASE).mock(side_effect=httpx.ConnectError("down"))
        router.get(AWC_TAF_BASE).mock(side_effect=httpx.ConnectError("down"))
        response = await async_client.get("/api/niebla", params={"lat": ROSARIO[0], "lon": ROSARIO[1]})

    assert response.status_code == 200
    assert response.json() == OPEN_METEO_ROSARIO


async def test_no_metar_and_no_open_meteo_is_503_visibility_unavailable(
    async_client: AsyncClient, open_meteo, monkeypatch
) -> None:
    monkeypatch.setattr("app.routers.niebla.get_visibility_forecast", AsyncMock(return_value=None))

    response = await get_niebla(async_client, ROSARIO, httpx.Response(200, json=[]))

    assert response.status_code == 503
    assert response.json() == {"detail": "visibility_unavailable"}


# ---------------------------------------------------------------------------
# Hourly source: taf > openmeteo_inference > openmeteo > none
# ---------------------------------------------------------------------------

async def test_hourly_from_the_taf_of_the_nearest_airport(async_client: AsyncClient, open_meteo, monkeypatch) -> None:
    # 03:30 in Argentina: the 12 slots start at 04:00 local (07:00Z) on the real TAF of SASA.
    freeze_clock(monkeypatch, datetime(2026, 10, 7, 6, 30, tzinfo=timezone.utc), "app.services.metar")
    metar = httpx.Response(
        200,
        json=awc_metar(datetime(2026, 10, 7, 6, 20, tzinfo=timezone.utc), "SASA", visib=4.35, wxString="BR"),
    )

    response = await get_niebla(async_client, SALTA, metar, taf=httpx.Response(200, json=load_taf("SASA")))

    assert response.status_code == 200
    assert response.json() == {
        "visibility_m": 7000.6464,
        "fog_level": 1,
        "fog_label": "Buena",
        "fog_color": "#5aaad8",
        "weather_code": 1,
        "hourly": [
            {"hour_label": "04:00", "visibility_m": 7000.6464, "fog_level": 1, "fog_label": "Buena", "fog_color": "#5aaad8"},
            {"hour_label": "05:00", "visibility_m": 7000.6464, "fog_level": 1, "fog_label": "Buena", "fog_color": "#5aaad8"},
            {"hour_label": "06:00", "visibility_m": 1995.58656, "fog_level": 2, "fog_label": "Neblina o bruma", "fog_color": "#f0a020"},
            {"hour_label": "07:00", "visibility_m": 1995.58656, "fog_level": 2, "fog_label": "Neblina o bruma", "fog_color": "#f0a020"},
            {"hour_label": "08:00", "visibility_m": 1995.58656, "fog_level": 2, "fog_label": "Neblina o bruma", "fog_color": "#f0a020"},
            {"hour_label": "09:00", "visibility_m": 7000.6464, "fog_level": 1, "fog_label": "Buena", "fog_color": "#5aaad8"},
            {"hour_label": "10:00", "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a"},
            {"hour_label": "11:00", "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a"},
            {"hour_label": "12:00", "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a"},
            {"hour_label": "13:00", "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a"},
            {"hour_label": "14:00", "visibility_m": 10000.0, "fog_level": 0, "fog_label": "Despejada", "fog_color": "#3ecf7a"},
            {"hour_label": "15:00", "visibility_m": None, "fog_level": 0, "fog_label": "Sin datos", "fog_color": "#90aabb"},
        ],
        "source": "metar",
        "metar_station": "SASA",
        "metar_station_name": "Salta",
        "metar_distance_km": 10.7,
        "hourly_source": "taf",
    }


async def test_taf_takes_priority_over_the_fog_inference(async_client: AsyncClient, open_meteo, monkeypatch) -> None:
    freeze_clock(monkeypatch, datetime(2026, 10, 7, 6, 30, tzinfo=timezone.utc), "app.services.metar")
    monkeypatch.setattr("app.routers.niebla.get_fog_inference_forecast", AsyncMock(return_value=INFERENCE))
    metar = httpx.Response(
        200,
        json=awc_metar(datetime(2026, 10, 7, 6, 20, tzinfo=timezone.utc), "SASA", visib="6+"),
    )

    response = await get_niebla(async_client, SALTA, metar, taf=httpx.Response(200, json=load_taf("SASA")))

    body = response.json()
    assert response.status_code == 200
    assert body["hourly_source"] == "taf"
    assert body["hourly"][0]["hour_label"] == "04:00"
    assert len(body["hourly"]) == 12


async def test_hourly_from_the_fog_inference_when_there_is_no_taf(
    async_client: AsyncClient, open_meteo, monkeypatch
) -> None:
    monkeypatch.setattr("app.routers.niebla.get_fog_inference_forecast", AsyncMock(return_value=INFERENCE))

    response = await get_niebla(async_client, ROSARIO, metar_response("6+"))

    assert response.status_code == 200
    assert response.json() == {**METAR_ROSARIO_CAVOK, "hourly": INFERENCE_HOURLY, "hourly_source": "openmeteo_inference"}


async def test_failed_taf_request_falls_back_to_the_fog_inference(
    async_client: AsyncClient, open_meteo, monkeypatch
) -> None:
    monkeypatch.setattr("app.routers.niebla.get_fog_inference_forecast", AsyncMock(return_value=INFERENCE))

    response = await get_niebla(
        async_client, ROSARIO, metar_response("6+"), taf=httpx.Response(500, text="boom")
    )

    assert response.status_code == 200
    assert response.json() == {**METAR_ROSARIO_CAVOK, "hourly": INFERENCE_HOURLY, "hourly_source": "openmeteo_inference"}


async def test_without_open_meteo_the_metar_still_answers_with_no_hourly(
    async_client: AsyncClient, open_meteo, monkeypatch
) -> None:
    monkeypatch.setattr("app.routers.niebla.get_visibility_forecast", AsyncMock(return_value=None))

    response = await get_niebla(async_client, ROSARIO, metar_response("6+"))

    assert response.status_code == 200
    assert response.json() == {
        "visibility_m": 10000.0,
        "fog_level": 0,
        "fog_label": "Despejada",
        "fog_color": "#3ecf7a",
        "weather_code": None,
        "hourly": [],
        "source": "metar",
        "metar_station": "SAAR",
        "metar_station_name": "Rosario",
        "metar_distance_km": 13.1,
        "hourly_source": "none",
    }
