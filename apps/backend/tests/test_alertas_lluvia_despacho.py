# ruff: noqa: F811  (the fixtures are imported by name and used as parameters)
"""El despacho del aviso de lluvia (lluvia, PR 3a): el plan, los destinatarios y las marcas propias.

El aviso de lluvia pasa por el MISMO `despachar_plan` que la tormenta (lotes, cortes, reintento, disyuntor), pero:
- sus destinatarios son el índice `alertas:zona:{slug}:lluvia`, y antes de mandar se RELEE el registro de cada id y se
  exige que siga pidiendo la lluvia y en esa zona (el índice es solo un índice);
- su done-set (`alertas:enviado:{slug}:lluvia-{hoy|manana}:{fecha}`), su Topic y su tag son propios: nunca pisan a la tormenta.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.alertas import despacho, despacho_lluvia, envio
from app.services.alertas import suscripcion as svc
from app.services.alertas.regla import ResultadoLluvia, VentanaLluvia
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    PushFalso,
    envio_activo,
    esperas,
    push,
    redis,
    registrar,
    reloj_de_openmeteo,
)
from tests.openmeteo_fake_source import own_caches  # noqa: F401

pytestmark = pytest.mark.integration

AR = timezone(timedelta(hours=-3))
H = 3600
FECHA = date(2026, 10, 14)
ENVIADOS_HOY = f"alertas:enviado:cordoba:lluvia-hoy:{FECHA:%Y-%m-%d}"
INDICE = "alertas:zona:cordoba:lluvia"


def _ts(dia: date, hora: int) -> int:
    return int(datetime(dia.year, dia.month, dia.day, tzinfo=AR).timestamp()) + hora * H


def _lluvia(desde: int = 14, hasta: int = 20, dia: date = FECHA) -> ResultadoLluvia:
    return ResultadoLluvia(
        ventanas=(
            VentanaLluvia(
                inicio=_ts(dia, desde), fin=_ts(dia, hasta), mm=3.6, probabilidad_media=90.0, horas_con_agua=hasta - desde,
                motivo="probabilidad",
            ),
        )
    )


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo, esperas, envio_activo):  # noqa: F811
    return own_caches


async def _plan(redis, aviso: str = despacho.AVISO_HOY, fecha: date = FECHA, resultado: ResultadoLluvia | None = None):
    return await despacho_lluvia.preparar_zona_lluvia(
        redis, slug="cordoba", resultado=resultado or _lluvia(), aviso=aviso, fecha=fecha
    )


async def _despachar(redis, plan, reloj=None, plazo_s: float = 60.0):
    return await despacho.despachar_plan(
        redis, plan, vapid=despacho.cargar_vapid(), plazo=despacho.Plazo.desde_ahora(plazo_s), reloj=reloj
    )


# ---------------------------------------------------------------------------
# El plan
# ---------------------------------------------------------------------------


async def test_el_plan_de_lluvia_lee_solo_el_indice_de_lluvia_y_su_propio_done_set(redis, fake_upstash, push) -> None:
    con = await registrar(redis, "cordoba", 2, lluvia=True)
    await registrar(redis, "cordoba", 3, lluvia=None, desde=10)  # reciben tormenta, no pidieron lluvia
    plan = await _plan(redis)
    assert plan.lluvia is True
    assert plan.aviso == "lluvia-hoy" and plan.slug == "cordoba" and plan.fecha == FECHA
    assert plan.miembros == 2 and plan.pendientes == tuple(sorted(con))
    assert plan.smn is not None  # lleva su Topic, su done-set y su vencimiento propios
    assert plan.smn.clave_enviados == ENVIADOS_HOY
    assert plan.smn.topic == envio.topic_lluvia("cordoba", FECHA)


async def test_el_done_set_de_lluvia_no_es_el_de_tormenta(redis, fake_upstash, push) -> None:
    plan = await _plan(redis)
    assert plan.smn is not None
    assert plan.smn.clave_enviados != despacho.clave_de_enviados("cordoba", despacho.AVISO_HOY, FECHA)


async def test_el_plan_ya_avisado_no_tiene_pendientes(redis, fake_upstash, push) -> None:
    con = await registrar(redis, "cordoba", 2, lluvia=True)
    fake_upstash.sets[ENVIADOS_HOY] = set(con)
    plan = await _plan(redis)
    assert plan.miembros == 2 and plan.pendientes == ()


async def test_el_texto_del_plan_de_manana_dice_manana_y_usa_su_propio_aviso(redis, fake_upstash, push) -> None:
    manana = FECHA + timedelta(days=1)
    await registrar(redis, "cordoba", 1, lluvia=True)
    plan = await _plan(redis, aviso=despacho.AVISO_MANANA, fecha=manana, resultado=_lluvia(6, 12, manana))
    assert plan.aviso == "lluvia-manana"
    cuerpo = json.loads(plan.payload)["body"]
    assert cuerpo.startswith("Posible lluvia persistente mañana a la mañana (6 a 12 h).")
    assert json.loads(plan.payload)["tag"] == envio.tag_lluvia("cordoba", manana)


async def test_sin_franjas_en_el_dia_del_aviso_la_zona_no_se_avisa(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 1, lluvia=True)
    plan = await _plan(redis, resultado=_lluvia(14, 20, FECHA - timedelta(days=1)))  # lluvia de AYER: ninguna hora de hoy
    assert plan.error is True


async def test_un_indice_vacio_no_manda_nada(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2, lluvia=None)
    plan = await _plan(redis)
    assert plan.miembros == 0
    resultado = await _despachar(redis, plan)
    assert resultado.resumen == despacho.ResumenEnvio() and push.llamadas == []


# ---------------------------------------------------------------------------
# El envío
# ---------------------------------------------------------------------------


async def test_se_manda_solo_a_quien_pidio_la_lluvia_con_su_topic_su_tag_y_su_done_set(redis, fake_upstash, push) -> None:
    con = await registrar(redis, "cordoba", 2, lluvia=True)
    await registrar(redis, "cordoba", 3, lluvia=None, desde=10)
    plan = await _plan(redis)
    resultado = await _despachar(redis, plan)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(con)
    assert resultado.resumen.enviados == 2 and resultado.resumen.avisadas == 1 and resultado.error is False
    llamada = push.llamadas[0]
    assert llamada.topic == envio.topic_lluvia("cordoba", FECHA)
    assert llamada.payload["tag"] == envio.tag_lluvia("cordoba", FECHA)
    assert "lluvia persistente" in llamada.payload["body"]
    assert fake_upstash.sets[ENVIADOS_HOY] == set(con)
    assert not [k for k in fake_upstash.sets if k.startswith("alertas:enviado:") and ":lluvia-" not in k]  # la tormenta, intacta


async def test_la_segunda_revision_del_dia_no_repite_el_aviso(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2, lluvia=True)
    await _despachar(redis, await _plan(redis))
    push.llamadas.clear()
    segunda = await _despachar(redis, await _plan(redis))
    assert push.llamadas == []
    assert segunda.resumen.ya_avisadas == 1 and segunda.resumen.enviados == 0


async def test_el_ttl_del_aviso_de_hoy_vence_a_medianoche_y_el_de_manana_dura_lo_de_siempre(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 1, lluvia=True)
    a_las_20 = lambda: datetime(2026, 10, 14, 20, 0, tzinfo=AR)  # noqa: E731
    await _despachar(redis, await _plan(redis), reloj=a_las_20)
    assert push.llamadas[0].ttl == 4 * H  # hasta las 24 h
    push.llamadas.clear()
    manana = FECHA + timedelta(days=1)
    await _despachar(redis, await _plan(redis, despacho.AVISO_MANANA, manana, _lluvia(6, 12, manana)), reloj=a_las_20)
    assert push.llamadas[0].ttl == envio.TTL_ALERTA_SEGUNDOS


# ---------------------------------------------------------------------------
# El índice es solo un índice: se relee el registro
# ---------------------------------------------------------------------------


async def test_un_id_del_indice_cuyo_registro_ya_no_pide_lluvia_no_recibe_nada_y_sale_del_indice(
    redis, fake_upstash, push
) -> None:
    ids = await registrar(redis, "cordoba", 2, lluvia=True)
    pegado, sano = ids
    registro = json.loads(fake_upstash.strings[f"alertas:sub:{pegado}"])
    registro.pop("lluvia")  # apagó la lluvia pero el índice quedó pegado (una falla a mitad de camino)
    fake_upstash.strings[f"alertas:sub:{pegado}"] = json.dumps(registro)
    resultado = await _despachar(redis, await _plan(redis))
    assert [c.sub_id for c in push.llamadas] == [sano]
    assert resultado.resumen.enviados == 1
    assert pegado not in fake_upstash.sets[INDICE] and sano in fake_upstash.sets[INDICE]
    assert pegado in fake_upstash.sets["alertas:zona:cordoba"]  # sigue recibiendo tormenta
    assert pegado in fake_upstash.sets[ENVIADOS_HOY]  # no se vuelve a mirar en esta fecha


async def test_un_id_cuyo_registro_se_mudo_de_zona_no_recibe_nada(redis, fake_upstash, push) -> None:
    (se_mudo,) = await registrar(redis, "cordoba", 1, lluvia=True)
    registro = json.loads(fake_upstash.strings[f"alertas:sub:{se_mudo}"])
    registro["zona"] = "rosario"
    fake_upstash.strings[f"alertas:sub:{se_mudo}"] = json.dumps(registro)
    await _despachar(redis, await _plan(redis))
    assert push.llamadas == []
    assert se_mudo not in fake_upstash.sets.get(INDICE, set())


async def test_un_id_del_indice_sin_registro_se_limpia_de_los_dos_sets(redis, fake_upstash, push) -> None:
    (vencido,) = await registrar(redis, "cordoba", 1, lluvia=True)
    del fake_upstash.strings[f"alertas:sub:{vencido}"]  # venció el TTL de 180 días
    resultado = await _despachar(redis, await _plan(redis))
    assert push.llamadas == [] and resultado.resumen.vencidos == 1
    assert vencido not in fake_upstash.sets.get(INDICE, set())
    assert vencido not in fake_upstash.sets.get("alertas:zona:cordoba", set())


async def test_leer_el_registro_con_lluvia_no_rompe_el_envio_de_tormenta(redis, fake_upstash, push) -> None:
    """El mismo registro (con `lluvia: true`) sigue siendo una suscripción válida para el envío de siempre."""
    (sub_id,) = await registrar(redis, "cordoba", 1, lluvia=True)
    leida = envio.leer_registro(fake_upstash.strings[f"alertas:sub:{sub_id}"])
    assert leida is not None and leida.zona == "cordoba"
    assert svc.lluvia_guardada(fake_upstash.strings[f"alertas:sub:{sub_id}"]) is True
