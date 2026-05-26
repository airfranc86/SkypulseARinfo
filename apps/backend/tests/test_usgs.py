"""Tests unitarios para services/usgs.py."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import respx
from httpx import Response

import app.services.usgs as usgs_module
from app.services.usgs import _parse_event, get_recent_earthquakes


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _feature(
    fid: str = "us7000abc1",
    lon: float = -68.5,
    lat: float = -32.9,
    depth: float = 10.0,
    mag: float = 4.5,
    time_ms: int = 1705320000000,
    place: str = "15 km E of Mendoza, Argentina",
    url: str = "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abc1",
) -> dict:
    return {
        "type": "Feature",
        "id": fid,
        "properties": {
            "mag": mag,
            "place": place,
            "time": time_ms,
            "url": url,
        },
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat, depth],
        },
    }


def _usgs_geojson(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "metadata": {"count": len(features)}, "features": features}


@pytest.fixture(autouse=True)
def clear_usgs_cache():
    usgs_module._event_cache.clear()
    yield
    usgs_module._event_cache.clear()


# ---------------------------------------------------------------------------
# _parse_event
# ---------------------------------------------------------------------------

class TestParseEvent:
    def test_happy_path(self):
        f = _feature(lon=-68.5, lat=-32.9, depth=10.0, mag=4.5, time_ms=1705320000000)
        ev = _parse_event(f, user_lat=-34.6, user_lon=-58.4)
        assert ev is not None
        assert ev.id == "us7000abc1"
        assert ev.magnitude == 4.5
        assert ev.depth_km == 10.0
        assert ev.lat == -32.9
        assert ev.lon == -68.5
        assert isinstance(ev.occurred_at, datetime)
        assert ev.occurred_at.tzinfo == timezone.utc
        assert ev.distance_km > 0

    def test_time_conversion_ms_to_utc(self):
        # 1705320000000 ms = 2024-01-15 14:00:00 UTC
        f = _feature(time_ms=1705320000000)
        ev = _parse_event(f, -34.6, -58.4)
        assert ev is not None
        assert ev.occurred_at.year == 2024
        assert ev.occurred_at.month == 1
        assert ev.occurred_at.day == 15

    def test_depth_abs_value(self):
        # USGS puede reportar depth negativo — lo normalizamos con abs()
        f = _feature(depth=-5.0)
        ev = _parse_event(f, -34.6, -58.4)
        assert ev is not None
        assert ev.depth_km == 5.0

    def test_missing_mag_returns_none(self):
        f = _feature()
        del f["properties"]["mag"]
        ev = _parse_event(f, -34.6, -58.4)
        assert ev is None

    def test_missing_geometry_returns_none(self):
        f = _feature()
        del f["geometry"]
        ev = _parse_event(f, -34.6, -58.4)
        assert ev is None

    def test_invalid_coordinates_returns_none(self):
        f = _feature()
        f["geometry"]["coordinates"] = ["bad", "data"]
        ev = _parse_event(f, -34.6, -58.4)
        assert ev is None

    def test_distance_calculation(self):
        # Córdoba → Buenos Aires ≈ 700 km
        f = _feature(lon=-64.2, lat=-31.4)  # near Córdoba
        ev = _parse_event(f, user_lat=-34.6, user_lon=-58.4)  # Buenos Aires
        assert ev is not None
        assert 600 < ev.distance_km < 800

    def test_rounding(self):
        f = _feature(mag=4.567, depth=12.345)
        ev = _parse_event(f, -34.6, -58.4)
        assert ev is not None
        assert ev.magnitude == 4.6
        assert ev.depth_km == 12.3


# ---------------------------------------------------------------------------
# get_recent_earthquakes
# ---------------------------------------------------------------------------

class TestGetRecentEarthquakes:

    @pytest.mark.asyncio
    async def test_happy_path_returns_events(self):
        features = [
            _feature("ev1", lon=-68.5, lat=-32.9, mag=4.5),  # Mendoza ~1000 km de BA
            _feature("ev2", lon=-64.2, lat=-31.4, mag=3.2),  # Córdoba ~700 km de BA
            _feature("ev3", lon=-58.5, lat=-35.0, mag=5.0),  # cerca de BA ~50 km
        ]
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(200, json=_usgs_geojson(features))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.total == 3
        assert result.radius_km == 2000
        assert len(result.events) == 3

    @pytest.mark.asyncio
    async def test_sorted_by_time_desc(self):
        # Eventos con timestamps distintos — el más reciente primero
        newer_ms = 1705320000000 + 3600_000  # 1 hora más nuevo
        features = [
            _feature("older", lon=-68.5, lat=-32.9, mag=4.5, time_ms=1705320000000),
            _feature("newer", lon=-58.5, lat=-35.0, mag=3.0, time_ms=newer_ms),
        ]
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(200, json=_usgs_geojson(features))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.events[0].id == "newer"
        assert result.events[1].id == "older"

    @pytest.mark.asyncio
    async def test_filter_by_radius(self):
        features = [
            _feature("close", lon=-58.5, lat=-35.0, mag=3.0),  # ~50 km de BA
            _feature("far", lon=-68.5, lat=-32.9, mag=4.5),    # ~1000 km de BA
        ]
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(200, json=_usgs_geojson(features))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=100)

        assert result.total == 1
        assert result.events[0].id == "close"

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self):
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                side_effect=Exception("Connection timeout")
            )
            result = await get_recent_earthquakes(-34.6, -58.4)

        assert result.total == 0
        assert result.events == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self):
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(503)
            )
            result = await get_recent_earthquakes(-34.6, -58.4)

        assert result.total == 0

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self):
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(200, json=_usgs_geojson([]))
            )
            result = await get_recent_earthquakes(-34.6, -58.4)

        assert result.total == 0
        assert result.events == []

    @pytest.mark.asyncio
    async def test_cache_prevents_double_fetch(self):
        features = [_feature("ev1")]
        call_count = 0

        async def _handler(request):
            nonlocal call_count
            call_count += 1
            return Response(200, json=_usgs_geojson(features))

        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(side_effect=_handler)
            await get_recent_earthquakes(-34.6, -58.4)
            await get_recent_earthquakes(-34.6, -58.4)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_invalid_feature_skipped(self):
        bad = _feature("bad")
        del bad["properties"]["mag"]
        good = _feature("good", lon=-58.5, lat=-35.0)
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(200, json=_usgs_geojson([bad, good]))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        assert result.total == 1
        assert result.events[0].id == "good"

    @pytest.mark.asyncio
    async def test_default_radius_500(self):
        features = [_feature("far", lon=-68.5, lat=-32.9)]  # ~1000 km de BA
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(200, json=_usgs_geojson(features))
            )
            result = await get_recent_earthquakes(-34.6, -58.4)  # radius_km default=500

        assert result.radius_km == 500.0
        assert result.total == 0  # el evento está a ~1000 km, fuera de 500

    @pytest.mark.asyncio
    async def test_newer_event_first_regardless_of_magnitude(self):
        # El evento más reciente aparece primero aunque tenga menor magnitud
        newer_ms = 1705320000000 + 7200_000  # 2 horas más nuevo
        features = [
            _feature("big_old", lon=-58.5, lat=-35.0, mag=5.0, time_ms=1705320000000),
            _feature("small_new", lon=-58.5, lat=-35.0, mag=3.0, time_ms=newer_ms),
        ]
        with respx.mock:
            respx.get(url__startswith="https://earthquake.usgs.gov").mock(
                return_value=Response(200, json=_usgs_geojson(features))
            )
            result = await get_recent_earthquakes(-34.6, -58.4, radius_km=2000)

        # El más reciente (menor magnitud) aparece primero
        assert result.events[0].id == "small_new"
        assert result.events[1].id == "big_old"
