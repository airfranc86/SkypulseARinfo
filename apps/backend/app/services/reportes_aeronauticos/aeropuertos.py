"""Argentine airports, ICAO code normalization and the nearest-airport lookup.

Pure module: standard library only, no network. Station coordinates were checked against AWC
`stationinfo` (FRA-327); see `tests/test_metar_airports_reference.py`.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Airport:
    icao: str
    name: str
    lat: float
    lon: float


AR_AIRPORTS: tuple[Airport, ...] = (
    Airport("SAEZ", "Ezeiza",             -34.822, -58.536),
    Airport("SABE", "Aeroparque",         -34.559, -58.416),
    Airport("SACO", "Córdoba",            -31.323, -64.208),
    Airport("SAME", "Mendoza",            -32.832, -68.793),
    Airport("SAAR", "Rosario",            -32.919, -60.785),
    Airport("SANT", "Tucumán",            -26.841, -65.105),
    Airport("SASA", "Salta",              -24.856, -65.486),
    Airport("SANU", "San Juan",           -31.572, -68.418),
    Airport("SAZS", "Bariloche",          -41.151, -71.157),
    Airport("SAVC", "Comodoro Rivadavia", -45.785, -67.499),
    Airport("SAWG", "Río Gallegos",       -51.609, -69.313),
    Airport("SAZN", "Neuquén",            -38.949, -68.156),
    Airport("SAWH", "Ushuaia",            -54.843, -68.295),
    Airport("SAAC", "Concordia",         -31.297, -57.997),
    Airport("SAAG", "Gualeguaychú",      -33.011, -58.611),
    Airport("SAZR", "Santa Rosa",        -36.588, -64.276),
    Airport("SAVV", "Viedma",            -40.869, -63.000),
    Airport("SAMM", "Malargüe",          -35.493, -69.574),
    Airport("SAMR", "San Rafael",        -34.588, -68.404),
    Airport("SAZM", "Mar del Plata",     -37.934, -57.573),
)

_ICAO_RE = re.compile(r"[A-Z0-9]{4}")


def normalize_icao(code: str) -> str | None:
    """Trimmed, upper-case ICAO code (4 letters or digits), or None when it is not one."""
    upper = code.strip().upper()
    return upper if _ICAO_RE.fullmatch(upper) else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two coordinates (haversine)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def nearest_airport(lat: float, lon: float) -> Airport:
    """The Argentine airport closest to (lat, lon)."""
    return min(AR_AIRPORTS, key=lambda a: haversine_km(lat, lon, a.lat, a.lon))


def nearest_airport_with_distance(lat: float, lon: float) -> tuple[Airport, float]:
    """Closest Argentine airport and the real distance to it in km (pure lookup, no network)."""
    airport = nearest_airport(lat, lon)
    return airport, haversine_km(lat, lon, airport.lat, airport.lon)
