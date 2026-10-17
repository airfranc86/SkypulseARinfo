"""El glosario de Mora (asistente 2d-4): 22 términos con una definición corta, como dato estático del backend.

El enrutador decide QUÉ términos sabe explicar (`TERMINOS_GLOSARIO`); la hoja filtra por los que pidió la pregunta; acá se prueba
que el dato existe, que cada definición cabe en la hoja y pasa el verificador, que `FuentesDeCache` lo entrega sin tocar la red
y que no diverge del glosario de nubes del frontend (`apps/frontend/src/data/clouds.ts`).
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.asistente import fuentes_cache
from app.services.asistente.enrutador import TERMINOS_GLOSARIO, enrutar, normalizar
from app.services.asistente.fuentes_cache import FuentesDeCache
from app.services.asistente.glosario import GLOSARIO
from app.services.asistente.hoja_datos import Ruta, armar_hoja
from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.verificador import verificar
from tests.asistente import escenarios as esc

AHORA = esc.AHORA
LAT, LON = -31.4, -64.2
RAIZ = Path(__file__).resolve().parents[4]  # la raíz del repo: tests/asistente -> tests -> backend -> apps -> raíz
CLOUDS_TS = RAIZ / "apps" / "frontend" / "src" / "data" / "clouds.ts"

# Cada nube del frontend (su `id` en clouds.ts) y el término del glosario que la explica.
NUBES_DEL_FRONTEND = {
    "cirros": "cirro",
    "cirrostratos": "cirrostrato",
    "cirrocumulos": "cirrocumulo",
    "altocumulos": "altocumulo",
    "altostratos": "altoestrato",
    "estrato": "estrato",
    "estratocumulos": "estratocumulo",
    "nimboestrato": "nimboestrato",
    "cumulo": "cumulo",
    "cumulonimbo": "cumulonimbo",
    "lenticular": "lenticular",
    "mammatus": "mammatus",
    "niebla": "niebla",
}


# ---------------------------------------------------------------------------
# El dato
# ---------------------------------------------------------------------------


def test_el_glosario_tiene_exactamente_los_terminos_que_el_enrutador_sabe_pedir() -> None:
    assert set(GLOSARIO) == set(TERMINOS_GLOSARIO)
    assert len(GLOSARIO) == 22


def test_las_claves_estan_normalizadas_como_las_busca_la_hoja() -> None:
    assert all(clave == normalizar(clave) and " " not in clave for clave in GLOSARIO)


def test_el_glosario_no_se_puede_modificar_desde_afuera() -> None:
    with pytest.raises(TypeError):
        GLOSARIO["cirro"] = "otra cosa"  # type: ignore[index]


@pytest.mark.parametrize("termino", sorted(TERMINOS_GLOSARIO))
def test_cada_definicion_es_una_oracion_corta_y_limpia(termino: str) -> None:
    d = GLOSARIO[termino]
    assert 30 <= len(d) <= 200, len(d)  # cabe entera en la hoja (`_limpiar(.., 200)`): nunca se corta a la mitad
    assert d == " ".join(d.split()) and d.endswith(".")  # una sola línea, termina en punto
    assert not re.search(r"\d", d), "sin cifras: el verificador las coteja contra los datos de la hoja"
    assert not re.search(r"[*_`#<>\[\]{}|\\]|https?://|www\.", d), "sin Markdown ni enlaces"
    assert not re.search(r"\b(?:evacu|emergenc|alarm)\w*", normalizar(d)), "sin alarmismo"
    assert not re.search(r"\b(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\s+\w+", normalizar(d)), "sin números en letras"
    assert not re.search(r"groq|llama|openai|gemini|claude|mixtral|cloudflare", normalizar(d)), "sin proveedores"


# ---------------------------------------------------------------------------
# En la hoja y en el verificador
# ---------------------------------------------------------------------------


def _hoja(*terminos: str):
    f = replace(esc.templado(), glosario=GLOSARIO)
    return armar_hoja(Ruta(bloques=("glosario",), terminos=terminos), f, AHORA)


@pytest.mark.parametrize("termino", sorted(TERMINOS_GLOSARIO))
def test_la_hoja_trae_cada_definicion_completa(termino: str) -> None:
    assert _hoja(termino).datos["glosario"] == [{"termino": termino, "definicion": GLOSARIO[termino]}]


@pytest.mark.parametrize("termino", sorted(TERMINOS_GLOSARIO))
async def test_la_respuesta_con_cada_definicion_pasa_el_verificador(termino: str) -> None:
    hoja = _hoja(termino)
    texto = await ModeloFalso().generar("x", hoja)
    v = verificar(texto, hoja)
    assert v.ok, (termino, texto, v.motivos)
    assert GLOSARIO[termino][:40] in texto  # la respuesta dice la definición, no otra cosa


def test_las_dos_definiciones_que_cabe_la_hoja_entran_juntas_en_la_respuesta() -> None:
    hoja = _hoja("cumulonimbo", "virga")
    assert [e["termino"] for e in hoja.datos["glosario"]] == ["cumulonimbo", "virga"]


# ---------------------------------------------------------------------------
# FuentesDeCache: sin red
# ---------------------------------------------------------------------------


@pytest.fixture
def sin_cache(monkeypatch):
    """Si el glosario mirara alguna caché de Open-Meteo o del SMN, esto lo grita: es un dato estático."""

    def prohibido(*_a, **_k):
        raise AssertionError("el glosario no necesita ninguna caché")

    for nombre in ("peek_hourly_forecast_ext", "peek_hourly_forecast_ecmwf", "peek_current", "peek_smn_alertas"):
        monkeypatch.setattr(fuentes_cache, nombre, prohibido)


async def test_pedir_el_glosario_lo_entrega_sin_tocar_ninguna_cache(sin_cache) -> None:
    f = await FuentesDeCache().obtener(("glosario",), lat=LAT, lon=LON, ahora_utc=datetime.now(timezone.utc))
    assert dict(f.glosario) == dict(GLOSARIO)


async def test_sin_pedir_el_glosario_la_hoja_no_lo_carga() -> None:
    f = await FuentesDeCache().obtener(("avisos",), lat=LAT, lon=LON, ahora_utc=datetime.now(timezone.utc))
    assert not f.glosario


async def test_de_la_pregunta_a_la_definicion_con_las_fuentes_reales(sin_cache) -> None:
    ruta = enrutar("¿Qué es una virga?")
    assert ruta.bloques == ("glosario",) and ruta.terminos == ("virga",)
    f = await FuentesDeCache().obtener(ruta.bloques, lat=LAT, lon=LON, ahora_utc=datetime.now(timezone.utc))
    hoja = armar_hoja(ruta, f, AHORA)
    assert hoja.datos["glosario"] == [{"termino": "virga", "definicion": GLOSARIO["virga"]}]
    texto = await ModeloFalso().generar("x", hoja)
    assert verificar(texto, hoja).ok


# ---------------------------------------------------------------------------
# No diverge del frontend
# ---------------------------------------------------------------------------


def _ids_de_nubes_del_frontend() -> list[str]:
    fuente = CLOUDS_TS.read_text(encoding="utf-8")
    inicio = fuente.index("export const CLOUDS")
    return re.findall(r"^\s{4}id: '([a-z]+)',", fuente[inicio:], flags=re.MULTILINE)


@pytest.mark.skipif(not CLOUDS_TS.exists(), reason="el backend corre sin el frontend al lado")
def test_cada_nube_del_frontend_tiene_su_definicion_en_el_backend() -> None:
    ids = _ids_de_nubes_del_frontend()
    assert len(ids) == len(NUBES_DEL_FRONTEND), ids  # una nube nueva en clouds.ts: agregarla acá y al glosario
    for nube in ids:
        assert nube in NUBES_DEL_FRONTEND, f"clouds.ts tiene '{nube}' y el glosario del asistente no la explica"
        assert NUBES_DEL_FRONTEND[nube] in GLOSARIO


def test_la_tabla_de_nubes_apunta_solo_a_terminos_que_existen() -> None:
    assert set(NUBES_DEL_FRONTEND.values()) <= set(GLOSARIO)
