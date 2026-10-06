"""Integration tests for GET /api/alertas-smn."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import AsyncClient

import app.services.smn_alertas as service
from app.schemas.smn_alertas import SmnAlerta, SmnAlertasResponse

_FIXTURES = Path(__file__).parent / "fixtures" / "smn_cap"
_FEED_URL = "https://ssl.smn.gob.ar/CAP/AR.php"
_STORM_SEVERE = "CAP_20261006090946_Tormenta_Llanura_alertas_alertas_1.xml"
_ZONDA = "CAP_20261006090946_Zonda_Cordillera_alertas_alertas_1.xml"
_DOCS_BASE = "https://ssl.smn.gob.ar/feeds/CAP/xml_generados/"
_RIO_CUARTO = {"lat": -33.1235, "lon": -64.3493}
_PATCH_TARGET = "app.routers.smn_alertas.get_smn_alertas"


def _alerta(**overrides) -> SmnAlerta:
    fields = dict(
        nivel="naranja",
        tipo="Tormentas",
        fecha_desde=datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc),
        fecha_hasta=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
        descripcion="Tormentas fuertes en la región serrana",
        severidad="Severe",
        instruccion="Evitá actividades al aire libre.",
    )
    return SmnAlerta(**{**fields, **overrides})


def _response(*alertas: SmnAlerta, available: bool = True) -> SmnAlertasResponse:
    return SmnAlertasResponse(
        alertas=list(alertas),
        available=available,
        fetched_at=datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _clean_state():
    service.reset_cache()
    yield
    service.reset_cache()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_alertas_smn_happy_path(async_client: AsyncClient):
    with patch(
        _PATCH_TARGET, new_callable=AsyncMock, return_value=_response(_alerta())
    ):
        response = await async_client.get("/api/alertas-smn")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["alertas"]) == 1
    assert data["alertas"][0]["nivel"] == "naranja"
    assert data["alertas"][0]["severidad"] == "Severe"
    assert data["alertas"][0]["instruccion"] == "Evitá actividades al aire libre."


@pytest.mark.asyncio
@pytest.mark.integration
async def test_alertas_smn_instruccion_may_be_null(async_client: AsyncClient):
    fake = _response(_alerta(instruccion=None, severidad=None))
    with patch(_PATCH_TARGET, new_callable=AsyncMock, return_value=fake):
        response = await async_client.get("/api/alertas-smn")

    alerta = response.json()["alertas"][0]
    assert alerta["instruccion"] is None
    assert alerta["severidad"] is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_alertas_smn_unavailable_still_returns_200(async_client: AsyncClient):
    """A source that cannot be verified is not a 5xx: the frontend decides what to show."""
    with patch(
        _PATCH_TARGET, new_callable=AsyncMock, return_value=_response(available=False)
    ):
        response = await async_client.get("/api/alertas-smn", params=_RIO_CUARTO)

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["alertas"] == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_without_coordinates_asks_for_every_alert(async_client: AsyncClient):
    mocked = AsyncMock(return_value=_response())
    with patch(_PATCH_TARGET, mocked):
        response = await async_client.get("/api/alertas-smn")

    assert response.status_code == 200
    mocked.assert_awaited_once_with(lat=None, lon=None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_with_coordinates_asks_for_that_point(async_client: AsyncClient):
    mocked = AsyncMock(return_value=_response(_alerta()))
    with patch(_PATCH_TARGET, mocked):
        response = await async_client.get("/api/alertas-smn", params=_RIO_CUARTO)

    assert response.status_code == 200
    mocked.assert_awaited_once_with(lat=-33.1235, lon=-64.3493)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "params",
    [
        {"lat": -33.1},
        {"lon": -64.3},
        {"lat": 91, "lon": -64.3},
        {"lat": -91, "lon": -64.3},
        {"lat": -33.1, "lon": 181},
        {"lat": -33.1, "lon": -181},
        {"lat": "abc", "lon": -64.3},
        {"lat": -33.1, "lon": "abc"},
    ],
    ids=[
        "only-lat",
        "only-lon",
        "lat>90",
        "lat<-90",
        "lon>180",
        "lon<-180",
        "lat-nan",
        "lon-nan",
    ],
)
async def test_invalid_coordinates_are_rejected_with_422(
    async_client: AsyncClient, params: dict
):
    mocked = AsyncMock(return_value=_response())
    with patch(_PATCH_TARGET, mocked):
        response = await async_client.get("/api/alertas-smn", params=params)

    assert response.status_code == 422
    mocked.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_boundary_coordinates_are_accepted(async_client: AsyncClient):
    mocked = AsyncMock(return_value=_response())
    with patch(_PATCH_TARGET, mocked):
        response = await async_client.get(
            "/api/alertas-smn", params={"lat": -90, "lon": 180}
        )

    assert response.status_code == 200
    mocked.assert_awaited_once_with(lat=-90.0, lon=180.0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_end_to_end_filters_the_cap_feed_by_location(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Router + service + parser against real CAP fixtures (respx for the SMN)."""
    # The fixtures were captured on 2026-10-06 and expire the next morning: freeze "now".
    frozen = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "_utcnow", lambda: frozen)
    feed = (
        '<rss version="2.0"><channel>'
        f"<item><guid>{_DOCS_BASE}{_STORM_SEVERE}</guid></item>"
        f"<item><guid>{_DOCS_BASE}{_ZONDA}</guid></item>"
        "</channel></rss>"
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_FEED_URL).mock(
            return_value=httpx.Response(200, content=feed.encode())
        )
        for name in (_STORM_SEVERE, _ZONDA):
            mock.get(_DOCS_BASE + name).mock(
                return_value=httpx.Response(
                    200, content=(_FIXTURES / name).read_bytes()
                )
            )
        everywhere = await async_client.get("/api/alertas-smn")
        rio_cuarto = await async_client.get("/api/alertas-smn", params=_RIO_CUARTO)

    assert everywhere.status_code == rio_cuarto.status_code == 200
    assert {a["tipo"] for a in everywhere.json()["alertas"]} == {
        "Tormentas",
        "Viento Zonda",
    }
    located = rio_cuarto.json()
    assert located["available"] is True
    assert [a["tipo"] for a in located["alertas"]] == ["Tormentas"]
    assert located["alertas"][0]["nivel"] == "naranja"
    assert "polygon" not in located["alertas"][0]
