"""Airport list, ICAO normalization and nearest-airport lookup (`reportes_aeronauticos.aeropuertos`).

Pure tests: no network. The expected stations and distances are the ones the lookup returned before
it moved out of `services/metar.py`.
"""
from __future__ import annotations

import dataclasses

import pytest

from app.services.reportes_aeronauticos.aeropuertos import (
    AR_AIRPORTS,
    Airport,
    haversine_km,
    nearest_airport,
    nearest_airport_with_distance,
    normalize_icao,
)

EXPECTED_ORDER = [
    "SAEZ", "SABE", "SACO", "SAME", "SAAR", "SANT", "SASA", "SANU", "SAZS", "SAVC",
    "SAWG", "SAZN", "SAWH", "SAAC", "SAAG", "SAZR", "SAVV", "SAMM", "SAMR", "SAZM",
]  # fmt: skip


# ---------------------------------------------------------------- normalize_icao


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SACO", "SACO"),
        (" saco ", "SACO"),
        ("saco", "SACO"),
        ("\tSaEz\n", "SAEZ"),
        ("S4C0", "S4C0"),
        ("1234", "1234"),
    ],
)
def test_normalize_icao_accepts_four_letters_or_digits(raw, expected) -> None:
    assert normalize_icao(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["SA-1", "SAC", "SACOO", "SA CO", "", "    ", "SAC.", "SÁCO", "SA_O", "SAC\nO"],
)
def test_normalize_icao_gives_none_when_it_is_not_four_alphanumerics(raw) -> None:
    assert normalize_icao(raw) is None


# ---------------------------------------------------------------- the list


def test_airports_keep_their_data_and_order() -> None:
    assert [a.icao for a in AR_AIRPORTS] == EXPECTED_ORDER
    saco = next(a for a in AR_AIRPORTS if a.icao == "SACO")
    assert (saco.name, saco.lat, saco.lon) == ("Córdoba", -31.323, -64.208)


def test_airport_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        AR_AIRPORTS[0].name = "x"  # type: ignore[misc]
    assert isinstance(AR_AIRPORTS[0], Airport)


# ---------------------------------------------------------------- nearest


@pytest.mark.parametrize(
    ("lat", "lon", "icao", "km"),
    [
        (-31.42, -64.18, "SACO", 11.10866192880506),
        (-34.6, -58.4, "SABE", 4.788538589072882),
        (-32.95, -60.65, "SAAR", 13.061929827739503),
        (-32.89, -68.84, "SAME", 7.801598601552831),
        (-26.83, -65.2, "SANT", 9.504922217319109),
        (-41.13, -71.31, "SAZS", 13.023382069736895),
        (-54.8, -68.3, "SAWH", 4.792098873552121),
        (-45.86, -67.48, "SAVC", 8.468585706825195),
        (-38.0, -57.55, "SAZM", 7.610790203911304),
        (-24.79, -65.41, "SASA", 10.615478014477874),
        (-31.323, -64.208, "SACO", 0.0),
        (0.0, 0.0, "SAAC", 7013.457333563673),
    ],
)
def test_nearest_airport_with_distance_matches_what_it_returned_before(lat, lon, icao, km) -> None:
    airport, distance = nearest_airport_with_distance(lat, lon)
    assert airport.icao == icao
    assert distance == pytest.approx(km, rel=1e-12, abs=1e-9)


def test_nearest_airport_is_the_first_of_the_with_distance_pair() -> None:
    assert nearest_airport(-31.42, -64.18) is nearest_airport_with_distance(-31.42, -64.18)[0]


def test_haversine_km() -> None:
    assert haversine_km(-31.3, -64.2, -31.3, -64.2) == pytest.approx(0.0, abs=1e-9)
    assert haversine_km(-31.0, -64.0, -32.0, -64.0) == pytest.approx(111.2, abs=0.5)
