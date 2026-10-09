"""GET /api/taf: TAF decodificado de AWC, sin clave de CheckWX (FRA-365, T3)."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from httpx import AsyncClient

import app.services.reportes_aeronauticos.taf as taf_module
from app.services.reportes_aeronauticos.awc import AWC_TAF_BASE

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).parent / "fixtures" / "awc_taf" / "SACO.json"


@pytest.fixture(autouse=True)
def _clean_caches():
    taf_module._taf_cache.clear()
    yield
    taf_module._taf_cache.clear()


@pytest.fixture
def saco() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


async def test_returns_the_decoded_taf_of_saco(async_client: AsyncClient, saco) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        response = await async_client.get("/api/taf", params={"icao": "SACO"})
    assert response.status_code == 200
    body = response.json()
    assert body["icao"] == "SACO"
    assert body["source"] == "aviationweather.gov (NOAA)"
    assert body["raw"].startswith("TAF SACO 061700Z")
    assert [p["change"] for p in body["periods"]] == ["initial", "becoming", "becoming", "tempo", "becoming"]
    assert body["periods"][0]["valid_from"] == "2026-10-06T18:00:00Z"
    assert body["periods"][3]["probability"] == 40
    assert dict(route.calls.last.request.url.params) == {"ids": "SACO", "format": "json"}


async def test_works_without_a_checkwx_key(async_client: AsyncClient, saco, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.checkwx_api_key", "")
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        response = await async_client.get("/api/taf", params={"icao": "SACO"})
    assert response.status_code == 200


async def test_the_icao_is_case_insensitive(async_client: AsyncClient, saco) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        response = await async_client.get("/api/taf", params={"icao": "saco"})
    assert response.status_code == 200
    assert route.calls.last.request.url.params["ids"] == "SACO"


@pytest.mark.parametrize("icao", ["SAC", "SACOX", "SA-O", "SA O", "S@CO"])
async def test_invalid_icao_is_422_and_nothing_is_requested(async_client: AsyncClient, icao) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        response = await async_client.get("/api/taf", params={"icao": icao})
    assert response.status_code == 422
    assert route.call_count == 0


async def test_missing_icao_is_422(async_client: AsyncClient) -> None:
    assert (await async_client.get("/api/taf")).status_code == 422


async def test_an_airport_without_taf_is_404(async_client: AsyncClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=[]))
        response = await async_client.get("/api/taf", params={"icao": "SAXX"})
    assert response.status_code == 404
    assert response.json()["detail"] == "taf_not_found"


@pytest.mark.parametrize("failure", [httpx.Response(400, text="x"), httpx.Response(503, text="x"), httpx.ConnectError("x")])
async def test_an_awc_failure_is_503_not_404(async_client: AsyncClient, failure) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(side_effect=[failure])
        response = await async_client.get("/api/taf", params={"icao": "SACO"})
    assert response.status_code == 503
    assert response.json()["detail"] == "taf_unavailable"


async def test_a_second_request_does_not_call_awc_again(async_client: AsyncClient, saco) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=saco))
        await async_client.get("/api/taf", params={"icao": "SACO"})
        await async_client.get("/api/taf", params={"icao": "SACO"})
    assert route.call_count == 1
