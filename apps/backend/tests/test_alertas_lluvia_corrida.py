"""La corrida completa con el envío de lluvia (lluvia, PR 3a): `evaluar(enviar=True)` y el flag `alertas_lluvia_activa`.

Con el flag APAGADO (el default) la corrida es la de siempre: la lluvia solo se cuenta (`con_lluvia`) y la respuesta, la
línea de log y los contadores no cambian. Con el flag ENCENDIDO manda el aviso de lluvia a quien lo pidió, después de la
tormenta, con su propio disyuntor y su propio resumen, y nunca en una zona que ya tiene tormenta.
"""

from __future__ import annotations

import logging

import pytest

from app.core.config import settings
from app.services.alertas import despacho, despacho_lluvia, evaluacion, metricas
from app.services.alertas.evaluacion import CONTADORES
from app.services.alertas.envio import Resultado
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    AHORA,
    CALMA,
    CLAVE_APAGADO,
    CLAVE_LOCK,
    correr,
    envio_activo,
    esperas,
    lineas_de_resumen,
    payload_horario,
    push,
    redis,
    registrar,
    reloj_de_openmeteo,
    respuestas_por_zona,
)
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401

pytestmark = pytest.mark.integration

# AHORA = miércoles 14/10/2026 10:30 (revisión de las 10 h: ventana 10 a 24 h). Llueve de 14 a 20 h con 90 %.
LLUEVE = payload_horario(lluvia={h: 0.6 for h in range(14, 20)}, probabilidad_base=90.0)
LLUEVE_Y_TORMENTA = payload_horario(codigos={16: 95}, lluvia={h: 0.6 for h in range(14, 20)}, probabilidad_base=90.0)
SOLO_TORMENTA = payload_horario(codigos={16: 95})


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo, esperas, envio_activo):  # noqa: F811
    return own_caches


@pytest.fixture
def lluvia_activa(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alertas_lluvia_activa", True)


# ---------------------------------------------------------------------------
# Flag apagado: la corrida es la de siempre
# ---------------------------------------------------------------------------


async def test_con_el_flag_apagado_la_lluvia_no_manda_nada_y_la_respuesta_es_la_de_siempre(
    redis, fake_upstash, install, push, caplog  # noqa: F811
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=True)
    resultado = await correr(redis)
    assert settings.alertas_lluvia_activa is False
    assert push.llamadas == []
    assert resultado.con_lluvia == 1 and resultado.envio_lluvia is None
    assert set(resultado.como_respuesta()) == {"estado", *CONTADORES, *despacho.CONTADORES_ENVIO}
    mensaje = lineas_de_resumen(caplog)[0].getMessage()
    assert "con_lluvia=1" in mensaje and "lluvia_enviados" not in mensaje and "lluvia_zonas" not in mensaje


# ---------------------------------------------------------------------------
# Flag encendido
# ---------------------------------------------------------------------------


async def test_con_el_flag_encendido_se_manda_la_lluvia_solo_a_quien_la_pidio(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    con = await registrar(redis, "cordoba", 2, lluvia=True)
    await registrar(redis, "cordoba", 3, lluvia=None, desde=10)  # solo tormenta
    resultado = await correr(redis)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(con)
    assert all("lluvia persistente" in c.payload["body"] for c in push.llamadas)
    assert resultado.envio_lluvia is not None and resultado.envio_lluvia.resumen.enviados == 2
    assert resultado.envio is not None and resultado.envio.enviados == 0  # el resumen de la tormenta, intacto
    assert resultado.con_tormenta == 0 and resultado.sin_tormenta == 1  # el veredicto de la zona no cambió


async def test_la_respuesta_trae_los_contadores_de_lluvia_solo_cuando_la_lluvia_corrio(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=True)
    respuesta = (await correr(redis)).como_respuesta()
    assert set(respuesta) == {"estado", *CONTADORES, *despacho.CONTADORES_ENVIO, *despacho_lluvia.CONTADORES_LLUVIA}
    assert respuesta["lluvia_zonas"] == 1 and respuesta["lluvia_enviados"] == 2 and respuesta["lluvia_avisadas"] == 1
    assert respuesta["lluvia_errores"] == 0 and respuesta["enviados"] == 0
    assert "con_lluvia" not in respuesta  # el contador de sombra sigue fuera del HTTP


async def test_la_linea_de_log_suma_los_contadores_de_lluvia(
    redis, fake_upstash, install, push, lluvia_activa, caplog  # noqa: F811
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=True)
    await correr(redis)
    mensaje = lineas_de_resumen(caplog)[0].getMessage()
    assert "lluvia_zonas=1" in mensaje and "lluvia_enviados=2" in mensaje and "lluvia_errores=0" in mensaje
    assert "cordoba" not in mensaje  # solo contadores


async def test_una_zona_con_tormenta_y_lluvia_recibe_solo_el_aviso_de_tormenta(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": LLUEVE_Y_TORMENTA}, por_defecto=CALMA))
    ids = await registrar(redis, "cordoba", 3, lluvia=True)
    resultado = await correr(redis)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)  # una sola tanda: la de tormenta
    assert all("tormentas" in c.payload["body"] and c.topic is None for c in push.llamadas)
    assert resultado.con_tormenta == 1 and resultado.envio.enviados == 3
    assert resultado.envio_lluvia is not None and resultado.envio_lluvia.zonas == 0


async def test_la_lluvia_se_manda_despues_de_la_tormenta_en_la_misma_corrida(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": SOLO_TORMENTA, "rosario": LLUEVE}, por_defecto=CALMA))
    tormenta_ids = await registrar(redis, "cordoba", 1, lluvia=True)
    lluvia_ids = await registrar(redis, "rosario", 1, lluvia=True)
    resultado = await correr(redis)
    orden = [c.sub_id for c in push.llamadas]
    assert orden == tormenta_ids + lluvia_ids
    assert resultado.envio.enviados == 1 and resultado.envio_lluvia.resumen.enviados == 1


async def test_la_segunda_corrida_del_dia_no_repite_el_aviso_de_lluvia(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=True)
    await correr(redis)
    push.llamadas.clear()
    fake_upstash.strings.pop(CLAVE_LOCK, None)  # otra corrida del día
    segunda = await correr(redis)
    assert push.llamadas == []
    assert segunda.envio_lluvia.resumen.ya_avisadas == 1 and segunda.envio_lluvia.resumen.enviados == 0


# ---------------------------------------------------------------------------
# Lo que no se manda
# ---------------------------------------------------------------------------


async def test_una_corrida_en_seco_no_manda_ni_prepara_la_lluvia(redis, fake_upstash, install, push, lluvia_activa) -> None:  # noqa: F811
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=True)
    resultado = await evaluacion.evaluar(redis, AHORA)  # sin enviar=True
    assert push.llamadas == [] and resultado.envio is None and resultado.envio_lluvia is None
    assert resultado.con_lluvia == 1  # sigue contándose


async def test_con_la_clave_de_apagado_no_se_manda_la_lluvia(redis, fake_upstash, install, push, lluvia_activa) -> None:  # noqa: F811
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=True)
    fake_upstash.strings[CLAVE_APAGADO] = "1"  # el operador apagó el envío
    resultado = await correr(redis)
    assert push.llamadas == []
    assert resultado.estado == evaluacion.ESTADO_APAGADO_A_MITAD


async def test_una_zona_sin_nadie_que_pidio_lluvia_no_manda_ni_falla(redis, fake_upstash, install, push, lluvia_activa) -> None:  # noqa: F811
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=None)
    resultado = await correr(redis)
    assert push.llamadas == [] and resultado.envio_lluvia.resumen.enviados == 0 and resultado.envio_lluvia.errores == 0


# ---------------------------------------------------------------------------
# Aislamiento: la lluvia nunca le cuesta nada a la tormenta
# ---------------------------------------------------------------------------


async def test_un_error_despachando_la_lluvia_es_un_error_de_lluvia_y_no_toca_la_tormenta(
    redis, fake_upstash, install, push, lluvia_activa, monkeypatch  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": SOLO_TORMENTA, "rosario": LLUEVE}, por_defecto=CALMA))
    tormenta_ids = await registrar(redis, "cordoba", 1)
    await registrar(redis, "rosario", 1, lluvia=True)
    original = despacho.despachar_plan

    async def falla_la_lluvia(redis_, plan, **kwargs):
        if plan.lluvia:
            raise RuntimeError("boom")
        return await original(redis_, plan, **kwargs)

    monkeypatch.setattr(despacho, "despachar_plan", falla_la_lluvia)
    resultado = await correr(redis)
    assert [c.sub_id for c in push.llamadas] == tormenta_ids  # la tormenta salió
    assert resultado.con_tormenta == 1 and resultado.errores == 0 and resultado.envio.enviados == 1
    assert resultado.envio_lluvia.errores == 1 and resultado.envio_lluvia.resumen.enviados == 0


async def test_la_lluvia_comparte_el_disyuntor_de_la_corrida_y_un_proxy_que_dice_404_a_todo_no_borra_nada(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    """El disyuntor es UNO por corrida (su tope de bajas también): si la tormenta lo abrió porque todo "venció", la lluvia no
    puede empezar con uno nuevo y borrar suscripciones vivas (3 envíos no alcanzan para que el suyo se abra solo)."""
    install(respond=respuestas_por_zona({"cordoba": SOLO_TORMENTA, "rosario": LLUEVE}, por_defecto=CALMA))
    todos = await registrar(redis, "cordoba", 6) + await registrar(redis, "rosario", 3, lluvia=True)
    for sub_id in todos:
        push.resultados[sub_id] = [Resultado.VENCIDA]  # un proxy que contesta 404 para todo
    resultado = await correr(redis)
    assert len(push.llamadas) == 9  # la tormenta intentó los 6 y la lluvia los 3
    vivas = [i for i in todos if f"alertas:sub:{i}" in fake_upstash.strings]
    assert vivas == todos  # ninguna suscripción se borró
    assert resultado.envio_lluvia.resumen.vencidos == 0 and resultado.envio_lluvia.resumen.fallidos == 3


async def test_la_lluvia_usa_el_mismo_objeto_disyuntor_que_la_tormenta(redis, fake_upstash, install, push, lluvia_activa) -> None:  # noqa: F811
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 1, lluvia=True)
    usados: list[object] = []
    original = despacho.despachar_plan

    async def espia(redis_, plan, **kwargs):
        usados.append(kwargs["disyuntor"])
        return await original(redis_, plan, **kwargs)

    despacho_original = despacho.despachar_plan
    despacho.despachar_plan = espia  # type: ignore[assignment]
    try:
        await correr(redis)
    finally:
        despacho.despachar_plan = despacho_original  # type: ignore[assignment]
    assert len(usados) == 1 and isinstance(usados[0], despacho.DisyuntorDeBajas)


# ---------------------------------------------------------------------------
# Qué zonas reciben la lluvia, y cuándo
# ---------------------------------------------------------------------------

LLUEVE_CON_UN_HUECO_EN_LA_TORMENTA = payload_horario(
    codigos={22: None}, lluvia={h: 0.6 for h in range(14, 20)}, probabilidad_base=90.0
)


async def test_una_zona_con_lluvia_y_un_hueco_en_la_tormenta_recibe_igual_la_lluvia(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    """Lluvia completa pero sin datos de tormenta en una hora: el veredicto es `sin_datos` (no "sin tormenta") y la evidencia
    positiva de la lluvia cuenta igual que en la tormenta."""
    install(respond=respuestas_por_zona({"cordoba": LLUEVE_CON_UN_HUECO_EN_LA_TORMENTA}, por_defecto=CALMA))
    ids = await registrar(redis, "cordoba", 2, lluvia=True)
    resultado = await correr(redis)
    assert resultado.sin_datos == 1 and resultado.con_tormenta == 0
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)


async def test_si_la_tormenta_se_quedo_sin_tiempo_para_la_segunda_pasada_no_se_manda_la_lluvia(
    redis, fake_upstash, install, push, lluvia_activa, monkeypatch  # noqa: F811
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 60)
    monkeypatch.setattr(despacho, "ESPERA_SEGUNDA_PASADA_SEGUNDOS", 100.0)  # más de lo que queda: sin segunda pasada
    install(respond=respuestas_por_zona({"cordoba": LLUEVE_CON_UN_HUECO_EN_LA_TORMENTA, "rosario": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 1, lluvia=True)
    await registrar(redis, "rosario", 1, lluvia=True)
    resultado = await correr(redis)
    assert resultado.estado == "evaluada_incompleta"
    assert push.llamadas == [] and resultado.envio_lluvia is None  # la corrida estaba cortada: la lluvia no corre


# ---------------------------------------------------------------------------
# El estado de la corrida es el de la tormenta
# ---------------------------------------------------------------------------


async def _con_un_corte_de_lluvia(redis, fake_upstash, install, push, monkeypatch, corte: str):  # noqa: ANN001, F811
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 1, lluvia=True)

    async def lluvia_cortada(*args, **kwargs):
        return despacho_lluvia.EnvioDeLluvia(zonas=1, corte=corte)

    monkeypatch.setattr(despacho_lluvia, "despachar_lluvia", lluvia_cortada)
    return await correr(redis)


async def test_si_la_lluvia_se_queda_sin_tiempo_el_estado_de_la_corrida_no_cambia(
    redis, fake_upstash, install, push, lluvia_activa, monkeypatch  # noqa: F811
) -> None:
    resultado = await _con_un_corte_de_lluvia(redis, fake_upstash, install, push, monkeypatch, despacho.CORTE_PLAZO)
    assert resultado.estado == evaluacion.ESTADO_EVALUADA  # la tormenta terminó completa: `lluvia_diferidos` dice el resto


@pytest.mark.parametrize("corte", [despacho.CORTE_APAGADO, despacho.CORTE_ILEGIBLE])
async def test_si_se_apaga_el_envio_durante_la_lluvia_la_corrida_queda_apagada_a_mitad(
    redis, fake_upstash, install, push, lluvia_activa, monkeypatch, corte  # noqa: F811
) -> None:
    resultado = await _con_un_corte_de_lluvia(redis, fake_upstash, install, push, monkeypatch, corte)
    assert resultado.estado == evaluacion.ESTADO_APAGADO_A_MITAD


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------


async def test_las_metricas_guardan_los_contadores_de_lluvia_distintos_de_cero(
    redis, fake_upstash, install, push, lluvia_activa  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2, lluvia=True)
    resultado = await correr(redis)
    campos = metricas.incrementos_de_corrida(metricas.TIPO_PRONOSTICO, resultado)
    assert campos[f"{metricas.TIPO_PRONOSTICO}:lluvia_enviados"] == 2
    assert campos[f"{metricas.TIPO_PRONOSTICO}:lluvia_zonas"] == 1
    assert not [c for c in campos if c.endswith("lluvia_errores")]  # los ceros no se guardan
