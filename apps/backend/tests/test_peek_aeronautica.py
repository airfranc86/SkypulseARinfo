"""METAR y TAF (asistente 2d-3a-2): los `peek_*` leen la caché y dan EXACTAMENTE lo que las funciones de red.

`get_nearest_metar_visibility` y `get_nearest_taf_hourly` piden a AWC (o leen su caché) y deciden. Ahora la decisión es una
función pura que comparten con `peek_nearest_metar_visibility` y `peek_nearest_taf_hourly`, que SOLO leen la caché: sin red,
sin esperar un pedido en vuelo, sin contar un pedido. Con lo mismo en caché, las dos vías dicen lo mismo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.reportes_aeronauticos import (
    clear_caches,
    get_nearest_metar_visibility,
    get_nearest_taf_hourly,
    nearest_airport,
    peek_nearest_metar_visibility,
    peek_nearest_taf_hourly,
)
from app.services.reportes_aeronauticos.awc_metar import metar_entries_cache
from app.services.reportes_aeronauticos.taf import _taf_cache

pytestmark = pytest.mark.unit

LAT, LON = -31.42, -64.19  # Córdoba, SACO a unos 11 km
LEJOS = (-38.0, -72.5)
AHORA = datetime(2026, 10, 19, 17, 20, tzinfo=timezone.utc)  # 14:20 en Argentina


@pytest.fixture(autouse=True)
def _limpia():
    clear_caches()
    yield
    clear_caches()


async def _metar(visib, hace_min=20, icao="SACO"):
    entrada = {"obsTime": int((AHORA - timedelta(minutes=hace_min)).timestamp()), "visib": visib}

    async def traer():
        return (entrada,)

    await metar_entries_cache.get_or_fetch(icao, traer)


async def _taf(visib, wx="", icao="SACO"):
    periodo = {
        "timeFrom": int((AHORA - timedelta(hours=1)).timestamp()),
        "timeTo": int((AHORA + timedelta(hours=30)).timestamp()),
        "visib": visib,
        "wxString": wx,
    }

    async def traer():
        return {"fcsts": [periodo]}

    await _taf_cache.get_or_fetch(icao, traer)


# --- METAR ---------------------------------------------------------------------------------------------------------------

async def test_el_peek_del_metar_da_lo_mismo_que_la_funcion_de_red_con_lo_mismo_en_cache():
    await _metar(0.25)
    assert peek_nearest_metar_visibility(LAT, LON, now=AHORA) == await get_nearest_metar_visibility(LAT, LON, now=AHORA)


async def test_sin_nada_en_cache_el_peek_no_pide_nada_y_dice_sin_visibilidad_pero_informa_la_estacion():
    r = peek_nearest_metar_visibility(LAT, LON, now=AHORA)
    assert r.visibility_m is None and r.icao == "SACO" and r.distance_km < 20 and r.observed_at is None


async def test_un_metar_de_hace_mas_de_el_maximo_no_se_usa_igual_que_en_la_pagina():
    await _metar(0.25, hace_min=95)
    r = peek_nearest_metar_visibility(LAT, LON, now=AHORA)
    assert r.visibility_m is None and r.observed_at is None
    assert r == await get_nearest_metar_visibility(LAT, LON, now=AHORA)


async def test_un_metar_de_hace_justo_90_minutos_pasa_en_las_dos_vias():
    await _metar(0.25, hace_min=90)
    r = peek_nearest_metar_visibility(LAT, LON, now=AHORA)
    assert r.visibility_m is not None and r == await get_nearest_metar_visibility(LAT, LON, now=AHORA)


async def test_lejos_de_todo_aeropuerto_el_peek_no_usa_el_metar_aunque_haya_uno_en_cache():
    lat, lon = LEJOS
    await _metar(0.25, icao=nearest_airport(lat, lon).icao)  # hay un METAR reciente de la estación más cercana, pero está lejos
    r = peek_nearest_metar_visibility(lat, lon, now=AHORA)
    assert r.visibility_m is None and r.distance_km > 20
    assert r == await get_nearest_metar_visibility(lat, lon, now=AHORA)


async def test_un_metar_sin_visibilidad_o_con_un_valor_ilegible_no_cuenta():
    await _metar(None)
    assert peek_nearest_metar_visibility(LAT, LON, now=AHORA).visibility_m is None
    clear_caches()
    await _metar("esto no es una visibilidad")
    assert peek_nearest_metar_visibility(LAT, LON, now=AHORA).visibility_m is None


async def test_el_peek_del_metar_sin_hora_usa_el_reloj_y_no_revienta():
    assert peek_nearest_metar_visibility(LAT, LON).visibility_m is None


# --- TAF -----------------------------------------------------------------------------------------------------------------

async def test_el_peek_del_taf_da_lo_mismo_que_la_funcion_de_red_con_lo_mismo_en_cache():
    await _taf(0.5, wx="FG")
    esperado = await get_nearest_taf_hourly(LAT, LON, hours=12, now=AHORA)
    assert esperado is not None
    assert peek_nearest_taf_hourly(LAT, LON, hours=12, now=AHORA) == esperado
    assert esperado[0].hour_label == "15:00" and esperado[0].fog_probable is True


async def test_sin_taf_en_cache_el_peek_da_none():
    assert peek_nearest_taf_hourly(LAT, LON, hours=12, now=AHORA) is None


async def test_un_taf_sin_visibilidad_en_ninguna_hora_da_none_como_en_la_pagina():
    await _taf(None)
    assert peek_nearest_taf_hourly(LAT, LON, hours=12, now=AHORA) is None
    assert await get_nearest_taf_hourly(LAT, LON, hours=12, now=AHORA) is None


async def test_el_peek_del_taf_respeta_cuantas_horas_se_piden():
    await _taf(1.0)
    assert len(peek_nearest_taf_hourly(LAT, LON, hours=5, now=AHORA) or []) == 5


async def test_una_estacion_que_se_sabe_sin_taf_no_da_un_taf_viejo():
    from app.services.reportes_aeronauticos import taf as taf_modulo

    await _taf(1.0)
    taf_modulo._no_taf_cache["SACO"] = True  # AWC acaba de decir que no hay TAF: eso gana sobre una copia vieja
    assert peek_nearest_taf_hourly(LAT, LON, hours=12, now=AHORA) is None
