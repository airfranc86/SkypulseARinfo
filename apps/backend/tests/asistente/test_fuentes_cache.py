"""T4 del PR 2c: `FuentesDeCache` arma las fuentes del asistente SOLO con lo que ya está en las cachés."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import respx

import app.services.openmeteo as om_module
import app.services.smn_alertas as smn
from app.schemas.smn_alertas import SmnAlerta
from app.services.asistente import fuentes_cache
from app.services.asistente.enrutador import Ruta
from app.services.asistente.fuentes_cache import FuentesDeCache
from app.services.asistente.hoja_datos import armar_hoja
from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.nucleo import responder
from app.services.calculators import compute_cota_de_nieve
from app.services.openmeteo_source import cache_key
from app.services.openmeteo import OpenMeteoCurrent
from tests.hourly_fixtures import DAY0, make_hourly
from tests.openmeteo_fake_source import LAT, LON, install  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

UTC = timezone.utc
AHORA = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)  # 12:00 en Argentina; la serie de `make_hourly` arranca ese día a las 00:00
PEDIDO_A_LAS = AHORA - timedelta(minutes=20)


async def _sembrar(serie, *, ecmwf=False) -> None:
    """Deja `serie` en la caché de Previsión, como si un usuario hubiera abierto esa página."""
    pedido = om_module._hourly_ecmwf_request(LAT, LON, 7) if ecmwf else om_module._hourly_request(LAT, LON, 7)

    async def traer():
        return serie

    await om_module._CACHE_FORECAST.get_or_fetch(cache_key(pedido.params()), traer)


def _serie(**sobrescribir):
    return replace(make_hourly(hours=48, **sobrescribir), fetched_at=PEDIDO_A_LAS)


async def _obtener(bloques, lat=LAT, lon=LON):
    return await FuentesDeCache().obtener(tuple(bloques), lat=lat, lon=lon, ahora_utc=AHORA)


@pytest.fixture
def sin_red(install, monkeypatch):  # noqa: F811
    """Cualquier pedido a Open-Meteo o al SMN revienta la prueba."""
    fuente = install(RuntimeError("no se puede pedir nada"))

    async def refresco_prohibido(*_a, **_k):
        raise AssertionError("el asistente no puede refrescar el feed del SMN")

    monkeypatch.setattr(smn, "_refresh", refresco_prohibido)
    smn.reset_cache()
    monkeypatch.setattr(smn, "_utcnow", lambda: AHORA)
    with respx.mock(assert_all_called=False) as http:  # sin rutas: cualquier pedido HTTP, por el camino que sea, revienta
        yield fuente
    smn.reset_cache()
    assert fuente.calls == [], "se hizo un pedido a Open-Meteo"
    assert http.calls.call_count == 0, "se hizo un pedido HTTP"


# --- Sin nada en caché -------------------------------------------------------------------------------------------------

async def test_con_las_cachés_vacías_no_hay_datos_ni_pedidos(sin_red):
    f = await _obtener(["ahora", "horas", "dias", "avisos", "cota_nieve"])
    assert f.ahora is None and f.franjas == () and f.dias == () and f.cota_nieve is None
    assert f.avisos is None  # el feed del SMN no está verificado: "no sé", no "no hay"
    assert f.generado_en is None


# --- La serie horaria --------------------------------------------------------------------------------------------------

async def test_ahora_horas_y_dias_salen_de_la_serie_de_previsión(sin_red):
    await _sembrar(_serie())
    f = await _obtener(["ahora", "horas", "dias"])
    assert (f.ahora.temp_c, f.ahora.humidity, f.ahora.wind_speed_kmh) == (20.0, 50.0, 10.0)
    assert len(f.franjas) == 4 and f.franjas[0].hour_label == "12:00"
    assert [d.date for d in f.dias][:2] == ["2026-09-19", "2026-09-20"]
    assert f.generado_en == PEDIDO_A_LAS


async def test_el_resultado_se_ve_en_la_hoja_con_los_numeros_de_la_serie(sin_red):
    await _sembrar(_serie())
    f = await _obtener(["ahora"])
    hoja = armar_hoja(Ruta(bloques=("ahora",)), f, AHORA)
    assert hoja.datos["ahora"] == {"temp_c": 20, "humedad_pct": 50, "viento_kmh": 10}


async def test_con_ecmwf_en_caché_la_lluvia_la_pone_ecmwf_como_en_el_dashboard(sin_red):
    await _sembrar(_serie())  # best_match: sin lluvia
    await _sembrar(_serie(precipitations={14: 6.0}), ecmwf=True)
    f = await _obtener(["horas"])
    lluvia = {s.hour_label: s.precip_mm for s in f.franjas}
    assert lluvia["15:00"] == 6.0  # la franja que termina a las 15:00 incluye la hora 14, con la lluvia de ECMWF


async def test_la_edad_del_pronóstico_es_la_de_la_serie_mas_vieja(sin_red):
    vieja = AHORA - timedelta(hours=3)
    await _sembrar(_serie())
    await _sembrar(replace(_serie(), fetched_at=vieja), ecmwf=True)
    assert (await _obtener(["ahora"])).generado_en == vieja


async def test_si_la_mezcla_con_ecmwf_falla_se_usa_best_match_solo(sin_red, monkeypatch, caplog):
    await _sembrar(_serie())
    await _sembrar(_serie(precipitations={14: 6.0}), ecmwf=True)

    def mezcla_rota(*_a, **_k):
        raise ValueError("serie rara")

    monkeypatch.setattr(fuentes_cache, "merge_hourly_ecmwf", mezcla_rota)
    f = await _obtener(["horas"])
    assert {s.precip_mm for s in f.franjas} == {0.0}
    assert f.generado_en == PEDIDO_A_LAS


async def test_una_serie_vencida_pero_con_copia_buena_se_usa_y_se_nota_su_edad(sin_red):
    vieja = AHORA - timedelta(hours=3)
    await _sembrar(replace(_serie(), fetched_at=vieja))
    clave = cache_key(om_module._hourly_request(LAT, LON, 7).params())
    del om_module._CACHE_FORECAST._cache[clave]  # venció el TTL de 30 min; queda la copia buena (hasta 3 h)
    f = await _obtener(["ahora"])
    assert f.ahora is not None and f.generado_en == vieja
    assert armar_hoja(Ruta(bloques=("ahora",)), f, AHORA).datos["pronostico_hace_h"] == 3


async def test_otras_coordenadas_no_encuentran_la_serie(sin_red):
    await _sembrar(_serie())
    f = await _obtener(["ahora"], lat=-34.6, lon=-58.4)
    assert f.ahora is None


# --- Solo lo que se pide ------------------------------------------------------------------------------------------------

async def test_solo_se_arma_lo_que_se_pide(sin_red):
    await _sembrar(_serie())
    f = await _obtener(["ahora"])
    assert f.ahora is not None and f.franjas == () and f.dias == () and f.cota_nieve is None and f.avisos is None


async def test_pedir_solo_avisos_no_mira_las_series(sin_red, monkeypatch):
    def prohibido(*_a, **_k):
        raise AssertionError("no hacía falta mirar la serie")

    monkeypatch.setattr(fuentes_cache, "peek_hourly_forecast_ext", prohibido)
    monkeypatch.setattr(fuentes_cache, "peek_hourly_forecast_ecmwf", prohibido)
    monkeypatch.setattr(fuentes_cache, "peek_current", prohibido)
    assert (await _obtener(["avisos"])).avisos is None


async def test_los_bloques_que_este_armador_no_conoce_quedan_sin_dato(sin_red):
    await _sembrar(_serie())
    f = await _obtener(["niebla", "metar", "taf"])
    assert (f.niebla, f.metar, f.taf) == (None, None, None) and not f.herramientas
    assert not f.glosario  # el glosario solo se carga si se pide (2d-4: ver test_glosario.py)
    # Las herramientas tampoco se cargan sin que se pidan (2d-2: ver test_fuentes_herramientas.py).


# --- La cota de nieve -----------------------------------------------------------------------------------------------------

async def test_la_cota_de_nieve_usa_la_temperatura_de_la_hora_850_hpa_y_la_altitud_del_punto(sin_red):
    await _sembrar(_serie(elevation_m=800.0, temps_c={12: 4.0}, temps_850_c={12: -2.0}))
    esperado = compute_cota_de_nieve(temp_c=4.0, station_altitude_m=800.0, temp_850_hpa=-2.0)
    assert (await _obtener(["cota_nieve"])).cota_nieve == esperado


async def test_sin_la_altitud_del_punto_no_se_inventa_una_cota(sin_red):
    await _sembrar(_serie(elevation_m=None))
    assert (await _obtener(["cota_nieve"])).cota_nieve is None


async def test_sin_temperatura_850_la_cota_igual_se_arma_con_los_otros_dos_metodos(sin_red):
    serie = replace(_serie(elevation_m=500.0), temps_850_c=[])
    await _sembrar(serie)
    cota = (await _obtener(["cota_nieve"])).cota_nieve
    assert cota is not None and cota.m850_hpa_m is None


# --- Los avisos del SMN ----------------------------------------------------------------------------------------------------

def _cargar_feed(monkeypatch, *avisos):
    poligono = ((-31.0, -64.6), (-31.0, -63.8), (-31.8, -63.8), (-31.8, -64.6))
    estado = smn._FeedState(
        entries={f"g{i}": smn.CapAlert(alerta=a, status="Actual", polygons=(poligono,)) for i, a in enumerate(avisos)},
        last_feed_ok=990.0, complete=True,
    )
    monkeypatch.setattr(smn, "_state", estado)
    monkeypatch.setattr(smn, "_monotonic", lambda: 1000.0)


async def test_con_el_feed_verificado_los_avisos_son_los_de_ese_punto(sin_red, monkeypatch):
    aviso = SmnAlerta(nivel="naranja", tipo="Tormentas", fecha_desde=AHORA, fecha_hasta=AHORA + timedelta(hours=5), descripcion="x")
    _cargar_feed(monkeypatch, aviso)
    assert (await _obtener(["avisos"])).avisos == (aviso,)
    assert (await _obtener(["avisos"], lat=-38.0, lon=-57.5)).avisos == ()  # verificado, y sin avisos ahí


async def test_con_el_feed_verificado_y_sin_avisos_es_una_tupla_vacia_no_none(sin_red, monkeypatch):
    _cargar_feed(monkeypatch)
    assert (await _obtener(["avisos"])).avisos == ()


# --- De punta a punta: la pregunta de un usuario ------------------------------------------------------------------------

async def test_la_pregunta_de_un_usuario_se_responde_con_los_datos_de_la_caché(sin_red):
    await _sembrar(_serie())
    ruta_fuentes = await _obtener(["ahora"])
    r = await responder("¿Qué temperatura hace ahora?", ruta_fuentes, ModeloFalso(), ahora_utc=AHORA)
    assert r.estado == "ok" and "20 °C" in r.texto and "humedad de 50 %" in r.texto


async def test_sin_nada_en_caché_la_pregunta_se_responde_sin_dato_y_sin_pedidos(sin_red):
    r = await responder("¿Qué temperatura hace ahora?", await _obtener(["ahora"]), ModeloFalso(), ahora_utc=AHORA)
    assert r.estado == "sin_dato"


# --- Series raras y objetos compartidos ---------------------------------------------------------------------------------

async def test_una_serie_vacia_en_caché_cuenta_como_sin_dato(sin_red):
    await _sembrar(replace(make_hourly(hours=0), fetched_at=PEDIDO_A_LAS))  # con fecha: lo único raro es que está vacía
    f = await _obtener(["ahora", "horas", "dias", "cota_nieve"])
    assert f.ahora is None and f.franjas == () and f.generado_en is None


async def test_un_ecmwf_vacio_se_ignora_y_se_usa_best_match(sin_red):
    await _sembrar(_serie())
    await _sembrar(replace(make_hourly(hours=0), fetched_at=AHORA - timedelta(hours=5)), ecmwf=True)
    f = await _obtener(["horas"])
    assert len(f.franjas) == 4
    assert f.generado_en == PEDIDO_A_LAS  # una serie vacía no envejece el pronóstico


async def test_no_modifica_las_series_compartidas_de_la_caché(sin_red):
    """La serie que devuelve `peek` es la misma que ven Previsión y las herramientas: tocarla las rompería."""
    import copy

    base, ecmwf = _serie(), _serie(precipitations={14: 6.0})
    await _sembrar(base)
    await _sembrar(ecmwf, ecmwf=True)
    antes = (copy.deepcopy(base), copy.deepcopy(ecmwf))
    await _obtener(["ahora", "horas", "dias", "cota_nieve"])
    assert (base, ecmwf) == antes


# --- Lo actual (la tarjeta "Ahora" de Previsión) ---------------------------------------------------------------------

async def _sembrar_actual(temp=18.0, hum=60.0, viento=11.0, fetched_at=PEDIDO_A_LAS) -> None:
    actual = OpenMeteoCurrent(
        temp_c=temp, feels_like_c=None, humidity=hum, wind_speed_kmh=viento, wind_dir_deg=None, pressure_hpa=None,
        precip_1h_mm=None, cloud_cover=None, weather_code=None, description=None, fetched_at=fetched_at,
    )

    async def traer():
        return actual

    clave = cache_key(om_module._current_request(LAT, LON).params())
    await om_module._CACHE_CURRENT.get_or_fetch(clave, traer)


async def test_ahora_sale_de_lo_actual_como_la_tarjeta_de_previsión_y_no_de_la_hora_de_la_serie(sin_red):
    await _sembrar(_serie())  # la serie horaria dice 20 °C, 50 %, 10 km/h
    await _sembrar_actual(temp=18.0, hum=60.0, viento=11.0)
    f = await _obtener(["ahora"])
    assert (f.ahora.temp_c, f.ahora.humidity, f.ahora.wind_speed_kmh) == (18.0, 60.0, 11.0)


async def test_ahora_funciona_con_solo_lo_actual_sin_serie(sin_red):
    await _sembrar_actual()
    f = await _obtener(["ahora", "horas"])
    assert f.ahora.temp_c == 18.0 and f.franjas == ()
    assert f.generado_en == PEDIDO_A_LAS


async def test_el_dato_que_le_falta_a_lo_actual_se_completa_con_la_serie(sin_red):
    await _sembrar(_serie())
    await _sembrar_actual(temp=18.0, hum=None, viento=None)
    f = await _obtener(["ahora"])
    assert (f.ahora.temp_c, f.ahora.humidity, f.ahora.wind_speed_kmh) == (18.0, 50.0, 10.0)


async def test_si_lo_actual_esta_vencido_pero_hay_copia_buena_se_usa(sin_red):
    await _sembrar_actual(temp=18.0)
    clave = cache_key(om_module._current_request(LAT, LON).params())
    del om_module._CACHE_CURRENT._cache[clave]  # venció el TTL de 10 min; queda la copia buena
    assert (await _obtener(["ahora"])).ahora.temp_c == 18.0


async def test_la_edad_es_la_del_dato_mas_viejo_entre_la_serie_y_lo_actual(sin_red):
    vieja = AHORA - timedelta(hours=1, minutes=30)
    await _sembrar(_serie())
    await _sembrar_actual(fetched_at=vieja)
    assert (await _obtener(["ahora"])).generado_en == vieja


async def test_la_cota_de_nieve_usa_la_temperatura_actual_como_el_endpoint(sin_red):
    await _sembrar(_serie(elevation_m=800.0, temps_c={12: 4.0}, temps_850_c={12: -2.0}))
    await _sembrar_actual(temp=6.0)
    esperado = compute_cota_de_nieve(temp_c=6.0, station_altitude_m=800.0, temp_850_hpa=-2.0)
    assert (await _obtener(["cota_nieve"])).cota_nieve == esperado


async def test_la_cota_de_nieve_necesita_la_serie_para_la_altitud_aunque_haya_lo_actual(sin_red):
    await _sembrar_actual(temp=6.0)
    assert (await _obtener(["cota_nieve"])).cota_nieve is None


# --- Casos límite de la serie ----------------------------------------------------------------------------------------------

async def test_una_serie_que_arranca_ayer_igual_deja_hoy_y_mañana(sin_red):
    """Entre las 00:00 y las 03:00 la copia que hay en caché puede ser de ayer: pedir 3 días alcanza para hoy y mañana."""
    await _sembrar(replace(make_hourly(hours=72, start=DAY0 - timedelta(days=1)), fetched_at=PEDIDO_A_LAS))
    f = await _obtener(["dias"])
    cuando = [d["cuando"] for d in armar_hoja(Ruta(bloques=("dias",)), f, AHORA).datos["dias"]]
    assert cuando == ["hoy", "mañana"]


async def test_si_la_temperatura_de_la_hora_viene_vacia_no_hay_cota(sin_red):
    await _sembrar(_serie(elevation_m=800.0, temps_c={12: None}))
    f = await _obtener(["cota_nieve"])
    assert f.cota_nieve is None  # sin temperatura no se inventa; antes esto era un TypeError


async def test_una_serie_sin_fecha_de_pedido_no_se_usa_porque_no_se_sabe_cuan_vieja_es(sin_red):
    await _sembrar(replace(make_hourly(hours=48), fetched_at=None))
    f = await _obtener(["ahora", "horas"])
    assert f.ahora is None and f.franjas == () and f.generado_en is None


# --- Las herramientas y el asistente ven la misma serie --------------------------------------------------------------------

async def test_la_serie_que_trae_una_herramienta_la_usa_el_asistente_sin_otro_pedido(async_client, install, fresh_rate_limit):  # noqa: F811
    fuente = install({
        "elevation": 25.0,
        "hourly": {
            "time": [f"{(AHORA + timedelta(hours=h - 12)).strftime('%Y-%m-%dT%H')}:00" for h in range(48)],
            "temperature_2m": [21.0] * 48,
        },
    })
    r = await async_client.get(f"/api/tools/tender-ropa?lat={LAT}&lon={LON}")
    assert r.status_code == 200 and len(fuente.calls) == 1
    f = await _obtener(["ahora"])
    assert f.ahora is not None and f.ahora.temp_c == 21.0
    assert len(fuente.calls) == 1
