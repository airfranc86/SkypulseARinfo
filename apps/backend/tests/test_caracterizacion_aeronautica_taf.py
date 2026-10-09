"""Characterization of GET /api/taf: the response content of the AWC TAF route, frozen as literal JSON.

The expected bodies below were taken from the real output of the route over the real AWC fixtures
(tests/fixtures/awc_taf). They pin CONTENT only, never cache TTLs, timeouts or the number of AWC
requests, so a refactor of the AWC client can prove the responses stay identical.
AWC is mocked with respx; the network is never touched.
"""
from __future__ import annotations

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.services.reportes_aeronauticos.awc import AWC_TAF_BASE
from tests.helpers_caracterizacion_aeronautica import load_taf, reset_aeronautical_state

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clean_state():
    reset_aeronautical_state()
    yield
    reset_aeronautical_state()


EXPECTED_SAAR = {
    "icao": "SAAR",
    "name": "Rosario Intl",
    "issued_at": "2026-10-06T17:00:00Z",
    "valid_from": "2026-10-06T18:00:00Z",
    "valid_to": "2026-10-07T18:00:00Z",
    "raw": "TAF SAAR 061700Z 0618/0718 08010KT CAVOK TX25/0618Z TN16/0710Z TEMPO 0618/0623 08010G20KT TEMPO 0709/0713 4000 TSRA SCT020 FEW040CB BKN060 BECMG 0713/0715 18015KT 3000 TSRA BKN008 FEW040CB OVC045",
    "periods": [
        {"change": "initial", "probability": None, "valid_from": "2026-10-06T18:00:00Z", "valid_to": "2026-10-07T13:00:00Z", "becoming_by": None, "wind": {"direction_deg": 80, "variable": False, "speed_kt": 10, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "NSC", "base_ft": None, "kind": None}], "weather": [], "flight_category": "VFR", "inherited": []},
        {"change": "tempo", "probability": None, "valid_from": "2026-10-06T18:00:00Z", "valid_to": "2026-10-06T23:00:00Z", "becoming_by": None, "wind": {"direction_deg": 80, "variable": False, "speed_kt": 10, "gust_kt": 20}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "NSC", "base_ft": None, "kind": None}], "weather": [], "flight_category": "VFR", "inherited": ["visibility", "clouds"]},
        {"change": "tempo", "probability": None, "valid_from": "2026-10-07T09:00:00Z", "valid_to": "2026-10-07T13:00:00Z", "becoming_by": None, "wind": {"direction_deg": 80, "variable": False, "speed_kt": 10, "gust_kt": None}, "visibility_m": 4000, "visibility_over": False, "clouds": [{"cover": "SCT", "base_ft": 2000, "kind": None}, {"cover": "FEW", "base_ft": 4000, "kind": "CB"}, {"cover": "BKN", "base_ft": 6000, "kind": None}], "weather": ["TSRA"], "flight_category": "IFR", "inherited": ["wind"]},
        {"change": "becoming", "probability": None, "valid_from": "2026-10-07T13:00:00Z", "valid_to": "2026-10-07T18:00:00Z", "becoming_by": "2026-10-07T15:00:00Z", "wind": {"direction_deg": 180, "variable": False, "speed_kt": 15, "gust_kt": None}, "visibility_m": 3000, "visibility_over": False, "clouds": [{"cover": "BKN", "base_ft": 800, "kind": None}, {"cover": "FEW", "base_ft": 4000, "kind": "CB"}, {"cover": "OVC", "base_ft": 4500, "kind": None}], "weather": ["TSRA"], "flight_category": "IFR", "inherited": []},
    ],
    "temperatures": [
        {"kind": "max", "celsius": 25.0, "valid_at": "2026-10-06T18:00:00Z"},
        {"kind": "min", "celsius": 16.0, "valid_at": "2026-10-07T10:00:00Z"},
    ],
    "source": "aviationweather.gov (NOAA)",
}

EXPECTED_SACO = {
    "icao": "SACO",
    "name": "Cordoba/Taravella Intl",
    "issued_at": "2026-10-06T17:00:00Z",
    "valid_from": "2026-10-06T18:00:00Z",
    "valid_to": "2026-10-07T18:00:00Z",
    "raw": "TAF SACO 061700Z 0618/0718 05015KT 9999 SCT035 TX28/0719Z TN14/0710Z BECMG 0623/0702 02005KT 9999 BKN035 FEW040TCU BECMG 0703/0706 02005KT 7000 BKN030 PROB40 TEMPO 0706/0709 18010KT 7000 SCT015 OVC020 BECMG 0712/0715 29015KT 9999 SCT030 FEW040TCU",
    "periods": [
        {"change": "initial", "probability": None, "valid_from": "2026-10-06T18:00:00Z", "valid_to": "2026-10-06T23:00:00Z", "becoming_by": None, "wind": {"direction_deg": 50, "variable": False, "speed_kt": 15, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "SCT", "base_ft": 3500, "kind": None}], "weather": [], "flight_category": "VFR", "inherited": []},
        {"change": "becoming", "probability": None, "valid_from": "2026-10-06T23:00:00Z", "valid_to": "2026-10-07T03:00:00Z", "becoming_by": "2026-10-07T02:00:00Z", "wind": {"direction_deg": 20, "variable": False, "speed_kt": 5, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "BKN", "base_ft": 3500, "kind": None}, {"cover": "FEW", "base_ft": 4000, "kind": "TCU"}], "weather": [], "flight_category": "VFR", "inherited": []},
        {"change": "becoming", "probability": None, "valid_from": "2026-10-07T03:00:00Z", "valid_to": "2026-10-07T12:00:00Z", "becoming_by": "2026-10-07T06:00:00Z", "wind": {"direction_deg": 20, "variable": False, "speed_kt": 5, "gust_kt": None}, "visibility_m": 7000, "visibility_over": False, "clouds": [{"cover": "BKN", "base_ft": 3000, "kind": None}], "weather": [], "flight_category": "MVFR", "inherited": []},
        {"change": "tempo", "probability": 40, "valid_from": "2026-10-07T06:00:00Z", "valid_to": "2026-10-07T09:00:00Z", "becoming_by": None, "wind": {"direction_deg": 180, "variable": False, "speed_kt": 10, "gust_kt": None}, "visibility_m": 7000, "visibility_over": False, "clouds": [{"cover": "SCT", "base_ft": 1500, "kind": None}, {"cover": "OVC", "base_ft": 2000, "kind": None}], "weather": [], "flight_category": "MVFR", "inherited": []},
        {"change": "becoming", "probability": None, "valid_from": "2026-10-07T12:00:00Z", "valid_to": "2026-10-07T18:00:00Z", "becoming_by": "2026-10-07T15:00:00Z", "wind": {"direction_deg": 290, "variable": False, "speed_kt": 15, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "SCT", "base_ft": 3000, "kind": None}, {"cover": "FEW", "base_ft": 4000, "kind": "TCU"}], "weather": [], "flight_category": "VFR", "inherited": []},
    ],
    "temperatures": [
        {"kind": "max", "celsius": 28.0, "valid_at": "2026-10-06T19:00:00Z"},
        {"kind": "min", "celsius": 14.0, "valid_at": "2026-10-07T10:00:00Z"},
    ],
    "source": "aviationweather.gov (NOAA)",
}

EXPECTED_SARI = {
    "icao": "SARI",
    "name": "Puerto Iguazú Intl",
    "issued_at": "2026-10-06T17:00:00Z",
    "valid_from": "2026-10-06T18:00:00Z",
    "valid_to": "2026-10-07T18:00:00Z",
    "raw": "TAF SARI 061700Z 0618/0718 32005KT 9999 BKN020 TX25/0618Z TN20/0710Z PROB30 0622/0702 CAVOK BECMG 0702/0704 0500 FG OVC005",
    "periods": [
        {"change": "initial", "probability": None, "valid_from": "2026-10-06T18:00:00Z", "valid_to": "2026-10-07T02:00:00Z", "becoming_by": None, "wind": {"direction_deg": 320, "variable": False, "speed_kt": 5, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "BKN", "base_ft": 2000, "kind": None}], "weather": [], "flight_category": "MVFR", "inherited": []},
        {"change": "prob", "probability": 30, "valid_from": "2026-10-06T22:00:00Z", "valid_to": "2026-10-07T02:00:00Z", "becoming_by": None, "wind": {"direction_deg": 320, "variable": False, "speed_kt": 5, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "NSC", "base_ft": None, "kind": None}], "weather": ["NSW"], "flight_category": "VFR", "inherited": ["wind"]},
        {"change": "becoming", "probability": None, "valid_from": "2026-10-07T02:00:00Z", "valid_to": "2026-10-07T18:00:00Z", "becoming_by": "2026-10-07T04:00:00Z", "wind": {"direction_deg": 320, "variable": False, "speed_kt": 5, "gust_kt": None}, "visibility_m": 500, "visibility_over": False, "clouds": [{"cover": "OVC", "base_ft": 500, "kind": None}], "weather": ["FG"], "flight_category": "LIFR", "inherited": []},
    ],
    "temperatures": [
        {"kind": "min", "celsius": 20.0, "valid_at": "2026-10-07T10:00:00Z"},
        {"kind": "max", "celsius": 25.0, "valid_at": "2026-10-06T18:00:00Z"},
    ],
    "source": "aviationweather.gov (NOAA)",
}

EXPECTED_SASA = {
    "icao": "SASA",
    "name": "Salta/Guemes Arpt",
    "issued_at": "2026-10-06T17:00:00Z",
    "valid_from": "2026-10-06T18:00:00Z",
    "valid_to": "2026-10-07T18:00:00Z",
    "raw": "TAF SASA 061700Z 0618/0718 05010KT CAVOK TX28/0718Z TN13/0710Z TEMPO 0619/0622 05015KT 9999 SCT035 BECMG 0700/0703 VRB03KT 7000 BKN025 PROB40 TEMPO 0709/0712 2000 BR OVC010 BECMG 0713/0716 05010KT 9999 SCT035 FEW040TCU",
    "periods": [
        {"change": "initial", "probability": None, "valid_from": "2026-10-06T18:00:00Z", "valid_to": "2026-10-07T00:00:00Z", "becoming_by": None, "wind": {"direction_deg": 50, "variable": False, "speed_kt": 10, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "NSC", "base_ft": None, "kind": None}], "weather": [], "flight_category": "VFR", "inherited": []},
        {"change": "tempo", "probability": None, "valid_from": "2026-10-06T19:00:00Z", "valid_to": "2026-10-06T22:00:00Z", "becoming_by": None, "wind": {"direction_deg": 50, "variable": False, "speed_kt": 15, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "SCT", "base_ft": 3500, "kind": None}], "weather": [], "flight_category": "VFR", "inherited": []},
        {"change": "becoming", "probability": None, "valid_from": "2026-10-07T00:00:00Z", "valid_to": "2026-10-07T13:00:00Z", "becoming_by": "2026-10-07T03:00:00Z", "wind": {"direction_deg": None, "variable": True, "speed_kt": 3, "gust_kt": None}, "visibility_m": 7000, "visibility_over": False, "clouds": [{"cover": "BKN", "base_ft": 2500, "kind": None}], "weather": [], "flight_category": "MVFR", "inherited": []},
        {"change": "tempo", "probability": 40, "valid_from": "2026-10-07T09:00:00Z", "valid_to": "2026-10-07T12:00:00Z", "becoming_by": None, "wind": {"direction_deg": None, "variable": True, "speed_kt": 3, "gust_kt": None}, "visibility_m": 2000, "visibility_over": False, "clouds": [{"cover": "OVC", "base_ft": 1000, "kind": None}], "weather": ["BR"], "flight_category": "IFR", "inherited": ["wind"]},
        {"change": "becoming", "probability": None, "valid_from": "2026-10-07T13:00:00Z", "valid_to": "2026-10-07T18:00:00Z", "becoming_by": "2026-10-07T16:00:00Z", "wind": {"direction_deg": 50, "variable": False, "speed_kt": 10, "gust_kt": None}, "visibility_m": 10000, "visibility_over": True, "clouds": [{"cover": "SCT", "base_ft": 3500, "kind": None}, {"cover": "FEW", "base_ft": 4000, "kind": "TCU"}], "weather": [], "flight_category": "VFR", "inherited": []},
    ],
    "temperatures": [
        {"kind": "max", "celsius": 28.0, "valid_at": "2026-10-06T18:00:00Z"},
        {"kind": "min", "celsius": 13.0, "valid_at": "2026-10-07T10:00:00Z"},
    ],
    "source": "aviationweather.gov (NOAA)",
}

EXPECTED = {
    "SAAR": EXPECTED_SAAR,
    "SACO": EXPECTED_SACO,
    "SARI": EXPECTED_SARI,
    "SASA": EXPECTED_SASA,
}


@pytest.mark.parametrize("icao", ["SAAR", "SACO", "SARI", "SASA"])
async def test_decoded_taf_of_each_real_fixture(async_client: AsyncClient, icao: str) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=load_taf(icao)))
        response = await async_client.get("/api/taf", params={"icao": icao})

    assert response.status_code == 200
    assert response.json() == EXPECTED[icao]


async def test_lowercase_icao_gives_the_same_body_as_uppercase(async_client: AsyncClient) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=load_taf("SACO")))
        response = await async_client.get("/api/taf", params={"icao": "saco"})

    assert response.status_code == 200
    assert response.json() == EXPECTED_SACO


@pytest.mark.parametrize("payload", [[], [{"icaoId": "SAXX", "fcsts": []}], [{"icaoId": "SAXX"}], {}, ["x"]])
async def test_airport_without_a_usable_taf_is_404(async_client: AsyncClient, payload) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(return_value=httpx.Response(200, json=payload))
        response = await async_client.get("/api/taf", params={"icao": "SAXX"})

    assert response.status_code == 404
    assert response.json() == {"detail": "taf_not_found"}


@pytest.mark.parametrize("icao", ["SA-O", "SA O", "S@CO", "!!!!"])
async def test_icao_with_invalid_characters_is_422_invalid_icao(async_client: AsyncClient, icao: str) -> None:
    with respx.mock(assert_all_called=False):
        response = await async_client.get("/api/taf", params={"icao": icao})

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_icao"}


@pytest.mark.parametrize(
    ("params", "error_type"),
    [({"icao": "SAC"}, "string_too_short"), ({"icao": "SACOX"}, "string_too_long"), ({}, "missing")],
)
async def test_icao_of_the_wrong_length_or_missing_is_422(
    async_client: AsyncClient, params: dict, error_type: str
) -> None:
    with respx.mock(assert_all_called=False):
        response = await async_client.get("/api/taf", params=params)

    assert response.status_code == 422
    assert response.json() == {
        "error": "invalid_request",
        "message": "Parámetros inválidos",
        "detail": {"errors": [{"loc": ["query", "icao"], "type": error_type}]},
    }


@pytest.mark.parametrize(
    "failure",
    [
        {"return_value": httpx.Response(400, text="bad request")},
        {"return_value": httpx.Response(500, text="boom")},
        {"return_value": httpx.Response(200, text="not json")},
        {"side_effect": httpx.ConnectError("down")},
        {"side_effect": httpx.ReadTimeout("slow")},
    ],
    ids=["http-400", "http-500", "invalid-json", "connect-error", "timeout"],
)
async def test_awc_failure_is_503_taf_unavailable_not_404(async_client: AsyncClient, failure: dict) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.get(AWC_TAF_BASE).mock(**failure)
        response = await async_client.get("/api/taf", params={"icao": "SACO"})

    assert response.status_code == 503
    assert response.json() == {"detail": "taf_unavailable"}
