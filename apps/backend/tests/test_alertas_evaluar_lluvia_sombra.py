"""La evaluación programada CUENTA la lluvia pero no cambia nada de lo que hacía (lluvia, PR 1: modo sombra).

Contrato de este PR, probado por la evaluación completa (Upstash y Open-Meteo falsos, sin red):
- el pedido a ECMWF suma `precipitation` y `precipitation_probability` y sigue siendo UNO por zona;
- el contador `con_lluvia` aparece en la línea de resumen del log (solo contadores: sin zonas, ids ni textos);
- NO cambia el veredicto de ninguna zona, NO manda nada y NO entra en la respuesta HTTP (la lista blanca de contadores
  sigue igual: es un contrato que lee QStash y el panel).
"""
from __future__ import annotations

import logging

import pytest

from app.services.alertas import evaluacion, pronostico
from app.services.alertas.evaluacion import CONTADORES
from app.services.alertas.zonas import zona_por_slug
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name; estado_de_alertas_limpio is autouse)
    AHORA,
    CALMA,
    CONTADORES_HTTP,
    TORMENTA,
    estado_de_alertas_limpio,
    lineas_de_resumen,
    payload_horario,
    redis,
    reloj_de_openmeteo,
    respuestas_por_zona,
    suscribir,
)
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401

pytestmark = pytest.mark.integration

# AHORA = miércoles 14/10/2026 10:30 (revisión de las 10 h: ventana 10 a 24 h). Llueve de 14 a 20 h con 90 %.
LLUEVE = payload_horario(
    lluvia={h: 0.6 for h in range(14, 20)},  # 3,6 mm en 6 h
    probabilidad_base=90.0,
)
LLUEVE_Y_TORMENTA = payload_horario(
    codigos={16: 95},
    lluvia={h: 0.6 for h in range(14, 20)},
    probabilidad_base=90.0,
)
NO_LLUEVE_CON_PROBABILIDAD = payload_horario(lluvia={}, probabilidad_base=90.0)  # 90 % pero 0 mm: no es lluvia


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo):  # noqa: F811
    return own_caches


# ---------------------------------------------------------------------------
# El pedido
# ---------------------------------------------------------------------------


def test_el_pedido_de_la_zona_suma_la_lluvia_y_sigue_siendo_uno():
    zona = zona_por_slug("cordoba")
    pedido = pronostico.pedido_de_zona(zona)
    assert pedido.hourly == ("weather_code", "cape", "precipitation", "precipitation_probability")
    assert pedido.params()["hourly"] == "weather_code,cape,precipitation,precipitation_probability"
    assert pedido.models == "ecmwf_ifs025"
    assert pedido.forecast_days == 2
    assert pedido.persist is False


async def test_una_corrida_hace_un_solo_pedido_por_zona(redis, fake_upstash, install) -> None:  # noqa: F811
    fake = install(respond=respuestas_por_zona({"cordoba": LLUEVE, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    await evaluacion.evaluar(redis, AHORA)
    assert len(fake.calls) == 2  # una por zona, con la lluvia incluida


# ---------------------------------------------------------------------------
# El contador
# ---------------------------------------------------------------------------


async def test_la_linea_de_resumen_cuenta_las_zonas_con_lluvia(redis, fake_upstash, install, caplog) -> None:  # noqa: F811
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": LLUEVE, "rosario": CALMA, "mendoza": LLUEVE}))
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza")
    resultado = await evaluacion.evaluar(redis, AHORA)
    mensaje = lineas_de_resumen(caplog)[0].getMessage()
    assert "con_lluvia=2" in mensaje
    assert resultado.con_lluvia == 2
    # solo contadores: ninguna zona, id ni texto
    for secreto in ("cordoba", "rosario", "mendoza", "ID-SECRETO"):
        assert secreto not in mensaje


async def test_sin_lluvia_el_contador_es_cero(redis, fake_upstash, install, caplog) -> None:  # noqa: F811
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": CALMA}))
    suscribir(fake_upstash, "cordoba")
    await evaluacion.evaluar(redis, AHORA)
    assert "con_lluvia=0" in lineas_de_resumen(caplog)[0].getMessage()


async def test_una_probabilidad_alta_sin_mm_no_cuenta_como_lluvia(redis, fake_upstash, install, caplog) -> None:  # noqa: F811
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": NO_LLUEVE_CON_PROBABILIDAD}))
    suscribir(fake_upstash, "cordoba")
    await evaluacion.evaluar(redis, AHORA)
    assert "con_lluvia=0" in lineas_de_resumen(caplog)[0].getMessage()


async def test_la_serie_sin_precipitacion_no_cuenta_ni_rompe_nada(redis, fake_upstash, install, caplog) -> None:  # noqa: F811
    """Una respuesta (o caché) sin `precipitation`: la tormenta se evalúa igual y la lluvia es "sin señal"."""
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": CALMA}))  # CALMA no trae precipitation
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.sin_tormenta == 1 and resultado.sin_datos == 0 and resultado.con_lluvia == 0


async def test_la_lluvia_y_la_tormenta_se_cuentan_por_separado(redis, fake_upstash, install, caplog) -> None:  # noqa: F811
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": LLUEVE_Y_TORMENTA, "rosario": TORMENTA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.con_tormenta == 2
    assert resultado.con_lluvia == 1
    mensaje = lineas_de_resumen(caplog)[0].getMessage()
    assert "con_tormenta=2" in mensaje and "con_lluvia=1" in mensaje


# ---------------------------------------------------------------------------
# Lo que NO cambia
# ---------------------------------------------------------------------------


async def test_la_lluvia_no_cambia_el_veredicto_de_la_zona(redis, fake_upstash, install) -> None:  # noqa: F811
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}))
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, AHORA)
    (zona,) = resultado.zonas
    assert zona.veredicto == evaluacion.VEREDICTO_SIN_TORMENTA  # llueve pero no hay tormenta: nada cambia
    assert resultado.sin_tormenta == 1 and resultado.con_tormenta == 0
    assert zona.revision is None and zona.aviso is None  # ningún aviso preparado


async def test_modo_sombra_no_manda_nada(redis, fake_upstash, install, caplog) -> None:  # noqa: F811
    """Con el envío apagado (corrida en seco) nada se manda; con la lluvia en modo sombra, tampoco hay ningún envío
    propio de la lluvia: el resultado no tiene `envio` y el log no trae contadores de envío."""
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}))
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.envio is None
    mensaje = lineas_de_resumen(caplog)[0].getMessage()
    assert "enviados=" not in mensaje and "avisadas=" not in mensaje


def test_la_lista_blanca_de_la_respuesta_http_no_cambia() -> None:
    assert CONTADORES == CONTADORES_HTTP
    assert "con_lluvia" not in CONTADORES


async def test_la_respuesta_http_del_resultado_no_lleva_la_lluvia(redis, fake_upstash, install) -> None:  # noqa: F811
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}))
    suscribir(fake_upstash, "cordoba")
    respuesta = (await evaluacion.evaluar(redis, AHORA)).como_respuesta()
    assert "con_lluvia" not in respuesta
    assert set(respuesta) == {"estado", *CONTADORES}


async def test_un_error_en_la_regla_de_lluvia_nunca_rompe_la_evaluacion_de_tormenta(
    redis, fake_upstash, install, caplog, monkeypatch  # noqa: F811
) -> None:
    """El modo sombra no puede costarle nada a las alertas reales: si la regla de lluvia falla, se registra y la zona
    conserva su veredicto de tormenta (acá: una tormenta que sigue siendo `con_tormenta`)."""
    from app.services.alertas import regla

    def _falla(*args, **kwargs):
        raise RuntimeError("bug en la regla de lluvia")

    monkeypatch.setattr(regla, "evaluar_revision_lluvia", _falla)
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.con_tormenta == 1 and resultado.sin_tormenta == 1
    assert resultado.errores == 0 and resultado.sin_datos == 0
    assert resultado.con_lluvia == 0
    assert any("rain shadow rule" in r.getMessage() for r in caplog.records)
    assert "bug en la regla" not in lineas_de_resumen(caplog)[0].getMessage()
