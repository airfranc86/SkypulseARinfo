"""Shared helpers: tiny GRIB2 messages built with eccodes, so the decoder is tested without the network."""

from __future__ import annotations

import eccodes as ec
import numpy as np
import pytest


def hacer_grib(
    ni: int,
    nj: int,
    lat_primera: float,
    lat_ultima: float,
    lon_primera: float,
    lon_ultima: float,
    valores: np.ndarray,
    *,
    j_positivo: bool,
    i_negativo: bool = False,
) -> bytes:
    """A regular lat/lon GRIB2 message whose values are given in file scan order (rows follow first -> last latitude)."""
    h = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        ec.codes_set(h, "Ni", ni)
        ec.codes_set(h, "Nj", nj)
        ec.codes_set(h, "jScansPositively", 1 if j_positivo else 0)
        ec.codes_set(h, "iScansNegatively", 1 if i_negativo else 0)
        ec.codes_set(h, "latitudeOfFirstGridPointInDegrees", lat_primera)
        ec.codes_set(h, "latitudeOfLastGridPointInDegrees", lat_ultima)
        ec.codes_set(h, "longitudeOfFirstGridPointInDegrees", lon_primera)
        ec.codes_set(h, "longitudeOfLastGridPointInDegrees", lon_ultima)
        ec.codes_set(h, "iDirectionIncrementInDegrees", abs(lon_ultima - lon_primera) / (ni - 1))
        ec.codes_set(h, "jDirectionIncrementInDegrees", abs(lat_ultima - lat_primera) / (nj - 1))
        ec.codes_set(h, "bitsPerValue", 24)
        ec.codes_set_values(h, np.asarray(valores, dtype=float).ravel())
        return ec.codes_get_message(h)
    finally:
        ec.codes_release(h)


LATS = np.array([90.0, 45.0, 0.0, -45.0, -90.0])  # north -> south
LONS = np.arange(8) * 45.0  # 0 .. 315


def valor(lat: float, lon360: float) -> float:
    """A value that encodes where it is, so any mix-up of rows or columns is visible."""
    return lat * 1000 + lon360


@pytest.fixture
def grib_norte_sur() -> bytes:
    """Like the NOAA bucket: latitude 90 -> -90 and longitude 0 -> 315."""
    valores = np.array([[valor(la, lo) for lo in LONS] for la in LATS])
    return hacer_grib(8, 5, 90, -90, 0, 315, valores, j_positivo=False)


@pytest.fixture
def grib_sur_norte() -> bytes:
    """Like a NOMADS subregion: latitude -90 -> 90 and longitude 0 -> 315."""
    valores = np.array([[valor(la, lo) for lo in LONS] for la in LATS[::-1]])
    return hacer_grib(8, 5, -90, 90, 0, 315, valores, j_positivo=True)
