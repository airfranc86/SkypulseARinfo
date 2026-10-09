"""Aeronautical reports (METAR/TAF from AWC): the public surface of the package.

Routers and services import from here, never from the submodules' private names:

- `awc`         the one place that builds AWC requests (`get_source` / `set_source`, `AwcError`)
- `aeropuertos` Argentine airports, ICAO codes and the nearest-airport lookup (pure)
- `metar`       current visibility from the METAR of the nearest airport
- `taf`         the TAF entry and its hourly visibility projection

`clear_caches()` empties the METAR and TAF caches (used by tests). The caches and the AWC budget will
merge into one in Phase 1c.
"""
from __future__ import annotations

from app.services.reportes_aeronauticos.aeropuertos import (
    AR_AIRPORTS,
    Airport,
    nearest_airport,
    nearest_airport_with_distance,
    normalize_icao,
)
from app.services.reportes_aeronauticos.awc import (
    AwcError,
    AwcSource,
    HttpAwcSource,
    get_source,
    set_source,
)
from app.services.reportes_aeronauticos.metar import (
    MetarVisibility,
    clear_metar_cache,
    get_metar_visibility,
    get_nearest_metar_visibility,
)
from app.services.reportes_aeronauticos.taf import (
    TafFetchError,
    TafHourlySlot,
    clear_taf_cache,
    fetch_taf_entry,
    get_nearest_taf_hourly,
    get_taf_for_icao,
    taf_hourly_slots,
)
from app.services.taf_decoded import normalize_taf

__all__ = [
    "AR_AIRPORTS",
    "Airport",
    "AwcError",
    "AwcSource",
    "HttpAwcSource",
    "MetarVisibility",
    "TafFetchError",
    "TafHourlySlot",
    "clear_caches",
    "fetch_taf_entry",
    "get_metar_visibility",
    "get_nearest_metar_visibility",
    "get_nearest_taf_hourly",
    "get_source",
    "get_taf_for_icao",
    "nearest_airport",
    "nearest_airport_with_distance",
    "normalize_icao",
    "normalize_taf",
    "set_source",
    "taf_hourly_slots",
]


def clear_caches() -> None:
    """Empty the METAR and the TAF caches."""
    clear_metar_cache()
    clear_taf_cache()
