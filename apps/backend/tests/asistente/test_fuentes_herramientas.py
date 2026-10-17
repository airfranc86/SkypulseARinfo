# ruff: noqa: F811  (los fixtures se importan por nombre y se usan como parámetros)
"""Asistente 2d-2: `FuentesDeCache` arma las tres herramientas (tender, deporte y lavar el auto) SOLO con lo que está en caché.

Mora tiene que decir lo mismo que la página de cada herramienta: sale de la misma cuenta (`services/herramientas.py`, 2d-1) y de
la misma serie (best_match de 7 días, la que pidió la página: SIN la mezcla con ECMWF que usa Previsión). Sin serie, vencida o sin
fecha de pedido no se inventa nada: esa herramienta queda sin dato y el modelo ni se llama.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from app.services import herramientas
from app.services.asistente.enrutador import Ruta, enrutar
from app.services.asistente.hoja_datos import armar_hoja
from app.services.asistente.modelo import ModeloFalso
from app.services.asistente.verificador import verificar
from tests.asistente.test_fuentes_cache import (  # noqa: F401  (los fixtures se usan por nombre)
    AHORA,
    PEDIDO_A_LAS,
    _obtener,
    _sembrar,
    _serie,
    sin_red,
)
from tests.hourly_fixtures import DAY0, make_hourly
from tests.openmeteo_fake_source import install  # noqa: F401

pytestmark = pytest.mark.unit

TRES = ["herramienta:tender", "herramienta:deporte", "herramienta:lavar_auto"]


def _serie_con(**sobrescribir):
    """48 h desde el 19/09 00:00 (Argentina); AHORA es ese día a las 12:00."""
    return _serie(**sobrescribir)


# --- Sin datos ------------------------------------------------------------------------------------------------------------

async def test_con_las_cachés_vacías_no_hay_herramientas_ni_pedidos(sin_red):
    f = await _obtener(TRES)
    assert not f.herramientas and f.generado_en is None


async def test_una_serie_sin_fecha_de_pedido_no_se_usa(sin_red):
    await _sembrar(replace(make_hourly(hours=48), fetched_at=None))
    assert not (await _obtener(TRES)).herramientas


async def test_una_serie_que_ya_termino_no_da_herramientas(sin_red):
    await _sembrar(replace(make_hourly(hours=10), fetched_at=PEDIDO_A_LAS))  # 00:00 a 09:00; ahora son las 12:00
    assert not (await _obtener(TRES)).herramientas


async def test_otras_coordenadas_no_encuentran_la_serie(sin_red):
    await _sembrar(_serie_con())
    assert not (await _obtener(TRES, lat=-34.6, lon=-58.4)).herramientas


# --- Lo mismo que la página -----------------------------------------------------------------------------------------------

async def test_tender_y_deporte_dan_exactamente_lo_que_da_la_pagina(sin_red):
    serie = _serie_con(precipitations={h: 1.5 for h in range(14, 18)}, temps_c={h: 27.0 for h in range(10, 20)})
    await _sembrar(serie)
    f = await _obtener(TRES)
    assert f.herramientas["tender"] == herramientas.tender_ropa(serie, AHORA)
    assert f.herramientas["deporte"] == herramientas.hacer_deporte(serie, AHORA)


async def test_solo_se_arma_lo_que_se_pide(sin_red):
    await _sembrar(_serie_con())
    assert set((await _obtener(["herramienta:tender"])).herramientas) == {"tender"}
    assert set((await _obtener(["herramienta:deporte", "herramienta:lavar_auto"])).herramientas) == {"deporte", "lavar_auto"}
    assert not (await _obtener(["ahora", "horas"])).herramientas


async def test_usa_la_serie_best_match_pelada_y_no_la_mezclada_con_ecmwf(sin_red):
    """Las páginas de las herramientas nunca piden ECMWF: si Mora usara la serie de Previsión (con ECMWF superpuesto), el
    puntaje y el motivo podrían diferir de lo que el usuario ve en la página."""
    base = _serie_con()  # sin lluvia
    await _sembrar(base)
    await _sembrar(_serie_con(precipitations={h: 6.0 for h in range(12, 18)}), ecmwf=True)  # ECMWF dice que llueve fuerte
    f = await _obtener(["herramienta:tender", "herramienta:deporte"])
    assert f.herramientas["tender"] == herramientas.tender_ropa(base, AHORA)
    assert f.herramientas["tender"].precip == 0.0  # la lluvia de ECMWF no entra
    assert f.herramientas["deporte"] == herramientas.hacer_deporte(base, AHORA)


async def test_la_edad_del_pronostico_incluye_la_serie_de_las_herramientas(sin_red):
    vieja = AHORA - timedelta(hours=5)
    await _sembrar(replace(_serie_con(), fetched_at=vieja))
    assert (await _obtener(["herramienta:tender"])).generado_en == vieja


# --- Lavar el auto: el día de hoy ----------------------------------------------------------------------------------------

async def test_lavar_auto_habla_de_hoy_y_no_de_ayer_si_la_copia_en_cache_arranca_ayer(sin_red):
    """Entre las 00:00 y las 03:00 la copia puede arrancar ayer: `lavar_coche_dias` cuenta desde la primera fecha de la serie."""
    ayer = DAY0 - timedelta(days=1)
    lluvia_ayer = {h: 8.0 for h in range(0, 24)}  # llovió todo el 18/09
    serie = replace(make_hourly(hours=72, start=ayer, precipitations=lluvia_ayer), fetched_at=PEDIDO_A_LAS)
    await _sembrar(serie)
    r = (await _obtener(["herramienta:lavar_auto"])).herramientas["lavar_auto"]
    hoy = next(d for d in herramientas.lavar_coche_dias(serie) if d.date == "2026-09-19")
    assert r.score == hoy.score and r.headline == hoy.headline  # el de HOY (19/09), no el de ayer lluvioso
    assert r.score > 50


async def test_lavar_auto_sin_el_dia_de_hoy_en_la_serie_no_da_dato(sin_red):
    ayer = DAY0 - timedelta(days=3)
    await _sembrar(replace(make_hourly(hours=48, start=ayer), fetched_at=PEDIDO_A_LAS))  # 16 y 17/09: hoy no está
    assert "lavar_auto" not in (await _obtener(["herramienta:lavar_auto"])).herramientas


async def test_lavar_auto_con_una_serie_que_arranca_despues_de_hoy_no_habla_de_otro_dia(sin_red):
    manana = DAY0 + timedelta(days=1)  # 20 y 21/09: el día de hoy (19/09) no está en la serie
    await _sembrar(replace(make_hourly(hours=48, start=manana), fetched_at=PEDIDO_A_LAS))
    assert "lavar_auto" not in (await _obtener(["herramienta:lavar_auto"])).herramientas


async def test_lavar_auto_dice_el_mejor_dia_cuando_no_es_hoy(sin_red):
    lluvia_hoy = {h: 4.0 for h in range(0, 24)}  # llueve todo hoy; mañana (domingo) está limpio
    await _sembrar(_serie_con(precipitations=lluvia_hoy))
    r = (await _obtener(["herramienta:lavar_auto"])).herramientas["lavar_auto"]
    assert r.best_window == "Mejor día: domingo"


async def test_lavar_auto_no_nombra_otro_dia_si_hoy_ya_es_el_mejor(sin_red):
    await _sembrar(_serie_con(precipitations={h: 4.0 for h in range(24, 48)}))  # llueve mañana, hoy no
    r = (await _obtener(["herramienta:lavar_auto"])).herramientas["lavar_auto"]
    assert r.best_window is None


async def test_lavar_auto_arma_el_motivo_con_los_numeros_del_dia(sin_red):
    serie = _serie_con(temps_c={12: 31.0}, precipitations={14: 2.5}, wind_speeds={13: 30.0})
    await _sembrar(serie)
    r = (await _obtener(["herramienta:lavar_auto"])).herramientas["lavar_auto"]
    assert r.reason == "Máxima de 31 grados, lluvia de 2,5 mm y viento de hasta 30 km/h."
    assert r.tool == "lavar-coche" and r.source == "openmeteo"


async def test_lavar_auto_sin_lluvia_lo_dice(sin_red):
    await _sembrar(_serie_con())
    r = (await _obtener(["herramienta:lavar_auto"])).herramientas["lavar_auto"]
    assert r.reason == "Máxima de 20 grados, sin lluvia y viento de hasta 10 km/h."


# --- De punta a punta -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("pregunta", "clave"),
    [
        ("¿Puedo tender la ropa hoy?", "tender"),
        ("¿Conviene salir a correr?", "deporte"),
        ("¿Lavo el auto?", "lavar_auto"),
    ],
)
async def test_de_la_pregunta_a_la_respuesta_con_las_fuentes_reales_pasa_el_verificador(sin_red, pregunta, clave):
    await _sembrar(_serie_con(precipitations={14: 2.5}, temps_c={12: 28.0}))
    ruta = enrutar(pregunta)
    assert ruta.bloques == (f"herramienta:{clave}",)
    f = await _obtener(ruta.bloques)
    hoja = armar_hoja(ruta, f, AHORA)
    assert hoja.datos[f"herramienta:{clave}"] != {"estado": "sin_dato"}
    texto = await ModeloFalso().generar("x", hoja)
    v = verificar(texto, hoja)
    assert v.ok, (clave, texto, v.motivos)


async def test_sin_datos_la_respuesta_dice_que_no_los_tiene(sin_red):
    ruta = Ruta(bloques=("herramienta:tender",))
    hoja = armar_hoja(ruta, await _obtener(ruta.bloques), AHORA)
    assert hoja.datos["herramienta:tender"] == {"estado": "sin_dato"}
    assert "No tengo datos" in await ModeloFalso().generar("x", hoja)
