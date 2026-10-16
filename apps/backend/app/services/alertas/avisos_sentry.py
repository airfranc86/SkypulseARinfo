"""Sentry alerts about the push-alert runs (FRA-360, T11, part 2): a failed run, a failed signature, failed sends.

Sentry sends the email by its default rule for new issues; this module only decides WHEN a run deserves an event and
emits it, at most once every 6 hours per kind (the free plan has 5,000 events a month). Three kinds, three Redis keys
(`alertas:sentry:{corrida|envios|firma}`):

    corrida   (`alert_kind=alertas_corrida`) a run that did not do its job: `upstash_no_disponible` and `sin_vapid` are
              errors; `evaluada_incompleta`, a forecast run where EVERY zone asked was `sin_datos` (`sin_datos_total`;
              a partial `sin_datos` is the usual Open-Meteo 429) and an SMN run that could not verify the feed
              (`smn_sin_datos`) are warnings. `en_curso`, `fuera_de_ventana`, `apagado_a_mitad` (the operator, or a kill key that could not be read, stopped it)
              and any state outside the closed list are NOT failures; `errores > 0` is not alerted here (it reaches the log)
    envios    (`alert_kind=alertas_envios`, error) more than 20 % of the notifications of a run failed: `intentos`
              is `enviados + fallidos` (`vencidos` and `diferidos` are not attempts that failed) and it fires with
              `intentos >= 5 and fallidos * 5 > intentos`, or `intentos >= 2` with every attempt failed
    firma     (`alert_kind=alertas_firma`, warning) `/evaluar` rejected a well-formed JWT that does not match: something
              SIGNED reached the endpoint. The four reasons that internet scanners produce (`MOTIVOS_SILENCIOSOS`) stay quiet

The layers are separate, like `metricas`: the rules are pure (`aviso_de_*`), the emission is a side effect that NEVER
raises (`avisar_*`: Sentry or Upstash failing logs one WARNING without data and the caller goes on as if nothing had
happened; a cancellation is not an `Exception` and propagates). Only state names and whole numbers travel: never an id,
an endpoint, a zone, a key, the signature, the body or the IP.

The 6-hour limit has two guards. The process memory (`_ultimas`, a monotonic clock) costs 0 commands. Then
`SET alertas:sentry:{tipo} 1 NX EX 21600` shares the limit between processes and restarts: created = emit; it already
existed = someone alerted within 6 hours. If Upstash cannot store the mark the alert goes out anyway (the
`upstash_no_disponible` alert happens precisely when no mark can be stored) and the memory stops the spam; on its return
Upstash may allow one more alert inside the same 6 hours. A healthy run costs 0 commands and 0 events.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sentry_sdk import capture_message

from app.core.upstash import UpstashRedis
from app.services.alertas import evaluacion, firma_qstash, metricas
from app.services.alertas.evaluacion import ResultadoEvaluacion, ResultadoEvaluacionSmn

logger = logging.getLogger(__name__)

PREFIJO = "alertas:sentry"
LIMITE_SEGUNDOS = 6 * 60 * 60  # 21.600 s: one alert per kind in this time

AVISO_CORRIDA = "corrida"  # the kind of alert; it ends the Redis key
AVISO_ENVIOS = "envios"
AVISO_FIRMA = "firma"

MOTIVO_SIN_DATOS_TOTAL = "sin_datos_total"
MOTIVO_SMN_SIN_DATOS = "smn_sin_datos"

# The closed lists of the rules. A signature reason is classified here on purpose (a test pins that the two sets cover
# exactly the reasons of `firma_qstash`): a new reason forces a decision about whether it is worth an email.
MOTIVOS_QUE_AVISAN = frozenset({
    firma_qstash.MOTIVO_CLAVE,
    firma_qstash.MOTIVO_SUB,
    firma_qstash.MOTIVO_BODY,
    firma_qstash.MOTIVO_ISS,
    firma_qstash.MOTIVO_EXP_NBF,
    firma_qstash.MOTIVO_ALGORITMO,
    firma_qstash.MOTIVO_CONFIG,
    firma_qstash.MOTIVO_INTERNO,
})
MOTIVOS_SILENCIOSOS = frozenset({
    firma_qstash.MOTIVO_SIN_CABECERA,
    firma_qstash.MOTIVO_FORMATO,
    firma_qstash.MOTIVO_FIRMA_LARGA,
    firma_qstash.MOTIVO_CUERPO,
})
_ESTADOS_DE_ERROR = frozenset({evaluacion.ESTADO_UPSTASH_NO_DISPONIBLE, evaluacion.ESTADO_SIN_VAPID})
_ESTADOS_CON_CONTADORES = frozenset({evaluacion.ESTADO_EVALUADA, evaluacion.ESTADO_EVALUADA_INCOMPLETA})

_ultimas: dict[str, float] = {}  # kind -> monotonic moment of the last decision (emitted or not) in this process


@dataclass(frozen=True)
class Aviso:
    """What one Sentry event carries. `tipo` is the kind (`AVISO_*`), which also names the Redis key of its limit."""

    tipo: str
    nivel: str
    mensaje: str
    tags: Mapping[str, str]
    extras: Mapping[str, int]
    fingerprint: tuple[str, ...]


def _monotonico() -> float:
    """The clock of the 6-hour limit. A function so the tests can move it."""
    return time.monotonic()


def reset_para_tests() -> None:
    _ultimas.clear()


# ---------------------------------------------------------------------------
# The rules (pure)
# ---------------------------------------------------------------------------


def _estado_conocido(estado: str) -> str:
    return estado if estado in metricas.ESTADOS_CONOCIDOS else metricas.ESTADO_DESCONOCIDO


def _motivo_de_corrida(tipo_corrida: str, resultado: ResultadoEvaluacion | ResultadoEvaluacionSmn) -> tuple[str, str] | None:
    """`(motivo, nivel)` of a failed run, or None. The first rule that matches wins."""
    estado = resultado.estado
    if estado in _ESTADOS_DE_ERROR:
        return estado, "error"
    if estado == evaluacion.ESTADO_EVALUADA_INCOMPLETA:
        return estado, "warning"
    if estado not in _ESTADOS_CON_CONTADORES:
        return None
    if tipo_corrida == metricas.TIPO_SMN:
        return (MOTIVO_SMN_SIN_DATOS, "warning") if resultado.smn.smn_sin_datos == 1 else None  # type: ignore[union-attr]
    if resultado.evaluadas > 0 and resultado.sin_datos == resultado.evaluadas:  # type: ignore[union-attr]
        return MOTIVO_SIN_DATOS_TOTAL, "warning"
    return None


def _extras_de_corrida(tipo_corrida: str, resultado: ResultadoEvaluacion | ResultadoEvaluacionSmn) -> dict[str, int]:
    nombres = ("smn_sin_datos", "smn_avisos", "smn_errores") if tipo_corrida == metricas.TIPO_SMN else (
        "evaluadas", "sin_datos", "errores", "diferidas")
    origen = resultado.smn if tipo_corrida == metricas.TIPO_SMN else resultado
    return {nombre: int(getattr(origen, nombre)) for nombre in nombres}


def aviso_de_corrida(tipo_corrida: str, resultado: ResultadoEvaluacion | ResultadoEvaluacionSmn) -> Aviso | None:
    """The alert of a run that failed (see the module docstring), or None."""
    falla = _motivo_de_corrida(tipo_corrida, resultado)
    if falla is None:
        return None
    motivo, nivel = falla
    return Aviso(
        tipo=AVISO_CORRIDA,
        nivel=nivel,
        mensaje=f"alertas: corrida fallida ({motivo})",
        tags={
            "alert_kind": "alertas_corrida",
            "corrida": tipo_corrida,
            "estado": _estado_conocido(resultado.estado),
            "motivo": motivo,
        },
        extras=_extras_de_corrida(tipo_corrida, resultado),
        fingerprint=("alertas-corrida", motivo),
    )


def aviso_de_envios(tipo_corrida: str, resultado: ResultadoEvaluacion | ResultadoEvaluacionSmn) -> Aviso | None:
    """The alert of a run whose sends failed above 20 %, or None (no sends, a run stopped by the operator, few attempts)."""
    envio = resultado.envio
    if envio is None or resultado.estado == evaluacion.ESTADO_APAGADO_A_MITAD:
        return None
    intentos = envio.enviados + envio.fallidos
    if not ((intentos >= 5 and envio.fallidos * 5 > intentos) or (intentos >= 2 and envio.fallidos == intentos)):
        return None
    return Aviso(
        tipo=AVISO_ENVIOS,
        nivel="error",
        mensaje="alertas: fallos de envío por encima del 20 %",
        tags={"alert_kind": "alertas_envios", "corrida": tipo_corrida, "estado": _estado_conocido(resultado.estado)},
        extras={
            "enviados": envio.enviados,
            "fallidos": envio.fallidos,
            "vencidos": envio.vencidos,
            "diferidos": envio.diferidos,
            "intentos": intentos,
            "porcentaje": envio.fallidos * 100 // intentos,
        },
        fingerprint=("alertas-envios",),
    )


def aviso_de_firma(motivo: str) -> Aviso | None:
    """The alert of a rejected signature whose reason is in `MOTIVOS_QUE_AVISAN`, or None. Only the fixed reason code
    travels: never the signature, the body or the IP (the SDK itself adds the request URL to an event)."""
    if motivo not in MOTIVOS_QUE_AVISAN:
        return None
    return Aviso(
        tipo=AVISO_FIRMA,
        nivel="warning",
        mensaje=f"alertas: /evaluar rechazó una firma de QStash ({motivo})",
        tags={"alert_kind": "alertas_firma", "motivo": motivo},
        extras={},
        fingerprint=("alertas-firma", motivo),
    )


# ---------------------------------------------------------------------------
# Emission (never raises)
# ---------------------------------------------------------------------------


async def _marca_nueva(redis: UpstashRedis | None, tipo: str) -> bool:
    """True if the alert must go out: the mark was created, or it could not be asked for (no Upstash, Upstash down)."""
    if redis is None:
        return True
    try:
        return await redis.set_nx(f"{PREFIJO}:{tipo}", "1", ex=LIMITE_SEGUNDOS)
    except Exception as exc:  # noqa: BLE001 - without the mark the alert still goes out; the memory stops the spam
        logger.warning("alertas: sentry mark could not be stored exc_type=%s", type(exc).__name__)
        return True


async def _emitir(redis: UpstashRedis | None, aviso: Aviso) -> None:
    ahora = _monotonico()
    previa = _ultimas.get(aviso.tipo)
    if previa is not None and ahora - previa < LIMITE_SEGUNDOS:
        return
    _ultimas[aviso.tipo] = ahora  # before the await: two requests at once cannot both pass the memory
    try:
        emitir = await _marca_nueva(redis, aviso.tipo)
    except asyncio.CancelledError:
        if previa is None:
            _ultimas.pop(aviso.tipo, None)
        else:
            _ultimas[aviso.tipo] = previa
        raise
    if emitir:
        capture_message(
            aviso.mensaje,
            level=aviso.nivel,
            tags=dict(aviso.tags),
            extras=dict(aviso.extras),
            fingerprint=list(aviso.fingerprint),
        )


def _no_se_pudo_emitir(exc: Exception) -> None:
    # Only the class of the error: a message could carry data, and these warnings are what the log export keeps.
    logger.warning("alertas: sentry alert could not be emitted exc_type=%s", type(exc).__name__)


async def _emitir_una_vez(redis: UpstashRedis | None, aviso: Aviso) -> None:
    """Emit `aviso` unless one of its kind went out in the last 6 hours. Never raises (a cancellation propagates)."""
    try:
        await _emitir(redis, aviso)
    except Exception as exc:  # noqa: BLE001 - alerting is a side effect: it never breaks the run or the response
        _no_se_pudo_emitir(exc)


async def _avisar(redis: UpstashRedis | None, derivar: Callable[[], Aviso | None]) -> None:
    try:
        aviso = derivar()
    except Exception as exc:  # noqa: BLE001 - a bug in a rule must not reach the run either
        _no_se_pudo_emitir(exc)
        return
    if aviso is not None:
        await _emitir_una_vez(redis, aviso)


async def avisar_corrida(
    redis: UpstashRedis | None, tipo_corrida: str, resultado: ResultadoEvaluacion | ResultadoEvaluacionSmn
) -> None:
    """Evaluate the alerts of a finished run (failed run, then failed sends) and emit what applies. Never raises."""
    await _avisar(redis, lambda: aviso_de_corrida(tipo_corrida, resultado))
    await _avisar(redis, lambda: aviso_de_envios(tipo_corrida, resultado))


async def avisar_upstash_no_disponible(redis: UpstashRedis | None, tipo_corrida: str) -> None:
    """Emit the `upstash_no_disponible` alert of a run that never started: the router answered `apagado` because the kill
    key could not be read with a sending flag ON (Upstash down or not configured). Same event as a run that ends in that
    state, same 6-hour limit (when Upstash is down the mark cannot be stored and the process memory stops the spam)."""
    resultado = ResultadoEvaluacionSmn if tipo_corrida == metricas.TIPO_SMN else ResultadoEvaluacion
    await _avisar(
        redis, lambda: aviso_de_corrida(tipo_corrida, resultado(estado=evaluacion.ESTADO_UPSTASH_NO_DISPONIBLE))
    )


async def avisar_firma_invalida(redis: UpstashRedis | None, motivo: str) -> None:
    """Emit the alert of a rejected signature, if its reason deserves one. Never raises."""
    await _avisar(redis, lambda: aviso_de_firma(motivo))
