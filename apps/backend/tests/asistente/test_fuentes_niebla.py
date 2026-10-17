# ruff: noqa: F811  (los fixtures se importan por nombre y se usan como parámetros)
"""Asistente 2d-3a-2: `FuentesDeCache` arma la niebla SOLO con lo que está en caché, con las reglas de la página de Niebla.

Fuentes (las mismas que la página): METAR del aeropuerto argentino más cercano (a menos de 20 km y de menos de 90 min), TAF de ese
aeropuerto y el pedido único de Open-Meteo de la niebla. Mora las lee con `peek` (cero red). Una fuente que no está en caché no
se inventa; sin visibilidad actual de ninguna, la niebla queda sin dato. Una copia vieja de Open-Meteo no se usa para decir cómo
está la visibilidad AHORA.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import app.services.openmeteo as om_module
from app.services.asistente.enrutador import Ruta, enrutar
from app.services.asistente.fuentes_cache import FuentesDeCache
from app.services.asistente.hoja_datos import armar_hoja
from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.verificador import verificar
from app.services.openmeteo_source import cache_key
from app.services.reportes_aeronauticos import clear_caches, nearest_airport
from app.services.reportes_aeronauticos.awc_metar import metar_entries_cache
from app.services.reportes_aeronauticos.taf import _taf_cache
from app.services.visibilidad import awc_visibility_m
from tests.asistente.test_fuentes_cache import sin_red  # noqa: F401  (el fixture se usa por nombre)
from tests.openmeteo_fake_source import install  # noqa: F401
from tests.test_niebla_servicio import _payload

pytestmark = pytest.mark.unit

AR = timezone(timedelta(hours=-3))
LAT, LON = -31.42, -64.19  # Córdoba: el aeropuerto SACO queda a unos 11 km
LEJOS = (-38.0, -72.5)  # sin ningún aeropuerto argentino a menos de 20 km
AHORA_AR = datetime(2026, 10, 19, 14, 20, tzinfo=AR)
AHORA = AHORA_AR.astimezone(timezone.utc)


@pytest.fixture(autouse=True)
def _aeronautica_limpia():
    clear_caches()
    yield
    clear_caches()


async def _sembrar_niebla(payload, lat=LAT, lon=LON) -> None:
    """Deja el JSON de la niebla en la caché, como si un usuario hubiera abierto la página de Niebla."""
    pedido = om_module._niebla_request(lat, lon)

    async def traer():
        return payload

    await om_module._CACHE_NOWCAST.get_or_fetch(cache_key(pedido.params()), traer)


async def _sembrar_metar(visib_sm: float, hace_min: int = 20, icao: str = "SACO") -> None:
    entrada = {"obsTime": int((AHORA - timedelta(minutes=hace_min)).timestamp()), "visib": visib_sm}

    async def traer():
        return (entrada,)

    await metar_entries_cache.get_or_fetch(icao, traer)


async def _sembrar_taf(visib_sm: float, wx: str = "", icao: str = "SACO") -> None:
    periodo = {
        "timeFrom": int((AHORA - timedelta(hours=1)).timestamp()),
        "timeTo": int((AHORA + timedelta(hours=30)).timestamp()),
        "visib": visib_sm,
        "wxString": wx,
    }

    async def traer():
        return {"fcsts": [periodo]}

    await _taf_cache.get_or_fetch(icao, traer)


async def _niebla(bloques=("niebla",), lat=LAT, lon=LON):
    return await FuentesDeCache().obtener(tuple(bloques), lat=lat, lon=lon, ahora_utc=AHORA)


# --- Sin nada en caché ----------------------------------------------------------------------------------------------------

async def test_con_las_cachés_vacías_no_hay_niebla_ni_pedidos(sin_red):
    assert (await _niebla()).niebla is None


async def test_solo_se_arma_si_se_pide_y_no_mira_lo_demas(sin_red, monkeypatch):
    await _sembrar_niebla(_payload())

    def prohibido(*_a, **_k):
        raise AssertionError("la niebla no necesita la serie del dashboard, lo actual ni los avisos")

    from app.services.asistente import fuentes_cache

    for nombre in ("peek_hourly_forecast_ext", "peek_hourly_forecast_ecmwf", "peek_current", "peek_smn_alertas"):
        monkeypatch.setattr(fuentes_cache, nombre, prohibido)
    assert (await _niebla(["niebla"])).niebla is not None


async def test_pedir_otra_cosa_no_arma_la_niebla(sin_red):
    await _sembrar_niebla(_payload())
    f = await FuentesDeCache().obtener(("ahora", "avisos"), lat=LAT, lon=LON, ahora_utc=AHORA)
    assert f.niebla is None


# --- La visibilidad de ahora ----------------------------------------------------------------------------------------------

async def test_con_un_metar_reciente_cerca_la_visibilidad_de_ahora_es_la_del_metar(sin_red):
    await _sembrar_niebla(_payload())
    await _sembrar_metar(0.25)  # un cuarto de milla: niebla
    n = (await _niebla()).niebla
    assert n is not None and n.source == "metar" and n.visibility_m == awc_visibility_m(0.25)
    assert n.metar_station == "SACO" and n.fog_level == 3
    assert n.metar_distance_km is not None and n.metar_distance_km < 20


async def test_un_metar_de_hace_mas_de_90_minutos_no_se_usa_y_queda_open_meteo(sin_red):
    await _sembrar_niebla(_payload())
    await _sembrar_metar(0.25, hace_min=95)
    n = (await _niebla()).niebla
    assert n is not None and n.source == "openmeteo" and n.visibility_m == 10_000.0
    assert n.metar_station == "SACO"  # la estación se informa igual


async def test_un_metar_de_hace_justo_90_minutos_todavia_se_usa(sin_red):
    await _sembrar_metar(0.25, hace_min=90)
    n = (await _niebla()).niebla
    assert n is not None and n.source == "metar"


async def test_lejos_de_todo_aeropuerto_el_metar_no_se_usa(sin_red):
    lat, lon = LEJOS
    await _sembrar_niebla(_payload(), lat, lon)
    await _sembrar_metar(0.25, icao=nearest_airport(lat, lon).icao)  # reciente, pero de una estación a más de 20 km
    n = (await _niebla(lat=lat, lon=lon)).niebla
    assert n is not None and n.source == "openmeteo" and n.metar_distance_km is not None and n.metar_distance_km > 20


async def test_sin_metar_ni_open_meteo_no_hay_niebla(sin_red):
    await _sembrar_taf(6.0)  # solo hay TAF: sin visibilidad de ahora no se responde
    assert (await _niebla()).niebla is None


async def test_open_meteo_de_hace_horas_no_dice_como_esta_la_visibilidad_ahora(sin_red):
    vieja = _payload()
    vieja["current"]["time"] = "2026-10-19T09:00"  # hace más de 5 horas
    await _sembrar_niebla(vieja)
    assert (await _niebla()).niebla is None


async def test_open_meteo_justo_en_el_limite_de_90_minutos_todavia_vale(sin_red):
    limite = _payload()
    limite["current"]["time"] = "2026-10-19T12:50"  # 90 minutos antes de las 14:20
    await _sembrar_niebla(limite)
    assert (await _niebla()).niebla is not None


# --- Las horas que vienen --------------------------------------------------------------------------------------------------

async def test_con_taf_en_cache_las_horas_salen_del_taf(sin_red):
    await _sembrar_niebla(_payload())
    await _sembrar_metar(2.0)
    await _sembrar_taf(0.5, wx="FG")
    n = (await _niebla()).niebla
    assert n is not None and n.hourly_source == "taf" and len(n.hourly) == 12
    assert n.hourly[0].hour_label == "15:00" and all(h.fog_level == 3 for h in n.hourly)


async def test_sin_taf_las_horas_salen_de_la_inferencia_de_open_meteo(sin_red):
    await _sembrar_niebla(_payload(weather_code={15: 45, 16: 45}))
    n = (await _niebla()).niebla
    assert n is not None and n.hourly_source == "openmeteo_inference"
    assert [h.fog_level for h in n.hourly[:3]] == [3, 3, 0]


async def test_una_serie_de_open_meteo_que_ya_no_llega_a_las_proximas_horas_no_inventa_horas(sin_red):
    vieja = _payload()
    vieja["current"]["time"] = "2026-10-19T14:00"
    for campo in vieja["hourly"]:
        vieja["hourly"][campo] = vieja["hourly"][campo][:12]  # termina a las 11:00: nada por delante
    await _sembrar_niebla(vieja)
    await _sembrar_metar(2.0)
    n = (await _niebla()).niebla
    assert n is not None and n.source == "metar" and n.hourly == [] and n.hourly_source == "openmeteo"


# --- En la hoja y en la respuesta -----------------------------------------------------------------------------------------

async def test_la_hoja_muestra_la_niebla_de_la_cache(sin_red):
    await _sembrar_niebla(_payload(weather_code={15: 45}))
    await _sembrar_metar(0.25)
    f = await _niebla()
    hoja = armar_hoja(Ruta(bloques=("niebla",)), f, AHORA)
    assert hoja.datos["niebla"]["estado"] and hoja.datos["niebla"]["estacion"] == "SACO"
    assert hoja.datos["niebla"]["horas_con_niebla"][0] == "15:00"


async def test_de_la_pregunta_a_la_respuesta_con_las_fuentes_reales_pasa_el_verificador(sin_red):
    await _sembrar_niebla(_payload())
    await _sembrar_metar(0.25)
    ruta = enrutar("¿Hay niebla ahora?")
    assert "niebla" in ruta.bloques
    f = await FuentesDeCache().obtener(ruta.bloques, lat=LAT, lon=LON, ahora_utc=AHORA)
    hoja = armar_hoja(ruta, f, AHORA)
    assert hoja.datos["niebla"] != {"estado": "sin_dato"}
    texto = await ModeloFalso().generar("x", hoja)
    v = verificar(texto, hoja)
    assert v.ok, (texto, v.motivos)


async def test_sin_datos_la_respuesta_dice_que_no_los_tiene(sin_red):
    ruta = Ruta(bloques=("niebla",))
    hoja = armar_hoja(ruta, await _niebla(), AHORA)
    assert hoja.datos["niebla"] == {"estado": "sin_dato"}
    assert "No tengo datos" in await ModeloFalso().generar("x", hoja)
