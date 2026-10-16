"""Decoding a GRIB2 message into a grid the rest of the pipeline can trust: latitude ascending, longitude -180..180."""

from __future__ import annotations

import eccodes as ec
import numpy as np
import pytest

from isobaras_core.grib import GribInvalido, decodificar, recortar
from tests.conftest import LATS, LONS, hacer_grib, valor


def _esperado(campo):
    """The value each cell must have, rebuilt from its own coordinates."""
    return np.array([[valor(la, lo % 360) for lo in campo.lon] for la in campo.lat])


def test_norte_sur_sale_con_latitud_ascendente_y_longitud_de_menos_180_a_180(grib_norte_sur):
    campo = decodificar(grib_norte_sur)
    assert list(campo.lat) == [-90, -45, 0, 45, 90]
    assert list(campo.lon) == [-180, -135, -90, -45, 0, 45, 90, 135]
    assert campo.valores.shape == (5, 8)
    np.testing.assert_allclose(campo.valores, _esperado(campo))


def test_sur_norte_da_exactamente_la_misma_grilla_que_norte_sur(grib_norte_sur, grib_sur_norte):
    a = decodificar(grib_norte_sur)
    b = decodificar(grib_sur_norte)
    np.testing.assert_array_equal(a.lat, b.lat)
    np.testing.assert_array_equal(a.lon, b.lon)
    np.testing.assert_allclose(a.valores, b.valores)


def test_longitud_que_ya_viene_de_menos_180_a_180_no_se_reordena():
    lons = np.arange(8) * 45.0 - 180  # -180 .. 135
    valores = np.array([[valor(la, lo % 360) for lo in lons] for la in LATS])
    campo = decodificar(hacer_grib(8, 5, 90, -90, -180, 135, valores, j_positivo=False))
    assert list(campo.lon) == list(lons)
    np.testing.assert_allclose(campo.valores, _esperado(campo))


def test_la_orientacion_se_lee_del_archivo_y_no_se_supone():
    """The same numbers laid out south -> north: reading them as north -> south would flip the map."""
    valores = np.array([[valor(la, lo) for lo in LONS] for la in LATS[::-1]])
    campo = decodificar(hacer_grib(8, 5, -90, 90, 0, 315, valores, j_positivo=True))
    assert campo.lat[0] == -90
    np.testing.assert_allclose(campo.valores, _esperado(campo))


def test_i_negativo_se_interpreta_bien():
    lons = 315 - np.arange(8) * 45.0  # 315 .. 0
    valores = np.array([[valor(la, lo) for lo in lons] for la in LATS])
    campo = decodificar(hacer_grib(8, 5, 90, -90, 315, 0, valores, j_positivo=False, i_negativo=True))
    np.testing.assert_allclose(campo.valores, _esperado(campo))


def test_una_grilla_que_no_es_latlon_regular_se_rechaza():
    h = ec.codes_grib_new_from_samples("reduced_gg_pl_32_grib2")
    try:
        mensaje = ec.codes_get_message(h)
    finally:
        ec.codes_release(h)
    with pytest.raises(GribInvalido) as e:
        decodificar(mensaje)
    assert "regular_ll" in str(e.value)


def test_bytes_que_no_son_un_grib_se_rechazan():
    with pytest.raises(GribInvalido):
        decodificar(b"esto no es un GRIB")


def test_recortar_deja_solo_la_caja_pedida_mas_el_margen(grib_norte_sur):
    campo = decodificar(grib_norte_sur)
    r = recortar(campo, lat_min=-45, lat_max=45, lon_min=-90, lon_max=0)
    assert list(r.lat) == [-45, 0, 45]
    assert list(r.lon) == [-90, -45, 0]
    np.testing.assert_allclose(r.valores, _esperado(r))
    con_margen = recortar(campo, lat_min=-45, lat_max=45, lon_min=-90, lon_max=0, margen=45)
    assert list(con_margen.lat) == [-90, -45, 0, 45, 90]
    assert list(con_margen.lon) == [-135, -90, -45, 0, 45]


def test_recortar_a_una_caja_vacia_se_rechaza(grib_norte_sur):
    with pytest.raises(GribInvalido):
        recortar(decodificar(grib_norte_sur), lat_min=100, lat_max=120, lon_min=0, lon_max=10)


def _con_clave(clave: str, valor: int) -> bytes:
    h = ec.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        ec.codes_set(h, "Ni", 8)
        ec.codes_set(h, "Nj", 5)
        ec.codes_set(h, "latitudeOfFirstGridPointInDegrees", 90)
        ec.codes_set(h, "latitudeOfLastGridPointInDegrees", -90)
        ec.codes_set(h, "longitudeOfFirstGridPointInDegrees", 0)
        ec.codes_set(h, "longitudeOfLastGridPointInDegrees", 315)
        ec.codes_set(h, "iDirectionIncrementInDegrees", 45)
        ec.codes_set(h, "jDirectionIncrementInDegrees", 45)
        ec.codes_set(h, clave, valor)
        ec.codes_set_values(h, np.full(40, 101300.0))
        return ec.codes_get_message(h)
    finally:
        ec.codes_release(h)


def test_un_grib_con_barrido_por_columnas_se_rechaza():
    with pytest.raises(GribInvalido) as e:
        decodificar(_con_clave("jPointsAreConsecutive", 1))
    assert "jPointsAreConsecutive" in str(e.value)


def test_un_grib_con_bitmap_se_rechaza():
    with pytest.raises(GribInvalido) as e:
        decodificar(_con_clave("bitmapPresent", 1))
    assert "bitmap" in str(e.value)
