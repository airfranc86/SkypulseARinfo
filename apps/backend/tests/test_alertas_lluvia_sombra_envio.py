"""La lluvia en modo sombra, con el envío ENCENDIDO (lluvia, PR 1): cuenta, pero no manda nada y no pisa la tormenta.

Los tests de `test_alertas_evaluar_lluvia_sombra.py` corren en seco (`envio is None` siempre); acá la corrida SÍ envía
(`evaluar(enviar=True)`, con el envío falso de `PushFalso`), que es donde un cambio equivocado haría que la lluvia
mandara avisos.
"""
from __future__ import annotations

import pytest

from app.services.alertas import despacho
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    CALMA,
    PushFalso,
    correr,
    envio_activo,
    esperas,
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


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo, esperas, envio_activo):  # noqa: F811
    return own_caches


async def test_una_zona_solo_con_lluvia_no_manda_ningun_aviso_aunque_el_envio_este_encendido(
    redis, fake_upstash, install, push  # noqa: F811
) -> None:
    install(respond=respuestas_por_zona({"cordoba": LLUEVE}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 3)
    resultado = await correr(redis)
    assert resultado.con_lluvia == 1  # la vio...
    assert resultado.con_tormenta == 0 and resultado.sin_tormenta == 1
    assert push.llamadas == []  # ...pero no mandó nada
    assert resultado.envio is not None
    assert resultado.envio.enviados == 0 and resultado.envio.avisadas == 0 and resultado.envio.diferidos == 0


async def test_la_lluvia_de_una_zona_con_tormenta_no_cambia_lo_que_se_manda(
    redis, fake_upstash, install, push  # noqa: F811
) -> None:
    """Con tormenta Y lluvia, la zona avisa por la tormenta como siempre: una sola tanda de avisos por suscriptor."""
    install(respond=respuestas_por_zona({"cordoba": LLUEVE_Y_TORMENTA}, por_defecto=CALMA))
    ids = await registrar(redis, "cordoba", 2)
    resultado = await correr(redis)
    assert resultado.con_tormenta == 1 and resultado.con_lluvia == 1
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)  # 2 suscriptores, 1 aviso cada uno
    assert resultado.envio is not None and resultado.envio.enviados == 2


async def test_si_falla_el_despacho_de_la_tormenta_la_zona_no_pierde_su_lluvia(
    redis, fake_upstash, install, push, monkeypatch  # noqa: F811
) -> None:
    """La zona se rearma como `error`; el contador de lluvia es independiente del veredicto y no puede quedar corto."""
    install(respond=respuestas_por_zona({"cordoba": LLUEVE_Y_TORMENTA}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 1)

    async def despacho_que_revienta(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(despacho, "despachar_plan", despacho_que_revienta)
    resultado = await correr(redis)
    assert resultado.errores == 1 and resultado.con_tormenta == 0
    assert resultado.con_lluvia == 1
