"""The cities drawn on the map: picked from Natural Earth populated places and written as a TypeScript module."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from isobaras_core.ciudades import (
    CAJA,
    URL_FUENTE,
    a_typescript,
    elegir_ciudades,
    main,
    nivel_de,
)


def _lugar(nombre, pais, lat, lon, pob, clase="Populated place"):
    return {
        "type": "Feature",
        "properties": {"name": nombre, "adm0name": pais, "pop_max": pob, "featurecla": clase},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


# ── nivel_de ─────────────────────────────────────────────────────────────────


def test_una_capital_nacional_es_de_nivel_1_aunque_sea_chica():
    assert nivel_de("UY", "Admin-0 capital", 40_000) == 1
    assert nivel_de("BO", "Admin-0 capital alt", 300_000) == 1


def test_una_ciudad_de_mas_de_millon_y_medio_es_de_nivel_1():
    assert nivel_de("AR", "Populated place", 1_500_000) == 1
    assert nivel_de("AR", "Populated place", 1_499_999) == 2  # >= 500 000
    assert nivel_de("BR", "Populated place", 5_000_000) == 1
    assert nivel_de("BR", "Populated place", 2_999_999) == 2  # Brazil asks for 3 000 000


def test_una_capital_de_provincia_o_de_medio_millon_es_de_nivel_2():
    assert nivel_de("AR", "Admin-1 capital", 80_000) == 2
    assert nivel_de("AR", "Populated place", 500_000) == 2
    assert nivel_de("CL", "Populated place", 499_999) == 3


def test_una_capital_de_provincia_muy_chica_solo_se_ve_con_zoom():
    assert nivel_de("AR", "Admin-1 capital", 50_000) == 2
    assert nivel_de("PY", "Admin-1 capital", 49_999) == 3
    assert nivel_de("PY", "Admin-1 capital", 5_000) == 3  # Pozo Colorado: still drawn, but only zoomed in


def test_las_ciudades_medianas_son_de_nivel_3():
    assert nivel_de("CL", "Populated place", 150_000) == 3
    assert nivel_de("CL", "Populated place", 149_999) is None


def test_argentina_baja_el_piso_a_cien_mil_para_que_entren_las_ciudades_grandes_de_la_patagonia():
    assert nivel_de("AR", "Populated place", 140_000) == 3  # Comodoro Rivadavia
    assert nivel_de("AR", "Populated place", 100_000) == 3
    assert nivel_de("AR", "Populated place", 99_999) is None


def test_brasil_pide_mas_gente_en_los_tres_niveles_para_no_llenar_el_mapa_de_suburbios():
    assert nivel_de("BR", "Populated place", 1_500_000) == 2
    assert nivel_de("BR", "Populated place", 1_499_999) == 3
    assert nivel_de("BR", "Populated place", 700_000) == 3
    assert nivel_de("BR", "Populated place", 699_999) is None
    # A province capital still counts, however small, and a national capital is always level 1.
    assert nivel_de("BR", "Admin-1 capital", 400_000) == 2
    assert nivel_de("BR", "Admin-0 capital", 400_000) == 1


def test_un_pais_que_no_esta_en_la_lista_no_tiene_nivel():
    assert nivel_de("PE", "Admin-0 capital", 9_000_000) is None


# ── elegir_ciudades ──────────────────────────────────────────────────────────


def test_solo_entran_los_seis_paises_y_la_zona_de_los_datos():
    candidatas = [
        _lugar("Rosario", "Argentina", -32.96, -60.69, 1_203_000),
        _lugar("Lima", "Peru", -12.05, -77.04, 9_000_000, "Admin-0 capital"),  # other country
        _lugar("Quito", "Ecuador", -0.2, -78.5, 1_800_000, "Admin-0 capital"),  # other country, out of the box
        _lugar("Salvador", "Brazil", -12.97, -38.48, 3_484_000, "Admin-1 capital"),
        _lugar("Natal", "Brazil", -5.8, -35.2, 800_000, "Admin-1 capital"),  # north of the box
        _lugar("Ushuaia", "Argentina", -54.8, -68.3, 57_000, "Admin-1 capital"),
    ]
    nombres = {c["nombre"] for c in elegir_ciudades(candidatas)}
    assert nombres == {"Rosario", "Salvador", "Ushuaia"}


def test_la_zona_es_la_de_las_isobaras():
    assert CAJA == (-62.0, -90.0, -12.0, -30.0)  # lat_min, lon_min, lat_max, lon_max


def test_un_suburbio_pegado_a_una_ciudad_mas_grande_se_descarta():
    candidatas = [
        _lugar("São Paulo", "Brazil", -23.56, -46.63, 18_845_000, "Admin-1 capital"),
        _lugar("Santo André", "Brazil", -23.65, -46.53, 1_700_000),  # 0.13 deg away: same urban area
        _lugar("Curitiba", "Brazil", -25.42, -49.32, 3_084_000, "Admin-1 capital"),  # 3 deg away: kept
    ]
    assert [c["nombre"] for c in elegir_ciudades(candidatas)] == ["São Paulo", "Curitiba"]


def test_una_capital_nacional_no_se_descarta_por_estar_cerca_de_otra_ciudad():
    candidatas = [
        _lugar("Gran Ciudad", "Chile", -33.0, -71.0, 9_000_000),
        _lugar("Capital Vecina", "Chile", -33.2, -71.2, 100_000, "Admin-0 capital"),
    ]
    assert {c["nombre"] for c in elegir_ciudades(candidatas)} == {"Gran Ciudad", "Capital Vecina"}


def test_las_capitales_de_provincia_gemelas_se_conservan_las_dos():
    # Corrientes is 0.16 degrees from Resistencia and Parana 0.2 from Santa Fe: neighbours, but each a capital.
    candidatas = [
        _lugar("Resistencia", "Argentina", -27.46, -58.99, 387_000, "Admin-1 capital"),
        _lugar("Corrientes", "Argentina", -27.47, -58.83, 341_000, "Admin-1 capital"),
        _lugar("Barranqueras", "Argentina", -27.49, -58.93, 60_000),  # not a capital and below the floor anyway
        _lugar("Fontana", "Argentina", -27.42, -59.03, 250_000),  # a plain neighbour of Resistencia: dropped
    ]
    assert [c["nombre"] for c in elegir_ciudades(candidatas)] == ["Resistencia", "Corrientes"]


def test_dos_ciudades_con_el_mismo_nombre_en_paises_distintos_llevan_el_pais_entre_parentesis():
    candidatas = [
        _lugar("Concepción", "Chile", -36.83, -73.05, 889_000, "Admin-1 capital"),
        _lugar("Concepción", "Paraguay", -23.4, -57.43, 80_000, "Admin-1 capital"),
        _lugar("Rosario", "Argentina", -32.96, -60.69, 1_203_000),
    ]
    assert [c["nombre"] for c in elegir_ciudades(candidatas)] == ["Rosario", "Concepción (CL)", "Concepción (PY)"]


def test_las_correcciones_a_la_fuente_se_aplican():
    candidatas = [
        _lugar("Capitan Pablo Lagerenza", "Paraguay", -20.0, -60.0, 1_200, "Admin-1 capital"),  # abolished department
        _lugar("Guaira", "Brazil", -24.08, -54.25, 36_000, "Admin-1 capital"),
        _lugar("San Nicolas", "Argentina", -33.33, -60.21, 127_742),
        _lugar("Coihaique", "Chile", -45.57, -72.07, 50_000, "Admin-1 capital"),
        _lugar("Posadas", "Argentina", -27.37, -55.9, 357_119, "Admin-1 capital"),
    ]
    assert sorted(c["nombre"] for c in elegir_ciudades(candidatas)) == ["Coyhaique", "Posadas", "San Nicolás"]


def test_las_islas_malvinas_no_se_dibujan_como_ciudad_de_ningun_pais():
    # Natural Earth files Stanley under the United Kingdom: no country of the list claims it, so it is left out.
    candidatas = [_lugar("Stanley", "United Kingdom", -51.7, -57.85, 2_100, "Admin-0 capital")]
    assert elegir_ciudades(candidatas) == []


def test_el_orden_es_por_poblacion_y_despues_por_nombre_y_no_cambia_entre_corridas():
    candidatas = [
        _lugar("Beta", "Argentina", -30.0, -60.0, 300_000),
        _lugar("Alfa", "Argentina", -40.0, -65.0, 300_000),
        _lugar("Gamma", "Argentina", -35.0, -58.0, 900_000),
    ]
    esperado = ["Gamma", "Alfa", "Beta"]
    assert [c["nombre"] for c in elegir_ciudades(candidatas)] == esperado
    assert [c["nombre"] for c in elegir_ciudades(list(reversed(candidatas)))] == esperado


def test_cada_ciudad_trae_nombre_pais_coordenadas_con_dos_decimales_nivel_y_poblacion():
    (ciudad,) = elegir_ciudades([_lugar("Córdoba", "Argentina", -31.41351, -64.18105, 1_452_000, "Admin-1 capital")])
    assert ciudad == {"nombre": "Córdoba", "pais": "AR", "lat": -31.41, "lon": -64.18, "nivel": 2, "pob": 1_452_000}


def test_un_lugar_sin_nombre_o_sin_coordenadas_validas_se_ignora():
    candidatas = [
        _lugar("", "Argentina", -30.0, -60.0, 900_000),
        _lugar("Sin Punto", "Argentina", float("nan"), -60.0, 900_000),
        {"type": "Feature", "properties": {"name": "Sin Geometria", "adm0name": "Argentina", "pop_max": 900_000, "featurecla": "Populated place"}, "geometry": None},
        _lugar("Bien", "Argentina", -30.0, -60.0, 900_000),
    ]
    assert [c["nombre"] for c in elegir_ciudades(candidatas)] == ["Bien"]


# ── a_typescript ─────────────────────────────────────────────────────────────


def test_el_modulo_generado_avisa_que_no_se_edita_y_cita_la_fuente():
    texto = a_typescript(elegir_ciudades([_lugar("Rosario", "Argentina", -32.96, -60.69, 1_203_000)]))
    assert "generated" in texto.splitlines()[0].lower()
    assert "Natural Earth" in texto
    assert "export const CIUDADES_DEL_MAPA" in texto
    assert "{ nombre: 'Rosario', pais: 'AR', lat: -32.96, lon: -60.69, nivel: 2, pob: 1203000 }," in texto


def test_los_nombres_con_comilla_o_barra_se_escapan():
    texto = a_typescript([{"nombre": "O'Higgins \\ Sur", "pais": "CL", "lat": -34.0, "lon": -71.0, "nivel": 3, "pob": 200_000}])
    assert "nombre: 'O\\'Higgins \\\\ Sur'" in texto


# ── main ─────────────────────────────────────────────────────────────────────


def _fuente(lugares) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": lugares}).encode("utf-8")


def test_main_escribe_el_modulo_y_cuenta_por_nivel(tmp_path: Path):
    pedidos = []

    def fetch(url, rango=None, *, tope=None):
        pedidos.append((url, tope))
        return _fuente([
            _lugar("Montevideo", "Uruguay", -34.91, -56.19, 1_513_000, "Admin-0 capital"),
            _lugar("Rosario", "Argentina", -32.96, -60.69, 1_203_000),
        ])

    salida, out, err = tmp_path / "ciudades.ts", io.StringIO(), io.StringIO()
    assert main(["--salida", str(salida)], fetch=fetch, out=out, err=err) == 0
    assert pedidos == [(URL_FUENTE, pedidos[0][1])] and pedidos[0][1] is not None  # one download, with a cap
    texto = salida.read_text(encoding="utf-8")
    assert "Montevideo" in texto and "Rosario" in texto
    assert "2 ciudades" in out.getvalue()


def test_main_con_una_descarga_rota_devuelve_4_y_no_escribe_nada(tmp_path: Path):
    def fetch(url, rango=None, *, tope=None):
        return b"esto no es json"

    salida, err = tmp_path / "ciudades.ts", io.StringIO()
    assert main(["--salida", str(salida)], fetch=fetch, out=io.StringIO(), err=err) == 4
    assert not salida.exists()
    assert "no se pudo armar" in err.getvalue()


def test_un_nombre_con_salto_de_linea_o_separador_unicode_no_rompe_el_modulo():
    texto = a_typescript([{"nombre": "Dos\nLineas\u2028Y\rMas", "pais": "AR", "lat": -30.0, "lon": -60.0, "nivel": 3, "pob": 100_000}])
    assert "nombre: 'Dos\\nLineas\\u2028Y\\rMas'" in texto
    assert "\u2028" not in texto and sum(1 for linea in texto.splitlines() if "Dos" in linea) == 1


def test_main_con_una_fuente_que_no_es_una_lista_de_lugares_devuelve_4(tmp_path: Path):
    def fetch(url, rango=None, *, tope=None):
        return json.dumps({"type": "FeatureCollection", "features": {"no": "es una lista"}}).encode("utf-8")

    salida, err = tmp_path / "ciudades.ts", io.StringIO()
    assert main(["--salida", str(salida)], fetch=fetch, out=io.StringIO(), err=err) == 4
    assert not salida.exists() and "no se pudo armar" in err.getvalue()


def test_main_con_un_nombre_que_no_se_puede_codificar_devuelve_4_y_deja_intacto_el_archivo_anterior(tmp_path: Path):
    salida = tmp_path / "ciudades.ts"
    salida.write_text("anterior", encoding="utf-8")

    def fetch(url, rango=None, *, tope=None):
        return _fuente([_lugar("Roto\ud800", "Argentina", -30.0, -60.0, 900_000)])

    assert main(["--salida", str(salida)], fetch=fetch, out=io.StringIO(), err=io.StringIO()) == 4
    assert salida.read_text(encoding="utf-8") == "anterior"


def test_main_con_una_fuente_sin_ninguna_ciudad_util_devuelve_4_y_no_escribe_nada(tmp_path: Path):
    def fetch(url, rango=None, *, tope=None):
        return _fuente([_lugar("Lima", "Peru", -12.05, -77.04, 9_000_000, "Admin-0 capital")])

    salida = tmp_path / "ciudades.ts"
    assert main(["--salida", str(salida)], fetch=fetch, out=io.StringIO(), err=io.StringIO()) == 4
    assert not salida.exists()


def test_la_fuente_es_una_version_fija_de_natural_earth():
    assert "natural-earth-vector/v5.1.2/geojson/ne_10m_populated_places_simple.geojson" in URL_FUENTE
