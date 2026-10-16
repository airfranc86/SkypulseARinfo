"""Finding the H and L centers: local extremes that stand out by at least 2 hPa, away from the edge and the Andes."""

from __future__ import annotations

import numpy as np

from isobaras_core import centros as modulo_centros
from isobaras_core.centros import detectar_centros
from isobaras_core.formato import Bbox
from isobaras_core.grib import Campo

BBOX = Bbox(lon_min=-90, lat_min=-62, lon_max=-30, lat_max=-12)
# The working grid is the box plus 6 degrees of margin, like the pipeline smooths it.
LAT = np.arange(-68.0, -6.0 + 0.125, 0.25)
LON = np.arange(-96.0, -24.0 + 0.125, 0.25)
LA, LO = np.meshgrid(LAT, LON, indexing="ij")


def _gauss(centro, amplitud, s):
    return amplitud * np.exp(-((LA - centro[0]) ** 2 + (LO - centro[1]) ** 2) / (2 * s * s))


def _campo(*bultos) -> Campo:
    return Campo(LAT, LON, 1013.0 + sum(bultos, np.zeros_like(LA)))


def _terreno(alto=None, centro=(0.0, 0.0), radio=0.0) -> Campo:
    """Flat sea level, optionally with a plateau of 3000 m around `centro`."""
    m = np.zeros_like(LA)
    if alto:
        m[np.hypot(LA - centro[0], LO - centro[1]) <= radio] = alto
    return Campo(LAT, LON, m)


def test_una_baja_gaussiana_da_exactamente_una_L_con_su_valor_y_posicion():
    centros = detectar_centros(_campo(_gauss((-50.0, -60.0), -25.0, 4.0)), _terreno(), BBOX)
    assert len(centros) == 1
    c = centros[0]
    assert c.t == "L"
    assert c.p == 988
    assert abs(c.lat - -50.0) <= 0.25 and abs(c.lon - -60.0) <= 0.25


def test_un_alto_y_una_baja_dan_una_H_y_una_L():
    campo = _campo(_gauss((-30.0, -50.0), 20.0, 4.0), _gauss((-52.0, -75.0), -22.0, 4.0))
    centros = detectar_centros(campo, _terreno(), BBOX)
    assert [(c.t, c.p) for c in centros] == [("H", 1033), ("L", 991)]


def test_un_campo_plano_no_tiene_centros():
    assert detectar_centros(_campo(), _terreno(), BBOX) == []


def test_un_alto_sobre_terreno_de_mas_de_1500_m_se_descarta():
    campo = _campo(_gauss((-30.0, -72.0), 20.0, 4.0))
    sobre_los_andes = _terreno(alto=3000.0, centro=(-30.0, -72.0), radio=2.0)
    assert detectar_centros(campo, sobre_los_andes, BBOX) == []
    assert len(detectar_centros(campo, _terreno(), BBOX)) == 1


def test_un_alto_sobre_terreno_justo_en_1500_m_se_conserva():
    campo = _campo(_gauss((-30.0, -72.0), 20.0, 4.0))
    justo = _terreno(alto=1500.0, centro=(-30.0, -72.0), radio=2.0)
    assert len(detectar_centros(campo, justo, BBOX)) == 1


def test_un_alto_ancho_y_suave_se_conserva_porque_baja_mas_de_2_hpa_antes_de_tocar_algo_mas_fuerte():
    """A broad 6 hPa high is nearly flat inside a 21-cell window, but it stands out by 6 hPa overall."""
    centros = detectar_centros(_campo(_gauss((-37.0, -60.0), 6.0, 15.0)), _terreno(), BBOX)
    assert [c.t for c in centros] == ["H"]


def test_un_bulto_de_menos_de_2_hpa_se_descarta():
    assert detectar_centros(_campo(_gauss((-37.0, -60.0), 1.5, 4.0)), _terreno(), BBOX) == []


def test_un_extremo_a_menos_de_1_grado_del_borde_se_descarta_y_a_mas_de_1_grado_se_conserva():
    pegado = _campo(_gauss((-12.5, -60.0), 20.0, 4.0))
    assert [c for c in detectar_centros(pegado, _terreno(), BBOX) if c.lat >= -13] == []
    lejos = _campo(_gauss((-14.0, -60.0), 20.0, 4.0))
    assert len(detectar_centros(lejos, _terreno(), BBOX)) == 1


def test_un_alto_unido_a_otro_mas_fuerte_por_una_cresta_a_1_hpa_no_se_destaca():
    """Two peaks 12 degrees apart joined by a ridge only 1 hPa below the weaker one: its prominence is 1 < 2."""
    fuerte = _gauss((-35.0, -70.0), 20.0, 2.0)
    debil = _gauss((-35.0, -58.0), 15.0, 2.0)
    cresta = np.where((LO >= -70.0) & (LO <= -58.0), 14.0 * np.exp(-((LA + 35.0) ** 2) / 18.0), 0.0)
    centros = detectar_centros(_campo(np.maximum.reduce([fuerte, debil, cresta])), _terreno(), BBOX)
    assert [(c.t, c.lon) for c in centros] == [("H", -70.0)]


def test_el_mismo_par_de_altos_con_una_cresta_mas_baja_conserva_los_dos():
    fuerte = _gauss((-35.0, -70.0), 20.0, 2.0)
    debil = _gauss((-35.0, -58.0), 15.0, 2.0)
    cresta = np.where((LO >= -70.0) & (LO <= -58.0), 10.0 * np.exp(-((LA + 35.0) ** 2) / 18.0), 0.0)
    centros = detectar_centros(_campo(np.maximum.reduce([fuerte, debil, cresta])), _terreno(), BBOX)
    assert sorted(c.lon for c in centros) == [-70.0, -58.0]


def test_dos_altos_bien_separados_se_conservan_los_dos():
    campo = _campo(_gauss((-30.0, -78.0), 18.0, 3.0), _gauss((-45.0, -42.0), 16.0, 3.0))
    assert len([c for c in detectar_centros(campo, _terreno(), BBOX) if c.t == "H"]) == 2


def test_las_H_van_primero_de_mayor_a_menor_y_despues_las_L_de_menor_a_mayor():
    campo = _campo(
        _gauss((-30.0, -78.0), 18.0, 3.0),
        _gauss((-45.0, -42.0), 25.0, 3.0),
        _gauss((-55.0, -80.0), -20.0, 3.0),
        _gauss((-25.0, -45.0), -30.0, 3.0),
    )
    resumen = [(c.t, c.p) for c in detectar_centros(campo, _terreno(), BBOX)]
    ps = [p for t, p in resumen]
    assert [t for t, _ in resumen] == ["H", "H", "L", "L"]
    assert ps[0] > ps[1] and ps[2] < ps[3]


def test_una_meseta_de_valores_iguales_da_un_solo_centro():
    plano = np.zeros_like(LA)
    plano[(np.abs(LA - -37.0) <= 1.0) & (np.abs(LO - -60.0) <= 1.0)] = 10.0  # flat-topped bump, many equal cells
    centros = detectar_centros(Campo(LAT, LON, 1013.0 + plano), _terreno(), BBOX)
    assert len(centros) == 1


def test_no_se_pasan_de_30_centros():
    bultos = [
        _gauss((la, lo), 10.0 if (i + j) % 2 else -10.0, 0.8)
        for i, la in enumerate(np.arange(-60.0, -13.0, 4.0))
        for j, lo in enumerate(np.arange(-88.0, -31.0, 4.0))
    ]
    assert len(detectar_centros(_campo(*bultos), _terreno(), BBOX)) <= 30


# ── Los umbrales exactos (cada uno acotado de los dos lados) ──────────────────


def test_la_prominencia_minima_queda_entre_1_8_y_2_5_hpa():
    assert detectar_centros(_campo(_gauss((-37.0, -60.0), 1.8, 4.0)), _terreno(), BBOX) == []
    assert len(detectar_centros(_campo(_gauss((-37.0, -60.0), 2.5, 4.0)), _terreno(), BBOX)) == 1


def test_la_altura_maxima_queda_entre_1500_y_2000_m():
    campo = _campo(_gauss((-30.0, -72.0), 20.0, 4.0))
    assert len(detectar_centros(campo, _terreno(alto=1499.0, centro=(-30.0, -72.0), radio=2.0), BBOX)) == 1
    assert detectar_centros(campo, _terreno(alto=2000.0, centro=(-30.0, -72.0), radio=2.0), BBOX) == []


def test_el_margen_del_borde_queda_entre_0_8_y_1_5_grados_en_los_cuatro_lados():
    # (lat, lon) of a high 0.8 degrees inside each edge (discarded) and 1.5 degrees inside (kept)
    casos = [
        ((-12.8, -60.0), (-13.5, -60.0)),  # north
        ((-61.2, -60.0), (-60.5, -60.0)),  # south
        ((-37.0, -89.2), (-37.0, -88.5)),  # west
        ((-37.0, -30.8), (-37.0, -31.5)),  # east
    ]
    for pegado, adentro in casos:
        assert detectar_centros(_campo(_gauss(pegado, 20.0, 4.0)), _terreno(), BBOX) == [], pegado
        assert len(detectar_centros(_campo(_gauss(adentro, 20.0, 4.0)), _terreno(), BBOX)) == 1, adentro


def test_dos_altos_a_3_5_grados_se_cuentan_por_separado_si_cada_uno_es_su_propio_maximo():
    campo = _campo(_gauss((-37.0, -60.0), 20.0, 0.8), _gauss((-37.0, -56.5), 10.0, 0.8))
    assert sorted(c.lon for c in detectar_centros(campo, _terreno(), BBOX)) == [-60.0, -56.5]


def test_dos_celdas_iguales_en_diagonal_son_un_solo_centro():
    plano = np.zeros_like(LA)
    i, j = int(np.abs(LAT - -37.0).argmin()), int(np.abs(LON - -60.0).argmin())
    plano[i, j] = plano[i + 1, j + 1] = 17.0  # a tie that touches only at a corner
    suave = Campo(LAT, LON, 1013.0 + plano)
    assert len(detectar_centros(suave, _terreno(), BBOX)) == 1


def test_el_tope_deja_los_30_centros_mas_alejados_de_1013(monkeypatch):
    bultos = []
    k = 0
    for la in np.arange(-60.0, -13.0, 4.0):
        for lo in np.arange(-88.0, -31.0, 4.0):
            k += 1
            bultos.append(_gauss((la, lo), (5.0 + k) * (1 if k % 2 else -1), 0.8))
    campo = _campo(*bultos)
    monkeypatch.setattr(modulo_centros, "MAX_CENTROS", 10_000)
    todos = detectar_centros(campo, _terreno(), BBOX)
    assert len(todos) > 30
    monkeypatch.undo()
    esperados = sorted(todos, key=lambda c: -abs(c.p - 1013.0))[:30]
    assert sorted((c.t, c.p, c.lat, c.lon) for c in detectar_centros(campo, _terreno(), BBOX)) == sorted(
        (c.t, c.p, c.lat, c.lon) for c in esperados
    )
