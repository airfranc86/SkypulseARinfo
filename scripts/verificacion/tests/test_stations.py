"""Tests for the target station table."""

from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import pytest

from stations import STATIONS, STATIONS_BY_NAME, Station, get_station

METAR_PATH = (
    Path(__file__).resolve().parents[3]
    / "apps" / "backend" / "app" / "services" / "reportes_aeronauticos" / "aeropuertos.py"
)

# SMN station coordinates and aerodrome coordinates may differ by a little (SAAR ~0.3 km, SAZN ~1.3 km today).
MAX_COORDINATE_GAP_KM = 2.0


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine) in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def test_names_and_icao_are_unique() -> None:
    assert len({s.smn_name for s in STATIONS}) == len(STATIONS)
    assert len({s.icao for s in STATIONS}) == len(STATIONS)


EXPECTED_WMO = {
    "SABE": "87582", "SAEZ": "87576", "SACO": "87344", "SASA": "87047", "SANT": "87121",
    "SAZM": "87692", "SAME": "87418", "SAWH": "87938", "SAAR": "87480", "SAZN": "87715",
    "SAZS": "87765", "SARE": "87155", "SAZB": "87750", "SARP": "87178",
}  # fmt: skip


def test_table_has_the_14_target_stations() -> None:
    assert len(STATIONS) == 14
    assert {s.icao for s in STATIONS} == set(EXPECTED_WMO)
    assert {s.smn_name for s in STATIONS} == {
        "AEROPARQUE AERO", "EZEIZA AERO", "CORDOBA AERO", "ROSARIO AERO", "NEUQUEN AERO",
        "SALTA AERO", "TUCUMAN AERO", "RESISTENCIA AERO", "BAHIA BLANCA AERO",
        "BARILOCHE AERO", "MAR DEL PLATA AERO", "POSADAS AERO", "MENDOZA AERO",
        "USHUAIA AERO",
    }  # fmt: skip


def test_wmo_ids_are_unique_and_match_awc() -> None:
    assert len({s.wmo_id for s in STATIONS}) == len(STATIONS)
    assert {s.icao: s.wmo_id for s in STATIONS} == EXPECTED_WMO


def test_stations_confirmed_against_awc_have_their_coordinates() -> None:
    by_icao = {s.icao: (s.lat, s.lon) for s in STATIONS}

    assert by_icao["SAAR"] == (-32.918, -60.782)
    assert by_icao["SAZN"] == (-38.950, -68.141)
    assert by_icao["SAZS"] == (-41.151, -71.157)
    assert by_icao["SARE"] == (-27.450, -59.056)
    assert by_icao["SAZB"] == (-38.725, -62.169)
    assert by_icao["SARP"] == (-27.386, -55.969)


def test_partial_coverage_flags() -> None:
    partial = {s.smn_name for s in STATIONS if s.partial_coverage}

    assert partial == {"MENDOZA AERO", "USHUAIA AERO"}


def test_coordinates_are_inside_argentina() -> None:
    for s in STATIONS:
        assert -56.0 < s.lat < -21.0, s
        assert -74.0 < s.lon < -53.0, s


def test_lookup_by_name() -> None:
    assert get_station("EZEIZA AERO").icao == "SAEZ"
    assert STATIONS_BY_NAME["AEROPARQUE AERO"].icao == "SABE"


def test_lookup_unknown_station_raises() -> None:
    with pytest.raises(KeyError, match="NOWHERE"):
        get_station("NOWHERE AERO")


def test_station_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        STATIONS[0].lat = 0.0  # type: ignore[misc]


def test_table_is_a_tuple_of_stations() -> None:
    assert isinstance(STATIONS, tuple)
    assert all(isinstance(s, Station) for s in STATIONS)


@pytest.mark.skipif(not METAR_PATH.exists(), reason="aeropuertos.py not available")
def test_coordinates_match_metar_for_stations_whose_icao_is_in_metar() -> None:
    source = METAR_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r'Airport\("(\w{4})",\s*"[^"]*",\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\)')
    in_metar = {m[1]: (float(m[2]), float(m[3])) for m in pattern.finditer(source)}

    shared = [s for s in STATIONS if s.icao in in_metar]

    # The backend list grows over time: these eight must stay shared, new ones are allowed.
    assert {
        "SABE", "SAEZ", "SACO", "SASA", "SANT", "SAZM", "SAME", "SAWH",
    } <= {s.icao for s in shared}  # fmt: skip
    for station in shared:
        lat, lon = in_metar[station.icao]
        distance = _distance_km(lat, lon, station.lat, station.lon)
        assert distance <= MAX_COORDINATE_GAP_KM, (station.icao, distance)


def test_wrong_icao_codes_of_metar_are_not_used() -> None:
    # metar.py lists Rosario as SARS, Bariloche as SAVB and Neuquen as SAWO (all wrong).
    assert {"SARS", "SAVB", "SAWO"}.isdisjoint({s.icao for s in STATIONS})
