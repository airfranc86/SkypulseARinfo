"""Leer de la caché de Open-Meteo lo que Previsión ya trajo, sin hacer ningún pedido (para el asistente)."""
from __future__ import annotations

import pytest

import app.services.openmeteo as om_module
import app.services.openmeteo_source as source_module
from app.services.openmeteo_source import CacheLevel, SeriesRequest
from tests.openmeteo_fake_source import LAT, LON, install  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

PAYLOAD = {
    "elevation": 25.0,
    "hourly": {"time": [f"2026-10-08T{h:02d}:00" for h in range(24)], "temperature_2m": [20.0] * 24},
}


async def test_antes_de_cualquier_pedido_no_hay_nada_y_peek_no_llama_a_la_fuente(install):  # noqa: F811
    fuente = install(PAYLOAD)
    for _ in range(3):
        assert om_module.peek_hourly_forecast_ext(LAT, LON) is None
        assert om_module.peek_hourly_forecast_ecmwf(LAT, LON) is None
    assert fuente.calls == []


async def test_la_serie_que_trajo_previsión_se_lee_con_peek_sin_otro_pedido(install):  # noqa: F811
    fuente = install(PAYLOAD)
    traida = await om_module.get_hourly_forecast_ext(LAT, LON, days=7)  # lo que piden el dashboard y las herramientas
    assert traida is not None
    assert om_module.peek_hourly_forecast_ext(LAT, LON) is traida
    assert len(fuente.calls) == 1


async def test_lo_mismo_con_la_serie_de_ecmwf(install):  # noqa: F811
    fuente = install(PAYLOAD)
    traida = await om_module.get_hourly_forecast_ecmwf(LAT, LON, days=7)
    assert om_module.peek_hourly_forecast_ecmwf(LAT, LON) is traida
    assert om_module.peek_hourly_forecast_ext(LAT, LON) is None  # son entradas distintas: el modelo va en la clave
    assert len(fuente.calls) == 1


async def test_una_serie_de_otros_dias_no_es_la_de_previsión(install):  # noqa: F811
    install(PAYLOAD)
    await om_module.get_hourly_forecast_ext(LAT, LON, days=2)
    assert om_module.peek_hourly_forecast_ext(LAT, LON) is None  # peek mira la de 7 días, la de Previsión
    assert om_module.peek_hourly_forecast_ext(LAT, LON, days=2) is not None


async def test_las_coordenadas_se_redondean_igual_que_en_el_pedido(install):  # noqa: F811
    install(PAYLOAD)
    traida = await om_module.get_hourly_forecast_ext(-31.4, -64.2, days=7)
    assert om_module.peek_hourly_forecast_ext(-31.401, -64.199) is traida  # mismo punto de 1,1 km
    assert om_module.peek_hourly_forecast_ext(-31.5, -64.2) is None


async def test_peek_series_lee_cualquier_pedido_por_su_nivel_y_sus_parametros(install):  # noqa: F811
    install(PAYLOAD)
    pedido = om_module._hourly_request(LAT, LON, 7)
    assert source_module.peek_series(pedido) is None
    traida = await om_module.get_hourly_forecast_ext(LAT, LON, days=7)
    assert source_module.peek_series(pedido) is traida
    otro = SeriesRequest(lat=LAT, lon=LON, level=CacheLevel.FORECAST, hourly=("temperature_2m",), forecast_days=7)
    assert source_module.peek_series(otro) is None


async def test_una_serie_vencida_pero_con_copia_buena_se_sigue_leyendo(install, monkeypatch):  # noqa: F811
    install(PAYLOAD)
    traida = await om_module.get_hourly_forecast_ext(LAT, LON, days=7)
    clave = source_module.cache_key(om_module._hourly_request(LAT, LON, 7).params())
    del om_module._CACHE_FORECAST._cache[clave]  # venció el TTL de 30 min; la copia buena (hasta 3 h) sigue
    assert om_module.peek_hourly_forecast_ext(LAT, LON) is traida


PAYLOAD_ACTUAL = {
    "current": {
        "time": "2026-10-08T12:00", "temperature_2m": 18.0, "relative_humidity_2m": 60.0, "wind_speed_10m": 11.0,
    },
}


async def test_las_condiciones_actuales_que_trajo_previsión_se_leen_con_peek(install):  # noqa: F811
    fuente = install(PAYLOAD_ACTUAL)
    assert om_module.peek_current(LAT, LON) is None
    traida = await om_module.get_current(LAT, LON)
    assert traida is not None and om_module.peek_current(LAT, LON) is traida
    assert len(fuente.calls) == 1


def test_los_siete_dias_de_previsión_tienen_una_sola_definicion():
    """Si Previsión pasara a otra cantidad de días, el asistente se quedaría sin dato en silencio."""
    import app.routers.tools as tools
    import app.routers.weather as weather
    import app.services.fire_danger as fire_danger

    assert om_module.DASHBOARD_HOURLY_DAYS == 7
    assert tools._FORECAST_DAYS == fire_danger._FORECAST_DAYS == weather.DASHBOARD_HOURLY_DAYS == 7


async def test_lo_que_trae_una_herramienta_lo_encuentra_el_asistente(async_client, install, fresh_rate_limit):  # noqa: F811
    fuente = install(PAYLOAD)
    respuesta = await async_client.get(f"/api/tools/tender-ropa?lat={LAT}&lon={LON}")
    assert respuesta.status_code == 200
    assert om_module.peek_hourly_forecast_ext(LAT, LON) is not None
    assert len(fuente.calls) == 1
