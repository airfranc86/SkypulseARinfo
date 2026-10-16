"""Independent probes of FRA-360 part 2 (verifier): tables derived from the spec, concurrency, cancellation, privacy."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas import avisos_sentry, firma_qstash, metricas
from app.services.alertas.despacho import ResumenEnvio, ResumenSmn
from app.services.alertas.evaluacion import ResultadoEvaluacion, ResultadoEvaluacionSmn
from tests.alertas_helpers import estado_de_alertas_limpio, sentry_espia  # noqa: F401
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL

ESTADOS = ("upstash_no_disponible", "sin_vapid", "evaluada_incompleta", "evaluada", "en_curso", "fuera_de_ventana",
           "apagado_a_mitad", "apagado", "algo_raro", "")


# ---- S3/S4: the oracle written from the spec text, not from the code -------------------------------------------------
def oraculo_corrida(tipo: str, estado: str, evaluadas: int, sin_datos: int, smn_sin_datos: int) -> tuple[str, str] | None:
    if estado in ("upstash_no_disponible", "sin_vapid"):
        return estado, "error"
    if estado == "evaluada_incompleta":
        return estado, "warning"
    if estado != "evaluada":  # apagado, en_curso, fuera_de_ventana, apagado_a_mitad, unknown: NOT failures (S3)
        return None
    if tipo == "smn":
        return ("smn_sin_datos", "warning") if smn_sin_datos == 1 else None
    if evaluadas > 0 and sin_datos == evaluadas:
        return "sin_datos_total", "warning"
    return None


@pytest.mark.parametrize("estado", ESTADOS)
@pytest.mark.parametrize(("evaluadas", "sin_datos"), [(0, 0), (1, 0), (1, 1), (5, 4), (5, 5), (12, 12)])
def test_forecast_rule_table(estado, evaluadas, sin_datos) -> None:
    r = ResultadoEvaluacion(estado=estado, evaluadas=evaluadas, sin_datos=sin_datos, errores=0, diferidas=3)
    aviso = avisos_sentry.aviso_de_corrida("pronostico", r)
    esperado = oraculo_corrida("pronostico", estado, evaluadas, sin_datos, 0)
    assert (None if aviso is None else (aviso.tags["motivo"], aviso.nivel)) == esperado
    if aviso is not None:
        assert aviso.mensaje == f"alertas: corrida fallida ({esperado[0]})"
        assert aviso.fingerprint == ("alertas-corrida", esperado[0])
        assert aviso.tags["estado"] in metricas.ESTADOS_CONOCIDOS | {"desconocido"}


@pytest.mark.parametrize("estado", ESTADOS)
@pytest.mark.parametrize("smn_sin_datos", [0, 1])
@pytest.mark.parametrize("smn_errores", [0, 3])
def test_smn_rule_table(estado, smn_sin_datos, smn_errores) -> None:
    r = ResultadoEvaluacionSmn(estado=estado, smn=ResumenSmn(smn_sin_datos=smn_sin_datos, smn_avisos=2, smn_errores=smn_errores))
    aviso = avisos_sentry.aviso_de_corrida("smn", r)
    esperado = oraculo_corrida("smn", estado, 0, 0, smn_sin_datos)
    assert (None if aviso is None else (aviso.tags["motivo"], aviso.nivel)) == esperado


# ---- S5: the 20 % rule, exhaustive for 0..12 attempts ----------------------------------------------------------------
@pytest.mark.parametrize("estado", ["evaluada", "evaluada_incompleta", "apagado_a_mitad", "sin_vapid"])
def test_sends_rule_table(estado) -> None:
    for intentos in range(0, 13):
        for fallidos in range(0, intentos + 1):
            for vencidos, diferidos in ((0, 0), (9, 0), (0, 9), (7, 7)):
                envio = ResumenEnvio(enviados=intentos - fallidos, fallidos=fallidos, vencidos=vencidos, diferidos=diferidos)
                for r in (ResultadoEvaluacion(estado=estado, envio=envio), ResultadoEvaluacionSmn(estado=estado, envio=envio)):
                    aviso = avisos_sentry.aviso_de_envios("pronostico", r)
                    dispara = estado != "apagado_a_mitad" and (
                        (intentos >= 5 and fallidos * 5 > intentos) or (intentos >= 2 and fallidos == intentos))
                    assert (aviso is not None) == dispara, (estado, intentos, fallidos, vencidos, diferidos)
                    if aviso is not None:
                        assert aviso.mensaje == "alertas: fallos de envío por encima del 20 %"
                        assert aviso.fingerprint == ("alertas-envios",)
                        assert aviso.extras["intentos"] == intentos
                        assert all(type(v) is int for v in aviso.extras.values())
    assert avisos_sentry.aviso_de_envios("pronostico", ResultadoEvaluacion(estado=estado, envio=None)) is None


# ---- S6: the 12 reasons ----------------------------------------------------------------------------------------------
def test_signature_reasons_partition() -> None:
    todos = {v for k, v in vars(firma_qstash).items() if k.startswith("MOTIVO_")}
    assert len(todos) == 12
    assert avisos_sentry.MOTIVOS_QUE_AVISAN == {"clave", "sub", "body", "iss", "exp_nbf", "algoritmo", "config", "interno"}
    assert avisos_sentry.MOTIVOS_SILENCIOSOS == {"sin_cabecera", "formato", "firma_larga", "cuerpo"}
    assert avisos_sentry.MOTIVOS_QUE_AVISAN | avisos_sentry.MOTIVOS_SILENCIOSOS == todos
    for m in todos:
        a = avisos_sentry.aviso_de_firma(m)
        assert (a is not None) == (m in avisos_sentry.MOTIVOS_QUE_AVISAN)


# ---- S7/S8: concurrency, cancellation, failure modes --------------------------------------------------------------------
class RedisLento(UpstashRedis):
    """set_nx that waits (an event) and then answers like Upstash; counts calls."""

    def __init__(self, resultado: object = True) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self.llamadas: list[tuple] = []
        self.puerta = asyncio.Event()
        self.resultado = resultado

    async def set_nx(self, key: str, value: str, ex: int) -> bool:
        self.llamadas.append((key, value, ex))
        await self.puerta.wait()
        if isinstance(self.resultado, BaseException):
            raise self.resultado
        return self.resultado  # type: ignore[return-value]


async def test_twenty_simultaneous_alerts_of_each_kind_emit_once_and_ask_once(sentry_espia) -> None:  # noqa: F811
    redis = RedisLento()
    corrida = ResultadoEvaluacion(estado="sin_vapid")
    envios = ResultadoEvaluacion(estado="evaluada", envio=ResumenEnvio(fallidos=3))
    tareas = [asyncio.create_task(avisos_sentry.avisar_firma_invalida(redis, "clave")) for _ in range(20)]
    tareas += [asyncio.create_task(avisos_sentry.avisar_corrida(redis, "pronostico", corrida)) for _ in range(20)]
    tareas += [asyncio.create_task(avisos_sentry.avisar_corrida(redis, "smn", envios)) for _ in range(20)]
    await asyncio.sleep(0)
    redis.puerta.set()
    await asyncio.gather(*tareas)
    assert sorted(k for k, _, _ in redis.llamadas) == ["alertas:sentry:corrida", "alertas:sentry:envios", "alertas:sentry:firma"]
    assert all(v == "1" and ex == 21600 for _, v, ex in redis.llamadas)
    assert sorted(k["tags"]["alert_kind"] for _, k in sentry_espia) == ["alertas_corrida", "alertas_envios", "alertas_firma"]


@pytest.mark.parametrize("previa", [None, "vencida"])
async def test_cancel_while_asking_restores_the_memory_and_propagates(sentry_espia, monkeypatch, previa) -> None:  # noqa: F811
    reloj = {"t": 100_000.0}
    monkeypatch.setattr(avisos_sentry, "_monotonico", lambda: reloj["t"])
    if previa == "vencida":
        avisos_sentry._ultimas["firma"] = reloj["t"] - 21_601
    antes = dict(avisos_sentry._ultimas)
    redis = RedisLento()
    tarea = asyncio.create_task(avisos_sentry.avisar_firma_invalida(redis, "clave"))
    await asyncio.sleep(0)
    assert avisos_sentry._ultimas["firma"] == reloj["t"]  # marked BEFORE the await
    tarea.cancel()
    with pytest.raises(asyncio.CancelledError):
        await tarea
    assert avisos_sentry._ultimas == antes and sentry_espia == []
    redis2 = RedisLento()
    redis2.puerta.set()
    await avisos_sentry.avisar_firma_invalida(redis2, "clave")  # the next one is not blocked by a poisoned memory
    assert len(sentry_espia) == 1 and len(redis2.llamadas) == 1


@pytest.mark.parametrize("falla", [UpstashUnavailableError("x"), RuntimeError("SECRETO"), ValueError("SECRETO")])
async def test_any_exception_of_the_mark_still_emits_once_and_never_raises(sentry_espia, caplog, falla) -> None:  # noqa: F811
    redis = RedisLento(resultado=falla)
    redis.puerta.set()
    for _ in range(5):
        await avisos_sentry.avisar_firma_invalida(redis, "clave")
    assert len(sentry_espia) == 1 and len(redis.llamadas) == 1
    assert "SECRETO" not in caplog.text


@pytest.mark.parametrize("exc", [RuntimeError, ValueError, TypeError, KeyError, OSError, UpstashUnavailableError])
async def test_capture_message_raising_anything_never_reaches_the_caller(monkeypatch, caplog, exc) -> None:
    def boom(*a, **k):
        raise exc("SECRETO-SDK")

    monkeypatch.setattr(avisos_sentry, "capture_message", boom)
    await avisos_sentry.avisar_corrida(None, "pronostico", ResultadoEvaluacion(estado="sin_vapid", envio=ResumenEnvio(fallidos=2)))
    await avisos_sentry.avisar_firma_invalida(None, "iss")
    assert "SECRETO-SDK" not in caplog.text


async def test_redis_none_emits_from_memory_only(sentry_espia) -> None:  # noqa: F811
    for _ in range(4):
        await avisos_sentry.avisar_corrida(None, "smn", ResultadoEvaluacionSmn(estado="evaluada", smn=ResumenSmn(smn_sin_datos=1)))
    assert len(sentry_espia) == 1


def test_no_bool_extra_and_closed_tags_over_the_whole_domain() -> None:
    vistos = []
    for estado in ESTADOS:
        for tipo, r in (("pronostico", ResultadoEvaluacion(estado=estado, evaluadas=2, sin_datos=2, envio=ResumenEnvio(fallidos=2))),
                        ("smn", ResultadoEvaluacionSmn(estado=estado, smn=ResumenSmn(smn_sin_datos=1), envio=ResumenEnvio(fallidos=2)))):
            for a in (avisos_sentry.aviso_de_corrida(tipo, r), avisos_sentry.aviso_de_envios(tipo, r)):
                if a is not None:
                    vistos.append(a)
                    assert all(type(v) is int for v in a.extras.values())
                    assert a.tags.get("estado") in metricas.ESTADOS_CONOCIDOS | {"desconocido"}
                    assert "algo_raro" not in json.dumps([a.mensaje, dict(a.tags), list(a.fingerprint)])
    assert vistos
