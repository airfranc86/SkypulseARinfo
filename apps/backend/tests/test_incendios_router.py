"""Tests de integración para GET /api/incendios."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.schemas.weather import SourceMeta, WeatherCurrentResponse
from app.services.fire_danger import FireDangerEntry
from app.services.windy import WindyNotConfiguredError


def _make_current_weather(
    temp_c: float = 26.0,
    humidity: float = 40.0,
    wind_speed_kmh: float = 10.0,
    precip_1h_mm: float = 0.0,
) -> WeatherCurrentResponse:
    """Observación real (SMN/Open-Meteo) usada para reemplazar el slot 'actual'."""
    return WeatherCurrentResponse(
        lat=-34.6,
        lon=-58.4,
        temp_c=temp_c,
        feels_like_c=None,
        humidity=humidity,
        wind_speed_kmh=wind_speed_kmh,
        wind_dir_deg=180.0,
        wind_dir_cardinal="S",
        pressure_hpa=1013.0,
        precip_1h_mm=precip_1h_mm,
        cloud_cover=None,
        description="Despejado",
        meta=SourceMeta(
            source="smn",
            reason="smn_nearby_fresh",
            station=None,
            fetched_at=datetime.now(timezone.utc),
            cache_hit=False,
        ),
    )


@pytest.fixture(autouse=True)
def mock_aggregate_current_unavailable():
    """
    Por defecto, aggregate_current no está disponible en los tests — mantiene
    el comportamiento de "solo Windy" sin tener que tocar cada test existente
    uno por uno. Los tests que prueban el path con observación real lo
    parchean explícitamente adentro (el patch interno gana mientras dura).
    """
    with patch(
        "app.routers.incendios.aggregate_current",
        new_callable=AsyncMock,
        side_effect=RuntimeError("aggregate_current no disponible en tests"),
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    score: float = 35.0,
    label: str = "Bajo",
    is_estimated: bool = True,
    date: str = "2026-05-26",
    hour_label: str = "12:00",
    timestamp_s: int | None = None,
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
        timestamp_s=timestamp_s if timestamp_s is not None else int(time.time()),
    )


def _make_entries(n: int = 3, is_estimated: bool = True) -> list[FireDangerEntry]:
    """
    Slots horarios sintéticos empezando en "ahora" — entries[0] es el más
    cercano al momento actual por construcción, igual que un array de Windy
    bien alineado. Para el caso desalineado (bug real), ver
    TestClosestToNowSelection más abajo.
    """
    hours = ["09:00", "12:00", "15:00", "18:00", "21:00", "00:00"]
    scores = [25.0, 45.0, 60.0, 50.0, 30.0, 20.0]
    labels = ["Bajo", "Moderado", "Moderado", "Moderado", "Bajo", "Muy bajo"]
    now = int(time.time())
    return [
        _make_entry(
            score=scores[i % len(scores)],
            label=labels[i % len(labels)],
            is_estimated=is_estimated,
            hour_label=hours[i % len(hours)],
            timestamp_s=now + i * 3600,
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
    async def test_current_reflects_closest_slot_not_raw_index_zero(self, async_client: AsyncClient):
        """
        Cableado end-to-end del bug reportado en vivo: el array de Windy
        empezaba varias horas antes de "ahora" (10°C, madrugada) mientras la
        temperatura real en ese momento era 22°C. La respuesta debe reflejar
        el slot correcto, y el array `slots` debe arrancar ahí también — el
        frontend toma slots[0] directamente como "condiciones actuales".
        """
        now = int(time.time())
        entries = [
            _make_entry(score=15.0, label="Muy bajo", hour_label="04:00", timestamp_s=now - 6 * 3600),
            _make_entry(score=20.0, label="Muy bajo", hour_label="07:00", timestamp_s=now - 3 * 3600),
            _make_entry(score=45.0, label="Moderado", hour_label="10:00", timestamp_s=now),
            _make_entry(score=55.0, label="Moderado", hour_label="13:00", timestamp_s=now + 3 * 3600),
        ]
        # temp_c=28.0 fijo en el helper — distinguimos por score/label en su lugar.
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        data = response.json()
        assert data["current_score"] == 45.0
        assert data["current_label"] == "Moderado"
        # El array recortado no debe incluir las 2 horas ya pasadas.
        assert len(data["slots"]) == 2
        assert data["slots"][0]["fire_risk_score"] == 45.0
        assert data["slots"][1]["fire_risk_score"] == 55.0

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


# ---------------------------------------------------------------------------
# Reemplazo de temp/humedad/viento "actuales" por observación real
# (bug reportado en vivo: Windy GFS mostraba 10-13°C con ~26°C reales)
# ---------------------------------------------------------------------------

class TestIncendiosCurrentWeatherOverride:

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_current_uses_real_observation_when_estimated(self, async_client: AsyncClient):
        """
        Score estimado (sin FWI real) + aggregate_current disponible → el slot
        actual usa temp/humedad/viento reales, y el score se recalcula con
        esos valores (no queda un score de Windy junto a una temp real).
        """
        entries = _make_entries(n=3, is_estimated=True)  # temp_c=28.0 en Windy
        real_weather = _make_current_weather(temp_c=26.0, humidity=40.0, wind_speed_kmh=10.0)
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ), patch(
            "app.routers.incendios.aggregate_current",
            new_callable=AsyncMock,
            return_value=real_weather,
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        assert response.status_code == 200
        data = response.json()
        current_slot = data["slots"][0]
        assert current_slot["temp_c"] == pytest.approx(26.0)
        assert current_slot["humidity"] == pytest.approx(40.0)
        assert current_slot["wind_kmh"] == pytest.approx(10.0)
        # El score ya no es el 25.0 sintético de Windy — fue recalculado.
        assert data["current_score"] != entries[0].fire_risk_score
        assert data["current_score"] == current_slot["fire_risk_score"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_current_display_overridden_but_score_kept_when_fwi_real(
        self, async_client: AsyncClient
    ):
        """
        Con FWI real (is_estimated=False), la temp mostrada se actualiza pero
        el score/label quedan intactos — vienen del modelo fireDanger real,
        no de una fórmula que podamos recalcular con temp/humedad/viento.
        """
        entries = _make_entries(n=3, is_estimated=False)
        real_weather = _make_current_weather(temp_c=26.0, humidity=40.0, wind_speed_kmh=10.0)
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ), patch(
            "app.routers.incendios.aggregate_current",
            new_callable=AsyncMock,
            return_value=real_weather,
        ):
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        data = response.json()
        current_slot = data["slots"][0]
        assert current_slot["temp_c"] == pytest.approx(26.0)
        assert data["current_score"] == entries[0].fire_risk_score
        assert data["current_label"] == entries[0].fire_risk_label

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_falls_back_to_windy_when_aggregate_current_fails(
        self, async_client: AsyncClient
    ):
        """aggregate_current falla → sigue respondiendo 200 con los datos de Windy tal cual."""
        entries = _make_entries(n=3, is_estimated=True)
        with patch(
            "app.routers.incendios.get_fire_danger",
            new_callable=AsyncMock,
            return_value=entries,
        ):
            # mock_aggregate_current_unavailable (autouse) ya simula el fallo.
            response = await async_client.get("/api/incendios?lat=-34.6&lon=-58.4")

        assert response.status_code == 200
        data = response.json()
        assert data["slots"][0]["temp_c"] == pytest.approx(entries[0].temp_c)
        assert data["current_score"] == entries[0].fire_risk_score
