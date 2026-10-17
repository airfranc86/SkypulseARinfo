# ruff: noqa: F811  (los fixtures se importan por nombre y se usan como parámetros)
"""Asistente 2d-3b: `FuentesDeCache` entrega el METAR y el TAF decodificados SOLO con lo que está en caché.

Mismo aeropuerto y mismos límites que la tarjeta "Ahora" (el más cercano, a menos de 20 km, METAR de menos de 90 min). Del
TAF solo lo que todavía rige. Una fuente que no está en caché no se inventa. Cero red.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.asistente.enrutador import Ruta, enrutar
from app.services.asistente.fuentes_cache import FuentesDeCache
from app.services.asistente.hoja_datos import armar_hoja
from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.verificador import verificar
from app.services.reportes_aeronauticos import clear_caches, nearest_airport
from app.services.reportes_aeronauticos import taf as taf_modulo
from app.services.reportes_aeronauticos.awc_metar import metar_entries_cache
from tests.asistente.test_fuentes_cache import sin_red  # noqa: F401  (el fixture se usa por nombre)
from tests.helpers_caracterizacion_aeronautica import load_taf
from tests.openmeteo_fake_source import install  # noqa: F401

pytestmark = pytest.mark.unit

LAT, LON = -31.42, -64.19  # Córdoba: el aeropuerto SACO queda a unos 11 km
LEJOS = (-38.0, -72.5)  # sin ningún aeropuerto argentino a menos de 20 km
AHORA = datetime(2026, 10, 19, 17, 20, tzinfo=timezone.utc)
AHORA_TAF = datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc)  # el TAF de SACO del fixture rige 06/10 18Z - 07/10 18Z


@pytest.fixture(autouse=True)
def _aeronautica_limpia():
    clear_caches()
    yield
    clear_caches()


async def _sembrar_metar(hace_min: int = 20, icao: str = "SACO", **campos) -> None:
    entrada = {
        "obsTime": int((AHORA - timedelta(minutes=hace_min)).timestamp()),
        "temp": 18, "dewp": 12, "wspd": 10, "wdir": 180, "rawOb": "SACO 191700Z 18005KT 9999 FEW040 18/12 Q1015",
        **campos,
    }

    async def traer():
        return (entrada,)

    await metar_entries_cache.get_or_fetch(icao, traer)


async def _sembrar_taf(icao: str = "SACO") -> None:
    entrada = load_taf("SACO")[0]

    async def traer():
        return entrada

    await taf_modulo._taf_cache.get_or_fetch(icao, traer)


async def _fuentes(bloques, ahora=AHORA, lat=LAT, lon=LON):
    return await FuentesDeCache().obtener(tuple(bloques), lat=lat, lon=lon, ahora_utc=ahora)


# --- Sin nada en caché ----------------------------------------------------------------------------------------------------

async def test_con_las_cachés_vacías_no_hay_metar_ni_taf(sin_red):
    f = await _fuentes(["metar", "taf"])
    assert f.metar is None and f.taf is None


async def test_solo_se_arma_lo_que_se_pide(sin_red):
    await _sembrar_metar()
    await _sembrar_taf()
    solo_metar = await _fuentes(["metar"], ahora=AHORA)
    assert solo_metar.metar is not None and solo_metar.taf is None
    solo_taf = await _fuentes(["taf"], ahora=AHORA_TAF)
    assert solo_taf.taf is not None and solo_taf.metar is None


async def test_no_mira_las_series_del_dashboard_para_responder_metar_o_taf(sin_red, monkeypatch):
    await _sembrar_metar()

    def prohibido(*_a, **_k):
        raise AssertionError("el METAR no necesita la serie del dashboard, lo actual ni los avisos")

    from app.services.asistente import fuentes_cache

    for nombre in ("peek_hourly_forecast_ext", "peek_hourly_forecast_ecmwf", "peek_current", "peek_smn_alertas"):
        monkeypatch.setattr(fuentes_cache, nombre, prohibido)
    assert (await _fuentes(["metar"])).metar is not None


# --- METAR ----------------------------------------------------------------------------------------------------------------

async def test_con_un_metar_reciente_cerca_se_entrega_decodificado(sin_red):
    await _sembrar_metar(wxString="BR")
    m = (await _fuentes(["metar"])).metar
    assert m is not None and m.icao == "SACO" and m.temp_c == 18 and m.dewpoint_c == 12
    assert m.wind_dir_deg == 180 and m.wx_string == "BR"


async def test_un_metar_de_hace_mas_de_90_minutos_no_se_entrega(sin_red):
    await _sembrar_metar(hace_min=95)
    assert (await _fuentes(["metar"])).metar is None


async def test_un_metar_de_hace_justo_90_minutos_todavia_se_entrega(sin_red):
    await _sembrar_metar(hace_min=90)
    assert (await _fuentes(["metar"])).metar is not None


async def test_lejos_de_todo_aeropuerto_no_se_entrega_el_metar(sin_red):
    lat, lon = LEJOS
    await _sembrar_metar(icao=nearest_airport(lat, lon).icao)
    assert (await _fuentes(["metar"], lat=lat, lon=lon)).metar is None


# --- TAF ------------------------------------------------------------------------------------------------------------------

async def test_con_taf_en_cache_se_entrega_solo_lo_que_todavia_rige(sin_red):
    await _sembrar_taf()
    t = (await _fuentes(["taf"], ahora=AHORA_TAF)).taf
    assert t is not None and t.icao == "SACO"
    assert [p.valid_to.hour for p in t.periods] == [12, 9, 18]


async def test_un_taf_vencido_no_se_entrega(sin_red):
    await _sembrar_taf()
    assert (await _fuentes(["taf"], ahora=AHORA)).taf is None  # 19/10: el TAF del fixture terminó el 07/10


async def test_una_estacion_que_se_sabe_sin_taf_no_da_un_taf_viejo(sin_red):
    await _sembrar_taf()
    taf_modulo._no_taf_cache["SACO"] = True
    assert (await _fuentes(["taf"], ahora=AHORA_TAF)).taf is None


async def test_lejos_de_todo_aeropuerto_no_se_entrega_el_taf(sin_red):
    lat, lon = LEJOS
    await _sembrar_taf(icao=nearest_airport(lat, lon).icao)
    assert (await _fuentes(["taf"], ahora=AHORA_TAF, lat=lat, lon=lon)).taf is None


# --- En la hoja y en la respuesta -----------------------------------------------------------------------------------------

async def test_la_hoja_muestra_el_metar_y_el_taf_de_la_cache(sin_red):
    await _sembrar_metar(wxString="BR")
    await _sembrar_taf()
    ruta = Ruta(bloques=("metar", "taf"))
    f_metar = await _fuentes(["metar"], ahora=AHORA)
    f_taf = await _fuentes(["taf"], ahora=AHORA_TAF)
    hoja_metar = armar_hoja(Ruta(bloques=("metar",)), f_metar, AHORA)
    assert hoja_metar.datos["metar"]["estacion"] == "SACO" and hoja_metar.datos["metar"]["fenomeno"] == "BR"
    hoja_taf = armar_hoja(Ruta(bloques=("taf",)), f_taf, AHORA_TAF)
    assert hoja_taf.datos["taf"]["estacion"] == "SACO" and len(hoja_taf.datos["taf"]["periodos"]) == 3
    assert ruta.bloques == ("metar", "taf")


async def test_de_la_pregunta_a_la_respuesta_con_el_metar_real_pasa_el_verificador(sin_red):
    await _sembrar_metar(wxString="BR")
    ruta = enrutar("¿Cómo está el METAR del aeropuerto?")
    assert "metar" in ruta.bloques
    f = await FuentesDeCache().obtener(ruta.bloques, lat=LAT, lon=LON, ahora_utc=AHORA)
    hoja = armar_hoja(ruta, f, AHORA)
    assert hoja.datos["metar"] != {"estado": "sin_dato"}
    texto = await ModeloFalso().generar("x", hoja)
    v = verificar(texto, hoja)
    assert v.ok, (texto, v.motivos)


async def test_sin_datos_la_respuesta_dice_que_no_los_tiene(sin_red):
    ruta = Ruta(bloques=("metar", "taf"))
    hoja = armar_hoja(ruta, await _fuentes(["metar", "taf"]), AHORA)
    assert hoja.datos["metar"] == {"estado": "sin_dato"} and hoja.datos["taf"] == {"estado": "sin_dato"}
    assert "No tengo datos" in await ModeloFalso().generar("x", hoja)
