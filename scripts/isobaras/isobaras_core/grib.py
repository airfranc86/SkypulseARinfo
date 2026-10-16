"""Decode a GRIB2 message into a grid with latitude ascending and longitude in -180..180.

The orientation is read from the message (scan flags and first/last points), never assumed: the NOAA
bucket serves latitude north -> south with longitude 0..360, while a NOMADS subregion comes
south -> north.
"""

from __future__ import annotations

from dataclasses import dataclass

import eccodes as ec
import numpy as np

_TOLERANCIA_GRADOS = 1e-3


class GribInvalido(ValueError):
    """The bytes are not a GRIB2 message we can use."""


@dataclass(frozen=True)
class Campo:
    """A regular lat/lon field. `valores[j, i]` is the value at `lat[j]`, `lon[i]`; both axes ascend."""

    lat: np.ndarray
    lon: np.ndarray
    valores: np.ndarray


def _clave(h: int, nombre: str):
    try:
        return ec.codes_get(h, nombre)
    except ec.CodesInternalError as e:
        raise GribInvalido(f"el GRIB no tiene la clave {nombre}") from e


def decodificar(mensaje: bytes) -> Campo:
    """Decode one GRIB2 message. Rejects anything that is not a regular lat/lon grid."""
    try:
        h = ec.codes_new_from_message(bytes(mensaje))
    except Exception as e:  # eccodes raises several error types for bytes that are not a message
        raise GribInvalido(f"no es un mensaje GRIB válido: {type(e).__name__}") from e
    try:
        tipo = _clave(h, "gridType")
        if tipo != "regular_ll":
            raise GribInvalido(f"se esperaba una grilla regular_ll y llegó {tipo}")
        ni, nj = int(_clave(h, "Ni")), int(_clave(h, "Nj"))
        lat0 = float(_clave(h, "latitudeOfFirstGridPointInDegrees"))
        lat1 = float(_clave(h, "latitudeOfLastGridPointInDegrees"))
        lon0 = float(_clave(h, "longitudeOfFirstGridPointInDegrees"))
        d_lon = float(_clave(h, "iDirectionIncrementInDegrees"))
        d_lat = float(_clave(h, "jDirectionIncrementInDegrees"))
        if _clave(h, "bitmapPresent"):
            raise GribInvalido("el GRIB trae bitmap: los datos faltantes no se manejan")
        if _clave(h, "jPointsAreConsecutive"):
            raise GribInvalido("el GRIB barre por columnas (jPointsAreConsecutive): no soportado")
        j_positivo = bool(_clave(h, "jScansPositively"))
        i_negativo = bool(_clave(h, "iScansNegatively"))
        valores = np.asarray(ec.codes_get_values(h), dtype=float)
    finally:
        ec.codes_release(h)

    if ni < 2 or nj < 2 or valores.size != ni * nj:
        raise GribInvalido(f"tamaño inconsistente: {ni}x{nj} no coincide con {valores.size} valores")

    lat = lat0 + np.arange(nj) * (d_lat if j_positivo else -d_lat)
    if abs(lat[-1] - lat1) > _TOLERANCIA_GRADOS:
        raise GribInvalido("la última latitud no coincide con la dirección de barrido declarada")
    lon = lon0 + np.arange(ni) * (-d_lon if i_negativo else d_lon)
    lon = (lon + 180.0) % 360.0 - 180.0  # 0..360 -> -180..180

    grilla = valores.reshape(nj, ni)
    orden_lat = np.argsort(lat)
    orden_lon = np.argsort(lon)
    lat, lon = lat[orden_lat], lon[orden_lon]
    if np.any(np.diff(lon) <= 0):
        raise GribInvalido("longitudes repetidas después de pasar a -180..180")
    return Campo(lat=lat, lon=lon, valores=grilla[np.ix_(orden_lat, orden_lon)])


def recortar(campo: Campo, *, lat_min: float, lat_max: float, lon_min: float, lon_max: float, margen: float = 0.0) -> Campo:
    """The part of `campo` inside the box, grown by `margen` degrees on every side."""
    eps = 1e-9
    filas = (campo.lat >= lat_min - margen - eps) & (campo.lat <= lat_max + margen + eps)
    cols = (campo.lon >= lon_min - margen - eps) & (campo.lon <= lon_max + margen + eps)
    if not filas.any() or not cols.any():
        raise GribInvalido("el recorte pedido no toca la grilla")
    return Campo(lat=campo.lat[filas], lon=campo.lon[cols], valores=campo.valores[np.ix_(filas, cols)])
