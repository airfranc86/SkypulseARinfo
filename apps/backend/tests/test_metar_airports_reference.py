"""Los aeropuertos de `AR_AIRPORTS` coinciden con la referencia verificada (FRA-327).

La lista tenía varios códigos ICAO equivocados (SARS, SAVB, SAWO, SASJ, SAWC,
SAVT, SAWP) con coordenadas y nombres de la ciudad correcta: AWC devolvía el
METAR de otra estación (o ninguno). La referencia sale de `stationinfo` de AWC
(2026-10-05). Test puro: sin llamadas externas.
"""
from __future__ import annotations

import pytest

from app.services.reportes_aeronauticos.aeropuertos import AR_AIRPORTS as _AR_AIRPORTS

# ICAO -> (lat, lon) según AWC stationinfo.
_REFERENCE: dict[str, tuple[float, float]] = {
    "SAEZ": (-34.822, -58.536),  # Ezeiza (Pistarini)
    "SABE": (-34.559, -58.416),  # Aeroparque (Newbery)
    "SACO": (-31.324, -64.208),  # Córdoba (Taravella)
    "SAME": (-32.832, -68.793),  # Mendoza (Plumerillo)
    "SAAR": (-32.918, -60.782),  # Rosario Intl
    "SANT": (-26.841, -65.105),  # Tucumán
    "SASA": (-24.856, -65.486),  # Salta (Güemes)
    "SANU": (-31.572, -68.418),  # San Juan
    "SAZS": (-41.151, -71.157),  # Bariloche
    "SAVC": (-45.790, -67.471),  # Comodoro Rivadavia
    "SAWG": (-51.609, -69.306),  # Río Gallegos
    "SAZN": (-38.950, -68.141),  # Neuquén
    "SAWH": (-54.844, -68.308),  # Ushuaia
    "SAAC": (-31.308, -58.016),  # Concordia
    "SAAG": (-33.010, -58.613),  # Gualeguaychú
    "SAZR": (-36.593, -64.280),  # Santa Rosa
    "SAVV": (-40.867, -63.001),  # Viedma
    "SAMM": (-35.481, -69.583),  # Malargüe
    "SAMR": (-34.585, -68.414),  # San Rafael
    "SAZM": (-37.932, -57.581),  # Mar del Plata
}

# Códigos que se habían usado por error y no deben volver a aparecer.
_WRONG_CODES = (
    "SARS", "SAVB", "SAWO", "SASJ", "SAWC",
    "SAVT", "SAWP", "SAAI", "SADP", "SATK",
)

# Tolerancia (grados) entre la coordenada del repo y la de AWC.
_TOLERANCE_DEG = 0.05


def _icaos() -> list[str]:
    return [airport.icao for airport in _AR_AIRPORTS]


def test_icao_set_matches_reference() -> None:
    assert set(_icaos()) == set(_REFERENCE)


def test_no_duplicate_icao_codes() -> None:
    codes = _icaos()
    assert len(codes) == len(set(codes))


def test_no_known_wrong_codes_present() -> None:
    present = sorted(set(_icaos()) & set(_WRONG_CODES))
    assert present == []


@pytest.mark.parametrize("icao", sorted(_REFERENCE))
def test_airport_is_near_reference_coordinates(icao: str) -> None:
    airport = next((a for a in _AR_AIRPORTS if a.icao == icao), None)
    assert airport is not None, f"{icao} no está en _AR_AIRPORTS"
    ref_lat, ref_lon = _REFERENCE[icao]
    assert abs(airport.lat - ref_lat) < _TOLERANCE_DEG
    assert abs(airport.lon - ref_lon) < _TOLERANCE_DEG
