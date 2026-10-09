"""Immutable table of target stations: SMN ``regtemp`` name -> ICAO, WMO id, lat, lon.

Source: AWC ``stationinfo`` API (aviationweather.gov/api/data/stationinfo), checked by the
coordinator on 2026-10-05. The 8 stations that were first copied from
``_AR_AIRPORTS`` (now ``AR_AIRPORTS`` in
``apps/backend/app/services/reportes_aeronauticos/aeropuertos.py``) are kept as they were because
they differ from AWC by less than 0.01 degrees (SACO: -31.323 vs -31.324 in AWC; SAZM:
-37.934/-57.573 vs -37.932/-57.581 in AWC).

WARNING: ``metar.py`` has 3 wrong ICAO codes: Rosario is listed as SARS (really Presidencia
Roque Saenz Pena; correct SAAR), Bariloche as SAVB (really El Bolson; correct SAZS) and
Neuquen as SAWO (returns no data; correct SAZN). They are NOT fixed here (out of scope);
this table uses the correct codes and AWC coordinates for those three.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Station:
    """A verification station matched between the SMN file and a coordinate source."""

    smn_name: str
    icao: str
    wmo_id: str
    lat: float
    lon: float
    partial_coverage: bool = False  # fewer than 365 days of observations in regtemp


STATIONS: tuple[Station, ...] = (
    Station("AEROPARQUE AERO", "SABE", "87582", -34.559, -58.416),
    Station("EZEIZA AERO", "SAEZ", "87576", -34.822, -58.536),
    Station("CORDOBA AERO", "SACO", "87344", -31.323, -64.208),
    Station("ROSARIO AERO", "SAAR", "87480", -32.918, -60.782),
    Station("NEUQUEN AERO", "SAZN", "87715", -38.950, -68.141),
    Station("SALTA AERO", "SASA", "87047", -24.856, -65.486),
    Station("TUCUMAN AERO", "SANT", "87121", -26.841, -65.105),
    Station("RESISTENCIA AERO", "SARE", "87155", -27.450, -59.056),
    Station("BAHIA BLANCA AERO", "SAZB", "87750", -38.725, -62.169),
    Station("BARILOCHE AERO", "SAZS", "87765", -41.151, -71.157),
    Station("MAR DEL PLATA AERO", "SAZM", "87692", -37.934, -57.573),
    Station("POSADAS AERO", "SARP", "87178", -27.386, -55.969),
    Station("MENDOZA AERO", "SAME", "87418", -32.832, -68.793, partial_coverage=True),  # 363 days
    Station("USHUAIA AERO", "SAWH", "87938", -54.843, -68.295, partial_coverage=True),  # 333 days
)

STATIONS_BY_NAME = MappingProxyType({s.smn_name: s for s in STATIONS})


def get_station(smn_name: str) -> Station:
    """Return the station for an SMN name or raise ``KeyError`` with a clear message."""
    try:
        return STATIONS_BY_NAME[smn_name]
    except KeyError:
        raise KeyError(f"unknown station {smn_name!r}; known: {sorted(STATIONS_BY_NAME)}") from None
