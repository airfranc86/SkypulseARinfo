"""METAR y TAF decodificados (asistente 2d-3b): los `peek_*` leen la caché y dan lo mismo que las funciones de red.

`get_nearest_metar_observation` (la tarjeta "Ahora") pide a AWC o lee su caché y decide; ahora la decisión es una función
pura compartida con `peek_nearest_metar_observation`, que SOLO lee la caché. Con lo mismo en caché, las dos vías dicen lo
mismo. Del TAF, `peek_taf_entry` lee la entrada de la caché y `taf_vigente` descarta lo que ya pasó.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.metar_observation import (
    get_nearest_metar_observation,
    observation_from_entries,
    peek_nearest_metar_observation,
)
from app.services.reportes_aeronauticos import clear_caches, nearest_airport, normalize_taf, peek_taf_entry
from app.services.reportes_aeronauticos import taf as taf_modulo
from app.services.reportes_aeronauticos.awc_metar import metar_entries_cache
from app.services.taf_decoded import taf_vigente
from tests.helpers_caracterizacion_aeronautica import load_taf

pytestmark = pytest.mark.unit

LAT, LON = -31.42, -64.19  # Córdoba, SACO a unos 11 km
LEJOS = (-38.0, -72.5)
AHORA = datetime(2026, 10, 19, 17, 20, tzinfo=timezone.utc)
AHORA_TAF = datetime(2026, 10, 7, 4, 0, tzinfo=timezone.utc)  # el TAF de SACO del fixture rige 06/10 18Z - 07/10 18Z


@pytest.fixture(autouse=True)
def _limpia():
    clear_caches()
    yield
    clear_caches()


def _entrada(hace_min=20, **campos):
    base = {"obsTime": int((AHORA - timedelta(minutes=hace_min)).timestamp()), "temp": 18, "dewp": 12, "wspd": 10, "wdir": 180}
    return {**base, **campos}


async def _metar(hace_min=20, icao="SACO", **campos):
    entrada = _entrada(hace_min, **campos)

    async def traer():
        return (entrada,)

    await metar_entries_cache.get_or_fetch(icao, traer)


async def _taf(icao="SACO"):
    entrada = load_taf("SACO")[0]

    async def traer():
        return entrada

    await taf_modulo._taf_cache.get_or_fetch(icao, traer)
    return entrada


# --- METAR ---------------------------------------------------------------------------------------------------------------

async def test_el_peek_del_metar_da_lo_mismo_que_la_funcion_de_red_con_lo_mismo_en_cache():
    await _metar(wxString="BR", rawOb="SACO 191700Z 18005KT 4000 BR")
    esperado = await get_nearest_metar_observation(LAT, LON, now=AHORA)
    assert esperado.reason == "metar_ok" and esperado.observation is not None
    assert peek_nearest_metar_observation(LAT, LON, now=AHORA) == esperado


async def test_sin_nada_en_cache_el_peek_no_pide_nada_y_dice_que_no_hay_metar():
    r = peek_nearest_metar_observation(LAT, LON, now=AHORA)
    assert r.reason == "metar_unavailable" and r.observation is None and r.icao == "SACO"


async def test_un_metar_de_hace_mas_de_90_minutos_no_se_usa_igual_que_en_la_tarjeta():
    await _metar(hace_min=95)
    r = peek_nearest_metar_observation(LAT, LON, now=AHORA)
    assert r.reason == "metar_stale" and r.observation is None
    assert r == await get_nearest_metar_observation(LAT, LON, now=AHORA)


async def test_un_metar_de_hace_justo_90_minutos_pasa_en_las_dos_vias():
    await _metar(hace_min=90)
    r = peek_nearest_metar_observation(LAT, LON, now=AHORA)
    assert r.reason == "metar_ok" and r == await get_nearest_metar_observation(LAT, LON, now=AHORA)


async def test_lejos_de_todo_aeropuerto_el_peek_no_usa_el_metar_aunque_haya_uno_en_cache():
    lat, lon = LEJOS
    await _metar(icao=nearest_airport(lat, lon).icao)
    r = peek_nearest_metar_observation(lat, lon, now=AHORA)
    assert r.reason == "metar_too_far" and r.observation is None and r.distance_km > 20
    assert r == await get_nearest_metar_observation(lat, lon, now=AHORA)


async def test_un_metar_sin_temperatura_no_se_usa_como_en_la_tarjeta():
    await _metar(temp=None)
    r = peek_nearest_metar_observation(LAT, LON, now=AHORA)
    assert r.reason == "metar_missing_fields" and r.observation is None
    assert r == await get_nearest_metar_observation(LAT, LON, now=AHORA)


async def test_el_peek_del_metar_sin_hora_usa_el_reloj_y_no_revienta():
    assert peek_nearest_metar_observation(LAT, LON).observation is None


def test_observation_from_entries_elige_el_reporte_mas_reciente_y_none_sin_lista():
    assert observation_from_entries(None, "SACO") is None
    assert observation_from_entries((), "SACO") is None
    viejo, nuevo = _entrada(60, temp=10), _entrada(10, temp=20)
    assert observation_from_entries((viejo, nuevo), "SACO").temp_c == 20


# --- TAF -----------------------------------------------------------------------------------------------------------------

async def test_peek_taf_entry_da_la_entrada_que_hay_en_cache():
    entrada = await _taf()
    assert peek_taf_entry("SACO") == entrada
    assert peek_taf_entry(" saco ") == entrada  # la misma estación, igual que `fetch_taf_entry`


def test_peek_taf_entry_sin_cache_da_none():
    assert peek_taf_entry("SACO") is None


async def test_peek_taf_entry_respeta_que_la_estacion_se_sabe_sin_taf():
    await _taf()
    taf_modulo._no_taf_cache["SACO"] = True  # AWC acaba de decir que no hay TAF: eso gana sobre una copia vieja
    assert peek_taf_entry("SACO") is None


async def test_taf_vigente_deja_solo_los_periodos_que_todavia_no_terminaron():
    taf = normalize_taf(await _taf())
    assert taf is not None and len(taf.periods) == 5
    vigente = taf_vigente(taf, AHORA_TAF)
    assert vigente is not None
    # a las 04:00Z ya terminaron el período base (hasta las 23Z) y el BECMG de las 23Z a las 03Z
    assert [p.valid_to.hour for p in vigente.periods] == [12, 9, 18]
    assert vigente.icao == taf.icao and vigente.raw == taf.raw


async def test_taf_vigente_no_modifica_el_taf_original():
    taf = normalize_taf(await _taf())
    taf_vigente(taf, AHORA_TAF)
    assert len(taf.periods) == 5


async def test_un_periodo_que_termina_justo_ahora_ya_no_rige():
    taf = normalize_taf(await _taf())
    justo = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)  # el BECMG de las 23Z termina a las 03Z
    vigente = taf_vigente(taf, justo)
    assert vigente is not None and all(p.valid_to > justo for p in vigente.periods)
    assert len(vigente.periods) == 3
    un_minuto_antes = taf_vigente(taf, justo - timedelta(minutes=1))
    assert un_minuto_antes is not None and len(un_minuto_antes.periods) == 4  # a las 02:59 ese período todavía rige


async def test_si_la_vigencia_total_del_taf_termino_no_rige_aunque_un_periodo_siga():
    taf = normalize_taf(await _taf())
    termina_ahora = taf.model_copy(update={"valid_to": AHORA_TAF})  # los períodos llegan hasta las 18Z, la vigencia no
    assert taf_vigente(termina_ahora, AHORA_TAF) is None
    termina_despues = taf.model_copy(update={"valid_to": AHORA_TAF + timedelta(minutes=1)})
    assert taf_vigente(termina_despues, AHORA_TAF) is not None


async def test_un_taf_vencido_o_inexistente_da_none():
    taf = normalize_taf(await _taf())
    assert taf_vigente(taf, datetime(2026, 10, 7, 18, 0, tzinfo=timezone.utc)) is None  # termina justo ahora
    assert taf_vigente(taf, datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)) is None
    assert taf_vigente(None, AHORA_TAF) is None
