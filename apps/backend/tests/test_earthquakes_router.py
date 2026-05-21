"""Tests de integración para GET /api/earthquakes/recent."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.earthquakes import EarthquakeEvent, EarthquakesResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(
    fid: str = "us7000abc1",
    distance_km: float = 120.0,
    magnitude: float = 4.5,
) -> EarthquakeEvent:
    return EarthquakeEvent(
        id=fid,
        place="15 km E of Mendoza, Argentina",
        magnitude=magnitude,
        depth_km=10.0,
        occurred_at=datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc),
        lat=-32.9,
        lon=-68.5,
        distance_km=distance_km,
        usgs_url="https://earthquake.usgs.gov/earthquakes/eventpage/us7000abc1",
    )


def _make_response(events: list[EarthquakeEvent] | None = None, radius_km: float = 500.0) -> EarthquakesResponse:
    evs = events or []
    return EarthquakesResponse(total=len(evs), radius_km=radius_km, events=evs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEarthquakesRouter:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_returns_200(self, async_client: AsyncClient):
        events = [_make_event("ev1", 120.0), _make_event("ev2", 300.0)]
        mock_resp = _make_response(events)
        with patch(
            "app.routers.earthquakes.get_recent_earthquakes",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            response = await async_client.get(
                "/api/earthquakes/recent?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["radius_km"] == 500.0
        assert len(data["events"]) == 2
        assert data["events"][0]["id"] == "ev1"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_event_fields_present(self, async_client: AsyncClient):
        mock_resp = _make_response([_make_event()])
        with patch(
            "app.routers.earthquakes.get_recent_earthquakes",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            response = await async_client.get(
                "/api/earthquakes/recent?lat=-34.6&lon=-58.4"
            )

        ev = response.json()["events"][0]
        assert "id" in ev
        assert "place" in ev
        assert "magnitude" in ev
        assert "depth_km" in ev
        assert "occurred_at" in ev
        assert "lat" in ev
        assert "lon" in ev
        assert "distance_km" in ev
        assert "usgs_url" in ev

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_events_when_none_in_radius(self, async_client: AsyncClient):
        mock_resp = _make_response([])
        with patch(
            "app.routers.earthquakes.get_recent_earthquakes",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            response = await async_client.get(
                "/api/earthquakes/recent?lat=-34.6&lon=-58.4"
            )

        assert response.status_code == 200
        assert response.json()["total"] == 0
        assert response.json()["events"] == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_custom_radius_km_forwarded(self, async_client: AsyncClient):
        mock_resp = _make_response([], radius_km=200.0)
        with patch(
            "app.routers.earthquakes.get_recent_earthquakes",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_fn:
            response = await async_client.get(
                "/api/earthquakes/recent?lat=-34.6&lon=-58.4&radius_km=200"
            )

        assert response.status_code == 200
        mock_fn.assert_called_once_with(-34.6, -58.4, 200.0)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_lat_returns_422(self, async_client: AsyncClient):
        response = await async_client.get(
            "/api/earthquakes/recent?lat=-60&lon=-58.4"
        )
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_outside_argentina_lon_returns_422(self, async_client: AsyncClient):
        response = await async_client.get(
            "/api/earthquakes/recent?lat=-34.6&lon=-50"
        )
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_missing_lat_lon_returns_422(self, async_client: AsyncClient):
        response = await async_client.get("/api/earthquakes/recent")
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_radius_km_below_min_returns_422(self, async_client: AsyncClient):
        response = await async_client.get(
            "/api/earthquakes/recent?lat=-34.6&lon=-58.4&radius_km=10"
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_radius_km_above_max_returns_422(self, async_client: AsyncClient):
        response = await async_client.get(
            "/api/earthquakes/recent?lat=-34.6&lon=-58.4&radius_km=5000"
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rate_limit_returns_429(self, async_client: AsyncClient):
        mock_resp = _make_response([])
        with patch(
            "app.routers.earthquakes.get_recent_earthquakes",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            statuses = [
                (await async_client.get("/api/earthquakes/recent?lat=-34.6&lon=-58.4")).status_code
                for _ in range(35)
            ]
        assert 429 in statuses
