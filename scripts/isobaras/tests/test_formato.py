"""Contract v1 of the pressure-map files, Python side.

The same fixtures are read by the frontend tests (`apps/frontend/tests/isobarasFormato.test.ts`):
what Python encodes, TypeScript decodes to the same coordinates.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from isobaras_core import formato
from isobaras_core.formato import (
    Bbox,
    Centro,
    FormatoInvalido,
    Hora,
    Linea,
    codificar_hora,
    codificar_manifest,
    leer_hora,
    leer_manifest,
)

FIXTURES = Path(__file__).resolve().parents[3] / "apps" / "frontend" / "tests" / "fixtures" / "isobaras"


def _leer(nombre: str) -> dict:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


MANIFEST_RAW = _leer("manifest.json")
HORA_RAW = _leer("f006.json")
DECODIFICADO = _leer("f006.decodificado.json")


@pytest.fixture
def manifest():
    return leer_manifest(copy.deepcopy(MANIFEST_RAW))


def _hora_con(cambio) -> dict:
    h = copy.deepcopy(HORA_RAW)
    cambio(h)
    return h


def _motivo(raw: object, manifest) -> str:
    with pytest.raises(FormatoInvalido) as e:
        leer_hora(raw, manifest)
    return e.value.motivo


# ── Manifest ─────────────────────────────────────────────────────────────────


def test_manifest_de_ejemplo_se_lee_entero(manifest):
    assert manifest.cycle == "2026-10-14T00:00Z"
    assert manifest.bbox == Bbox(lon_min=-90, lat_min=-62, lon_max=-30, lat_max=-12)
    assert manifest.interval_hpa == 4
    assert manifest.scale == 100
    assert [(h.f, h.file) for h in manifest.hours] == [
        (0, "isobaras_f000.json"),
        (3, "isobaras_f003.json"),
        (6, "isobaras_f006.json"),
    ]


def test_manifest_se_codifica_igual_que_el_de_ejemplo(manifest):
    assert codificar_manifest(manifest) == MANIFEST_RAW


def test_manifest_version_desconocida():
    with pytest.raises(FormatoInvalido) as e:
        leer_manifest({**MANIFEST_RAW, "v": 2})
    assert e.value.motivo == "version"


@pytest.mark.parametrize(
    "malo",
    [None, "x", 7, [], {}, {**MANIFEST_RAW, "hours": []}, {**MANIFEST_RAW, "bbox": [1, 2, 3]}, {**MANIFEST_RAW, "cycle": "ayer"}],
)
def test_manifest_malformado(malo):
    with pytest.raises(FormatoInvalido) as e:
        leer_manifest(malo)
    assert e.value.motivo == "formato"


@pytest.mark.parametrize("archivo", ["../secreto.json", "https://otro.sitio/x.json", "isobaras_f6.json", "otra.json"])
def test_manifest_nombre_de_archivo_no_permitido(archivo):
    horas = [{"f": 0, "valid": "2026-10-14T00:00Z", "file": archivo}]
    with pytest.raises(FormatoInvalido) as e:
        leer_manifest({**MANIFEST_RAW, "hours": horas})
    assert e.value.motivo == "formato"


def test_manifest_horas_fuera_de_orden():
    horas = [
        {"f": 3, "valid": "2026-10-14T03:00Z", "file": "isobaras_f003.json"},
        {"f": 0, "valid": "2026-10-14T00:00Z", "file": "isobaras_f000.json"},
    ]
    with pytest.raises(FormatoInvalido):
        leer_manifest({**MANIFEST_RAW, "hours": horas})


# ── Hora: decodificación y codificación ──────────────────────────────────────


def _como_plano(hora: Hora) -> dict:
    return {
        "cycle": hora.cycle,
        "f": hora.f,
        "valid": hora.valid,
        "lineas": [
            {
                "p": ln.p,
                "cerrada": ln.cerrada,
                "puntos": [[lat, lon] for lat, lon in ln.puntos],
                "etiquetas": [[lat, lon] for lat, lon in ln.etiquetas],
            }
            for ln in hora.lineas
        ],
        "centros": [{"t": c.t, "p": c.p, "lat": c.lat, "lon": c.lon} for c in hora.centros],
    }


def test_hora_de_ejemplo_se_decodifica_a_las_coordenadas_compartidas(manifest):
    assert _como_plano(leer_hora(copy.deepcopy(HORA_RAW), manifest)) == DECODIFICADO


def test_codificar_lo_decodificado_da_el_archivo_original(manifest):
    hora = leer_hora(copy.deepcopy(HORA_RAW), manifest)
    assert codificar_hora(hora, manifest.scale) == HORA_RAW


def test_codificar_una_curva_cerrada_no_repite_el_primer_punto(manifest):
    cerrada = Linea(p=1012, cerrada=True, puntos=((-39.0, -55.0), (-39.0, -53.0), (-41.0, -53.0), (-39.0, -55.0)), etiquetas=())
    hora = Hora(cycle=manifest.cycle, f=6, valid="2026-10-14T06:00Z", lineas=(cerrada,), centros=())
    c = codificar_hora(hora, manifest.scale)["lines"][0]["c"]
    assert c == [-3900, -5500, 0, 200, -200, 0]  # last point == first was dropped


def test_codificar_una_curva_abierta_conserva_todos_los_puntos(manifest):
    abierta = Linea(p=1016, cerrada=False, puntos=((-31.4, -64.18), (-31.4, -64.18)), etiquetas=())
    hora = Hora(cycle=manifest.cycle, f=6, valid="2026-10-14T06:00Z", lineas=(abierta,), centros=())
    assert codificar_hora(hora, manifest.scale)["lines"][0]["c"] == [-3140, -6418, 0, 0]


def test_codificar_redondea_al_entero_mas_cercano(manifest):
    linea = Linea(p=1016, cerrada=False, puntos=((-31.404, -64.186), (-31.396, -64.174)), etiquetas=())
    hora = Hora(cycle=manifest.cycle, f=6, valid="2026-10-14T06:00Z", lineas=(linea,), centros=(Centro("H", 1028, -38.254, -52.496),))
    codificado = codificar_hora(hora, manifest.scale)
    assert codificado["lines"][0]["c"] == [-3140, -6419, 0, 2]  # -6418.6 -> -6419, -6417.4 -> -6417
    assert codificado["centers"][0]["lat"] == -3825
    assert codificado["centers"][0]["lon"] == -5250


# ── Hora: rechazos ───────────────────────────────────────────────────────────


def test_hora_version_desconocida(manifest):
    assert _motivo(_hora_con(lambda h: h.update(v=2)), manifest) == "version"


def test_hora_c_de_largo_impar(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].pop()), manifest) == "formato"


def test_hora_c_con_menos_de_dos_puntos(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0].update(c=[-3140, -6418])), manifest) == "formato"


def test_hora_latitud_fuera_del_recorte(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].__setitem__(0, -1100)), manifest) == "fuera-de-bbox"


def test_hora_longitud_fuera_del_recorte(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].__setitem__(1, -2900)), manifest) == "fuera-de-bbox"


def test_hora_punto_que_sale_del_recorte_por_las_diferencias(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].__setitem__(2, 9000)), manifest) == "fuera-de-bbox"


def test_hora_etiqueta_o_centro_fuera_del_recorte(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0]["labels"][0].__setitem__(0, 500)), manifest) == "fuera-de-bbox"
    assert _motivo(_hora_con(lambda h: h["centers"][0].update(lon=500)), manifest) == "fuera-de-bbox"


def test_hora_p_que_no_es_entero(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0].update(p=1016.5)), manifest) == "formato"
    assert _motivo(_hora_con(lambda h: h["centers"][0].update(p="1028")), manifest) == "formato"


def test_hora_un_booleano_no_cuenta_como_entero(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0].update(p=True)), manifest) == "formato"


def test_hora_valor_de_c_que_no_es_entero(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].__setitem__(3, 1.5)), manifest) == "formato"


def test_hora_centro_que_no_es_h_ni_l(manifest):
    assert _motivo(_hora_con(lambda h: h["centers"][0].update(t="X")), manifest) == "formato"


def test_hora_scale_distinta_de_la_del_manifest(manifest):
    assert _motivo(_hora_con(lambda h: h.update(scale=10)), manifest) == "formato"


@pytest.mark.parametrize("malo", [None, "x", [], {}])
def test_hora_malformada(manifest, malo):
    assert _motivo(malo, manifest) == "formato"


def test_hora_sin_lines(manifest):
    assert _motivo(_hora_con(lambda h: h.pop("lines")), manifest) == "formato"


def test_hora_de_otro_ciclo_se_marca_ciclo_cambiado(manifest):
    assert _motivo(_hora_con(lambda h: h.update(cycle="2026-10-14T06:00Z")), manifest) == "ciclo-cambiado"


def test_los_motivos_son_los_del_contrato():
    assert formato.MOTIVOS == ("version", "formato", "fuera-de-bbox", "ciclo-cambiado")


# ── Casos compartidos con TypeScript (`rechazos.json`) ───────────────────────
# Los dos lectores tienen que aceptar y rechazar exactamente lo mismo, con el mismo motivo.

CASOS = _leer("rechazos.json")


def _aplicar(base: dict, caso: dict) -> dict:
    doc = copy.deepcopy(base)

    def alcanzar(ruta: list):
        nodo = doc
        for clave in ruta[:-1]:
            nodo = nodo[clave]
        return nodo

    for ruta, valor in caso.get("parche", []):
        alcanzar(ruta)[ruta[-1]] = valor
    for ruta in caso.get("quitar", []):
        del alcanzar(ruta)[ruta[-1]]
    return doc


def _resultado(leer) -> str:
    try:
        leer()
    except FormatoInvalido as e:
        return e.motivo
    return "ok"


@pytest.mark.parametrize("caso", CASOS["manifest"], ids=lambda c: c["nombre"])
def test_compartido_manifest(caso):
    assert _resultado(lambda: leer_manifest(_aplicar(MANIFEST_RAW, caso))) == caso["esperado"]


@pytest.mark.parametrize("caso", CASOS["hora"], ids=lambda c: c["nombre"])
def test_compartido_hora(caso, manifest):
    assert _resultado(lambda: leer_hora(_aplicar(HORA_RAW, caso), manifest)) == caso["esperado"]


# ── Entradas que solo Python puede recibir ───────────────────────────────────


def test_enteros_gigantes_se_rechazan_sin_desbordar(manifest):
    grande = int("1" + "0" * 400)
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].__setitem__(2, grande)), manifest) == "formato"
    with pytest.raises(FormatoInvalido) as e:
        leer_manifest({**MANIFEST_RAW, "bbox": [-90, -62, -30, grande]})
    assert e.value.motivo == "formato"
    with pytest.raises(FormatoInvalido) as e:
        leer_manifest({**MANIFEST_RAW, "scale": grande})
    assert e.value.motivo == "formato"


def test_nan_e_infinito_se_rechazan(manifest):
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].__setitem__(2, float("nan"))), manifest) == "formato"
    assert _motivo(_hora_con(lambda h: h["lines"][0]["c"].__setitem__(2, float("inf"))), manifest) == "formato"


# ── Topes de tamaño (el archivo viene de un host de terceros) ─────────────────


def test_tope_de_horas_en_el_manifest():
    horas = [{"f": i, "valid": "2026-10-14T00:00Z", "file": f"isobaras_f{i:03d}.json"} for i in range(130)]
    with pytest.raises(FormatoInvalido):
        leer_manifest({**MANIFEST_RAW, "hours": horas})
    assert leer_manifest({**MANIFEST_RAW, "hours": horas[:129]})


def test_topes_de_lineas_puntos_y_centros(manifest):
    def muchas_lineas(h):
        h["lines"] = [copy.deepcopy(h["lines"][0]) for _ in range(201)]

    assert _motivo(_hora_con(muchas_lineas), manifest) == "formato"
    assert _motivo(_hora_con(lambda h: h["lines"][0].update(c=[-3140, -6418] + [0] * (2 * 5000))), manifest) == "formato"
    assert leer_hora(_hora_con(lambda h: h["lines"][0].update(c=[-3140, -6418] + [0] * (2 * 4999))), manifest)
    assert _motivo(_hora_con(lambda h: h.update(centers=[copy.deepcopy(h["centers"][0]) for _ in range(31)])), manifest) == "formato"


def test_codificar_compara_despues_de_redondear_para_cerrar(manifest):
    cerrada = Linea(
        p=1012,
        cerrada=True,
        puntos=((-39.0, -55.0), (-39.0, -53.0), (-41.0, -53.0), (-39.000001, -55.000001)),
        etiquetas=(),
    )
    hora = Hora(cycle=manifest.cycle, f=6, valid="2026-10-14T06:00Z", lineas=(cerrada,), centros=())
    assert codificar_hora(hora, manifest.scale)["lines"][0]["c"] == [-3900, -5500, 0, 200, -200, 0]
