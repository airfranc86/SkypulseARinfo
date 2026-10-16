"""The map's own background: coastlines and borders from Natural Earth, clipped, simplified and encoded."""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest

from isobaras_core.base import (
    CAJA,
    CAPAS,
    ErrorDeBase,
    codificar_base,
    leer_lineas_geojson,
    main,
    recortar_linea,
)

# A small box makes the cases easy to read: lat 0..10, lon 0..10.
CAJA_CHICA = (0.0, 0.0, 10.0, 10.0)  # lat_min, lon_min, lat_max, lon_max


def _lineas(res):
    return [r.tolist() for r in res]


# ── recortar_linea ───────────────────────────────────────────────────────────


def test_una_linea_toda_adentro_queda_igual():
    linea = np.array([[2.0, 2.0], [3.0, 5.0], [8.0, 8.0]])
    assert _lineas(recortar_linea(linea, CAJA_CHICA)) == [linea.tolist()]


def test_una_linea_toda_afuera_desaparece():
    assert recortar_linea(np.array([[20.0, 20.0], [30.0, 30.0]]), CAJA_CHICA) == []


def test_una_linea_que_sale_se_corta_en_el_borde():
    linea = np.array([[5.0, 5.0], [5.0, 15.0]])  # goes east out of the box
    assert _lineas(recortar_linea(linea, CAJA_CHICA)) == [[[5.0, 5.0], [5.0, 10.0]]]


def test_una_linea_que_entra_se_corta_en_el_borde():
    linea = np.array([[5.0, -5.0], [5.0, 5.0]])
    assert _lineas(recortar_linea(linea, CAJA_CHICA)) == [[[5.0, 0.0], [5.0, 5.0]]]


def test_una_linea_que_cruza_toda_la_caja_queda_de_borde_a_borde():
    linea = np.array([[5.0, -5.0], [5.0, 15.0]])
    assert _lineas(recortar_linea(linea, CAJA_CHICA)) == [[[5.0, 0.0], [5.0, 10.0]]]


def test_una_linea_que_sale_y_vuelve_a_entrar_da_dos_tramos():
    linea = np.array([[5.0, 5.0], [5.0, 15.0], [8.0, 15.0], [8.0, 5.0]])
    tramos = _lineas(recortar_linea(linea, CAJA_CHICA))
    assert tramos == [[[5.0, 5.0], [5.0, 10.0]], [[8.0, 10.0], [8.0, 5.0]]]


def test_una_diagonal_que_roza_una_esquina_por_afuera_no_deja_tramo():
    assert recortar_linea(np.array([[-1.0, 9.0], [1.0, 11.0]]), CAJA_CHICA) == []


def test_un_punto_suelto_o_una_linea_vacia_no_dan_tramos():
    assert recortar_linea(np.array([[5.0, 5.0]]), CAJA_CHICA) == []
    assert recortar_linea(np.zeros((0, 2)), CAJA_CHICA) == []


def test_la_caja_del_pipeline_cubre_el_recorte_de_las_isobaras_mas_el_margen_del_mapa():
    lat_min, lon_min, lat_max, lon_max = CAJA
    assert lat_min <= -62 - 10 and lat_max >= -12 + 10
    assert lon_min <= -90 - 10 and lon_max >= -30 + 10


# ── leer_lineas_geojson ──────────────────────────────────────────────────────


def _geojson(*geometrias) -> dict:
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": g} for g in geometrias]}


def test_el_geojson_se_lee_como_lineas_de_lat_lon():
    datos = _geojson(
        {"type": "LineString", "coordinates": [[-60.0, -30.0], [-61.0, -31.0]]},
        {"type": "MultiLineString", "coordinates": [[[-70.0, -40.0], [-71.0, -41.0]], [[-50.0, -20.0], [-51.0, -21.0]]]},
    )
    lineas = leer_lineas_geojson(datos)
    assert [l.tolist() for l in lineas] == [
        [[-30.0, -60.0], [-31.0, -61.0]],  # the file has [lon, lat]; we want [lat, lon]
        [[-40.0, -70.0], [-41.0, -71.0]],
        [[-20.0, -50.0], [-21.0, -51.0]],
    ]


def test_el_geojson_ignora_lo_que_no_es_una_linea():
    datos = _geojson({"type": "Point", "coordinates": [0, 0]}, {"type": "LineString", "coordinates": [[1, 2], [3, 4]]})
    assert len(leer_lineas_geojson(datos)) == 1


@pytest.mark.parametrize("malo", [None, [], {}, {"features": "x"}, {"features": [{"geometry": {"type": "LineString", "coordinates": [["a", "b"], [1, 2]]}}]}])
def test_un_geojson_roto_se_rechaza(malo):
    with pytest.raises(ErrorDeBase):
        leer_lineas_geojson(malo)


# ── codificar_base ───────────────────────────────────────────────────────────


def test_la_base_se_codifica_con_diferencias_en_centesimas_de_grado():
    base = codificar_base(
        costas=[np.array([[-30.0, -60.0], [-30.5, -60.25], [-31.0, -60.5]])],
        paises=[],
        provincias=[np.array([[-40.0, -70.0], [-40.0, -69.0]])],
    )
    assert base["v"] == 1
    assert base["scale"] == 100
    assert base["fuente"] == "Natural Earth"
    assert base["caja"] == [CAJA[1], CAJA[0], CAJA[3], CAJA[2]]
    assert base["costas"] == [[-3000, -6000, -50, -25, -50, -25]]
    assert base["paises"] == []
    assert base["provincias"] == [[-4000, -7000, 0, 100]]


def test_una_linea_con_menos_de_dos_puntos_distintos_se_descarta():
    base = codificar_base(costas=[np.array([[1.0, 1.0], [1.001, 1.001]])], paises=[], provincias=[])
    assert base["costas"] == []


# ── main (con red falsa) ─────────────────────────────────────────────────────


COSTA = _geojson({"type": "LineString", "coordinates": [[-60.0, -30.0], [-60.0, -40.0], [-60.0, -150.0]]})
PAISES = _geojson({"type": "LineString", "coordinates": [[-65.0, -30.0], [-65.0, -45.0]]})
PROVINCIAS = _geojson({"type": "MultiLineString", "coordinates": [[[-68.0, -35.0], [-66.0, -36.0]], [[0.0, 80.0], [1.0, 81.0]]]})


class RedFalsa:
    def __init__(self):
        self.pedidos: list[str] = []
        self.topes: list[int | None] = []

    def fetch(self, url: str, rango=None, *, tope=None) -> bytes:
        self.pedidos.append(url)
        self.topes.append(tope)
        if "coastline" in url:
            return json.dumps(COSTA).encode()
        if "boundary_lines_land" in url:
            return json.dumps(PAISES).encode()
        if "states_provinces_lines" in url:
            return json.dumps(PROVINCIAS).encode()
        raise OSError("404")


def _correr(tmp_path: Path, red: RedFalsa | None = None, *extra: str):
    salida = tmp_path / "mapa" / "base.json"
    out, err = io.StringIO(), io.StringIO()
    codigo = main(["--salida", str(salida), *extra], fetch=(red or RedFalsa()).fetch, out=out, err=err)
    return codigo, salida, out.getvalue(), err.getvalue()


def test_main_baja_las_tres_capas_y_escribe_la_base_ya_recortada(tmp_path):
    red = RedFalsa()
    codigo, salida, texto, errores = _correr(tmp_path, red)
    assert codigo == 0, errores
    assert len(red.pedidos) == 3
    assert all(u.startswith("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/") for u in red.pedidos)
    # provinces come from the 10m file: the 50m one only has the provinces of a handful of countries (not Argentina)
    assert any("ne_10m_admin_1_states_provinces_lines" in u for u in red.pedidos)
    assert all(t is not None and t >= 25_000_000 for u, t in zip(red.pedidos, red.topes) if "ne_10m_admin_1" in u)
    base = json.loads(salida.read_text(encoding="utf-8"))
    assert base["v"] == 1 and len(base["costas"]) == 1 and len(base["paises"]) == 1
    assert len(base["provincias"]) == 1  # the far-away province line (80 N) is gone
    assert "líneas" in texto


def test_la_costa_que_se_sale_de_la_caja_queda_cortada_en_el_borde(tmp_path):
    _, salida, _, _ = _correr(tmp_path)
    costa = json.loads(salida.read_text(encoding="utf-8"))["costas"][0]
    lat = costa[0]
    lon = costa[1]
    for k in range(2, len(costa), 2):
        lat += costa[k]
        lon += costa[k + 1]
    assert CAJA[1] * 100 <= lon <= CAJA[3] * 100
    assert CAJA[0] * 100 <= lat <= CAJA[2] * 100


def test_un_error_de_red_sale_en_4_y_no_escribe_nada(tmp_path):
    class Caida(RedFalsa):
        def fetch(self, url, rango=None, *, tope=None):
            raise OSError("sin conexión")

    codigo, salida, _, errores = _correr(tmp_path, Caida())
    assert codigo == 4
    assert "sin conexión" in errores
    assert not salida.exists()


def test_un_archivo_que_no_es_json_sale_en_4(tmp_path):
    class Roto(RedFalsa):
        def fetch(self, url, rango=None, *, tope=None):
            return b"<html>"

    codigo, salida, _, errores = _correr(tmp_path, Roto())
    assert codigo == 4 and not salida.exists()


def test_la_base_pesa_poco_y_se_escribe_compacta(tmp_path):
    _, salida, _, _ = _correr(tmp_path)
    texto = salida.read_text(encoding="utf-8")
    assert "\n" not in texto.strip() and ", " not in texto
    assert len(texto) < 200_000


def test_la_caja_es_exactamente_la_acordada():
    assert CAJA == (-74.0, -102.0, 0.0, -18.0)


def test_la_fuente_esta_fijada_a_una_version_de_natural_earth_y_no_a_la_rama_master():
    for url in CAPAS.values():
        assert "/natural-earth-vector/v5.1.2/geojson/" in url, url
        assert "/master/" not in url


def _con_clase(clase: str | None) -> dict:
    propiedades = {} if clase is None else {"FEATURECLA": clase}
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": propiedades, "geometry": {"type": "LineString", "coordinates": [[-60.0, -30.0], [-61.0, -31.0]]}}
        ],
    }


@pytest.mark.parametrize("clase", ["International boundary (verify)", "International boundary", "Admin-1 boundary", "Coastline", None])
def test_las_lineas_definidas_se_conservan(clase):
    assert len(leer_lineas_geojson(_con_clase(clase))) == 1


@pytest.mark.parametrize("clase", ["Indefinite (please verify)", "Disputed (please verify)", "Line of control (please verify)", "Overlay limit"])
def test_los_limites_indefinidos_o_en_disputa_no_se_dibujan_como_si_estuvieran_definidos(clase):
    """E.g. the Southern Patagonian Ice Field segment: pending demarcation, not a drawn border."""
    assert leer_lineas_geojson(_con_clase(clase)) == []
