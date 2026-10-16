"""Turning a smoothed pressure grid into simplified isobar lines and deciding where their labels go."""

from __future__ import annotations

import numpy as np
import pytest

from isobaras_core.curvas import CurvaCruda, etiquetas, niveles, simplificar, suavizar, trazar
from isobaras_core.formato import Bbox
from isobaras_core.grib import Campo

BBOX = Bbox(lon_min=-90, lat_min=-62, lon_max=-30, lat_max=-12)


def _grilla(lat_min=-62.0, lat_max=-12.0, lon_min=-90.0, lon_max=-30.0, paso=0.25):
    lat = np.arange(lat_min, lat_max + paso / 2, paso)
    lon = np.arange(lon_min, lon_max + paso / 2, paso)
    return lat, lon


def _pozo(centro=(-37.0, -60.0), amplitud=20.0, s=4.0, base=1013.0, signo=1.0) -> Campo:
    """A Gaussian high (or low with signo=-1) over a flat 1013 hPa field."""
    lat, lon = _grilla()
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    r2 = (la - centro[0]) ** 2 + (lo - centro[1]) ** 2
    return Campo(lat, lon, base + signo * amplitud * np.exp(-r2 / (2 * s * s)))


# ── niveles ──────────────────────────────────────────────────────────────────


def test_niveles_son_multiplos_del_intervalo_dentro_del_rango():
    assert niveles(1001.2, 1017.9, 4) == [1004, 1008, 1012, 1016]
    assert niveles(1004.0, 1012.0, 4) == [1004, 1008, 1012]
    assert niveles(1005.0, 1006.0, 4) == []


# ── suavizar ─────────────────────────────────────────────────────────────────


def test_suavizar_no_cambia_un_campo_plano_y_baja_un_pico():
    plano = Campo(*_grilla(), np.full((201, 241), 1013.0))
    np.testing.assert_allclose(suavizar(plano, 2.0).valores, 1013.0)
    pozo = _pozo(s=0.25)  # a spike one cell wide
    assert suavizar(pozo, 2.0).valores.max() < pozo.valores.max()


def test_suavizar_no_muta_el_campo_original():
    pozo = _pozo()
    antes = pozo.valores.copy()
    suavizar(pozo, 2.0)
    np.testing.assert_array_equal(pozo.valores, antes)


# ── trazar ───────────────────────────────────────────────────────────────────


def test_un_alto_gaussiano_da_anillos_cerrados_sin_repetir_el_primer_punto():
    curvas = trazar(suavizar(_pozo(), 2.0), 4)
    assert sorted(c.p for c in curvas) == [1016, 1020, 1024, 1028, 1032]
    for c in curvas:
        assert c.cerrada
        assert not np.array_equal(c.puntos[0], c.puntos[-1])
        assert len(c.puntos) >= 3


def test_los_anillos_rodean_el_centro_y_se_achican_hacia_arriba():
    curvas = {c.p: c for c in trazar(suavizar(_pozo(centro=(-37.0, -60.0)), 2.0), 4)}
    for c in curvas.values():
        assert abs(c.puntos[:, 0].mean() - -37.0) < 0.3
        assert abs(c.puntos[:, 1].mean() - -60.0) < 0.3
    radio = {p: np.ptp(c.puntos[:, 0]) for p, c in curvas.items()}
    assert radio[1016] > radio[1020] > radio[1024] > radio[1028] > radio[1032]


def test_un_gradiente_plano_da_lineas_abiertas_que_llegan_a_los_bordes():
    lat, lon = _grilla()
    la, _ = np.meshgrid(lat, lon, indexing="ij")
    campo = Campo(lat, lon, 1000.2 + 0.5 * (la + 62.0))  # 1000.2 at the south edge, 1025.2 at the north edge
    curvas = trazar(campo, 4)
    assert sorted(c.p for c in curvas) == [1004, 1008, 1012, 1016, 1020, 1024]
    for c in curvas:
        assert not c.cerrada
        assert c.puntos[:, 1].min() == pytest.approx(-90.0)
        assert c.puntos[:, 1].max() == pytest.approx(-30.0)


def test_ninguna_curva_sale_de_la_grilla():
    for c in trazar(suavizar(_pozo(centro=(-20.0, -80.0), s=9.0), 2.0), 4):
        assert c.puntos[:, 0].min() >= -62 and c.puntos[:, 0].max() <= -12
        assert c.puntos[:, 1].min() >= -90 and c.puntos[:, 1].max() <= -30


def test_un_campo_plano_no_da_curvas():
    assert trazar(Campo(*_grilla(), np.full((201, 241), 1013.0)), 4) == []


# ── simplificar ──────────────────────────────────────────────────────────────


def test_puntos_alineados_se_reducen_a_los_extremos():
    linea = np.array([[0.0, 0.0], [0.0, 1.0], [0.0, 2.0], [0.0, 3.0]])
    np.testing.assert_array_equal(simplificar(linea, 0.03, cerrada=False), linea[[0, 3]])


def test_simplificar_respeta_la_tolerancia_y_conserva_los_extremos():
    t = np.linspace(0, np.pi, 200)
    arco = np.column_stack([np.sin(t) * 5, np.cos(t) * 5])
    tol = 0.03
    s = simplificar(arco, tol, cerrada=False)
    assert len(s) < len(arco) / 3
    np.testing.assert_array_equal(s[0], arco[0])
    np.testing.assert_array_equal(s[-1], arco[-1])
    # every original point is within the tolerance of the simplified polyline
    for p in arco:
        d = min(_dist_segmento(p, s[i], s[i + 1]) for i in range(len(s) - 1))
        assert d <= tol + 1e-9


def _dist_segmento(p, a, b):
    ab = b - a
    t = 0.0 if not ab.any() else np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1)
    return float(np.linalg.norm(p - (a + t * ab)))


def test_un_anillo_simplificado_sigue_siendo_cerrado_sin_repetir_el_primer_punto():
    t = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    anillo = np.column_stack([np.sin(t) * 5, np.cos(t) * 5])
    s = simplificar(anillo, 0.03, cerrada=True)
    assert 8 <= len(s) < 200
    assert not np.array_equal(s[0], s[-1])


def test_un_anillo_diminuto_se_descarta():
    t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    assert simplificar(np.column_stack([np.sin(t) * 0.01, np.cos(t) * 0.01]), 0.03, cerrada=True) is None


# ── etiquetas ────────────────────────────────────────────────────────────────


def _recta(largo: float, lat=-37.0, lon0=-80.0) -> np.ndarray:
    return np.array([[lat, lon0], [lat, lon0 + largo]])


def test_una_curva_corta_no_lleva_etiqueta():
    assert etiquetas(_recta(3.9), False, BBOX) == []


def test_una_curva_de_largo_medio_lleva_una_etiqueta_en_el_medio():
    (e,) = etiquetas(_recta(10), False, BBOX)
    assert e[0] == pytest.approx(-37.0)
    assert e[1] == pytest.approx(-75.0, abs=0.3)


def test_una_curva_muy_larga_lleva_dos_etiquetas_separadas():
    es = etiquetas(_recta(30, lon0=-88.0), False, BBOX)
    assert len(es) == 2
    assert abs(es[0][1] - es[1][1]) > 5


def test_el_borde_de_25_grados_todavia_lleva_una():
    assert len(etiquetas(_recta(25, lon0=-85.0), False, BBOX)) == 1


def test_ninguna_etiqueta_queda_a_menos_de_1_5_grados_del_borde():
    linea = np.array([[-37.0, -90.0], [-37.0, -60.0]])  # starts on the west edge
    for lat, lon in etiquetas(linea, False, BBOX):
        assert lon >= -90 + 1.5 and lon <= -30 - 1.5
        assert lat >= -62 + 1.5 and lat <= -12 - 1.5


def test_una_curva_larga_pegada_al_borde_no_lleva_etiqueta():
    pegada = np.array([[-61.5, -90.0], [-61.5, -60.0]])  # all of it within 1.5 degrees of the south edge
    assert etiquetas(pegada, False, BBOX) == []


def test_un_anillo_se_etiqueta_sobre_su_perimetro():
    t = np.linspace(0, 2 * np.pi, 200, endpoint=False)
    anillo = np.column_stack([-37 + np.sin(t) * 4, -60 + np.cos(t) * 4])  # perimeter ~25
    es = etiquetas(anillo, True, BBOX)
    assert len(es) == 2  # perimeter ~25.1 degrees, just over the 25 that brings the second label
    for lat, lon in es:
        assert np.hypot(lat + 37, lon + 60) == pytest.approx(4, abs=0.1)


def test_curvacruda_es_un_valor_simple():
    c = CurvaCruda(p=1016, cerrada=False, puntos=np.zeros((2, 2)))
    assert c.p == 1016 and not c.cerrada


def test_los_puntos_de_borde_no_se_salen_de_la_grilla_ni_por_un_ulp():
    """contourpy interpolates on the edge; an inexact grid (linspace) must not leave points 1 ulp outside."""
    lat = np.linspace(-62.0, -12.0, 201)
    lon = np.linspace(-90.0, -30.0, 241)
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    for c in trazar(Campo(lat, lon, 1000.3 + 0.37 * (la + 62.0) + 0.011 * (lo + 90.0)), 4):
        assert c.puntos[:, 0].min() >= lat[0] and c.puntos[:, 0].max() <= lat[-1]
        assert c.puntos[:, 1].min() >= lon[0] and c.puntos[:, 1].max() <= lon[-1]


def test_un_anillo_simplificado_respeta_la_tolerancia_en_todo_el_perimetro():
    t = np.linspace(0, 2 * np.pi, 600, endpoint=False)
    anillo = np.column_stack([np.sin(t) * 5, np.cos(t) * 5])
    simple = simplificar(anillo, 0.03, cerrada=True)
    cerrado = np.vstack([simple, simple[:1]])
    for p in anillo:
        assert min(_dist_segmento(p, cerrado[i], cerrado[i + 1]) for i in range(len(cerrado) - 1)) <= 0.03 + 1e-9


def test_si_los_tercios_de_una_horquilla_quedan_a_menos_de_2_grados_se_busca_otro_lugar():
    """A >25 degree line folded so the 1/3 and 2/3 spots are close: the second label moves, never overlaps."""
    horquilla = np.array([[-37.0, -80.0], [-37.0, -62.0], [-36.0, -62.0], [-36.0, -80.0], [-35.0, -80.0], [-35.0, -62.0]])
    es = etiquetas(horquilla, False, BBOX)
    assert 1 <= len(es) <= 2
    if len(es) == 2:
        assert np.hypot(es[0][0] - es[1][0], es[0][1] - es[1][1]) >= 2.0
