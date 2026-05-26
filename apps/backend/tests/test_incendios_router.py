"""Tests de integración para GET /api/incendios."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.services.fire_danger import FireDangerEntry
from app.services.windy import WindyNotConfiguredError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    score: float = 35.0,
    label: str = "Bajo",
    is_estimated: bool = True,
    date: str = "2026-05-26",
    hour_label: str = "12:00",
) -> FireDangerEntry:
    return FireDangerEntry(
        date=date,
        hour_label=hour_label,
        fwi=None if is_estimated else round(score / 2, 2),
        fire_risk_score=score,
        fire_risk_label=label,
        temp_c=28.0,
        humidity=45.0,
        wind_kmh=20.0,
        precip_mm=0.0,
        is_estimated=is_estimated,
    )


def _make_entries(n: int = 3, is_estimated: bool = True) -> list[FireDangerEntry]:
    hours = ["09:00", "12:00", "15:00", "18:00", "21:00", "00:00"]
    scores = [25.0, 45.0, 60.0, 50.0, 30.0, 20.0]
    labels = ["Bajo", "Moderado", "Moderado", "Moderado", "Bajo", "Muy bajo"]
    return [
        _make_entry(
            score=scores[i % len(scores)],
            label=labels[i % len(labels)],
            is_estimated=is_estimated,
            hour_label=hours[i % len(hours)],
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIncendiosRouter:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_windy_not_configured_returns_503(self, async_client: AsyncClient):
        """Cuando Windy no está configurado → 503 con detail windy_not_configured."""
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            side_effect=WindyNotConfiguredError("windy_api_key no configurada"),
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        assert response.status_code == 503
        assert response.json()["detail"] == "windy_not_configured"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_estimated_returns_200(self, async_client: AsyncClient):
        """Happy path con datos estimados (GFS fallback) → 200 con campos completos."""
        entries = _make_entries(n=6, is_estimated=True)
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        assert response.status_code == 200
        data = response.json()

        # Campos de respuesta presentes
        assert "slots" in data
        assert "current_score" in data
        assert "current_label" in data
        assert "current_color" in data
        assert "peak_score" in data
        assert "peak_label" in data
        assert "peak_hour_label" in data
        assert "source" in data
        assert "is_estimated" in data

        # Source correcto para datos estimados
        assert data["source"] == "windy_gfs_estimated"
        assert data["is_estimated"] is True

        # current = primer slot
        assert data["current_score"] == entries[0].fire_risk_score
        assert data["current_label"] == entries[0].fire_risk_label

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_happy_path_fwi_model_returns_windy_source(self, async_client: AsyncClient):
        """Happy path con modelo fireDanger (FWI real) → source = windy_firedanger."""
        entries = _make_entries(n=4, is_estimated=False)
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "windy_firedanger"
        assert data["is_estimated"] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_peak_is_max_score_slot(self, async_client: AsyncClient):
        """El peak debe ser el slot con mayor fire_risk_score."""
        entries = _make_entries(n=6, is_estimated=True)
        expected_peak = max(entries, key=lambda e: e.fire_risk_score)
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        data = response.json()
        assert data["peak_score"] == expected_peak.fire_risk_score
        assert data["peak_label"] == expected_peak.fire_risk_label

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_lat_outside_argentina_returns_422(self, async_client: AsyncClient):
        """lat fuera de Argentina (< -55 o > -21) → 422 outside_argentina."""
        response = await async_client.get("/api/incendios?lat=-60.0&lon=-58.4")
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_lon_outside_argentina_returns_422(self, async_client: AsyncClient):
        """lon fuera de Argentina → 422."""
        response = await async_client.get("/api/incendios?lat=-34.6&lon=-50.0")
        assert response.status_code == 422
        assert response.json()["error"] == "outside_argentina"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_missing_lat_lon_returns_422(self, async_client: AsyncClient):
        """Sin lat/lon → 422."""
        response = await async_client.get("/api/incendios")
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_slot_fields_present(self, async_client: AsyncClient):
        """Cada slot debe tener todos los campos requeridos."""
        entries = _make_entries(n=2, is_estimated=True)
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        slot = response.json()["slots"][0]
        assert "date" in slot
        assert "hour_label" in slot
        assert "fwi" in slot
        assert "fire_risk_score" in slot
        assert "fire_risk_label" in slot
        assert "temp_c" in slot
        assert "humidity" in slot
        assert "wind_kmh" in slot
        assert "precip_mm" in slot
        assert "is_estimated" in slot

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_generic_exception_returns_503(self, async_client: AsyncClient):
        """Ante excepción inesperada → 503 fire_danger_unavailable."""
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            side_effect=RuntimeError("network failure"),
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        assert response.status_code == 503
        assert response.json()["detail"] == "fire_danger_unavailable"
