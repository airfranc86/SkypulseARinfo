"""Daily counters of the push alerts, kept in Upstash for the admin panel (FRA-360, T11, part 1).

The Render logs of the Hobby plan last 7 days; these counters last 40. They are the numbers the runs already compute
(the HTTP response of `POST /api/alertas/evaluar`) plus the new subscriptions and the deletions asked for.

Shape: ONE Redis HASH per Argentine day, `alertas:metricas:{YYYY-MM-DD}`, with one field per counter:

    pronostico:corridas:{estado}   one per forecast run, by its final state (`evaluada`, `en_curso`, `sin_vapid`...); a state
                                   outside `ESTADOS_CONOCIDOS` is counted as `pronostico:corridas:desconocido`
    pronostico:{contador}          the sending counters of a forecast run that sent (`despacho.CONTADORES_ENVIO`) and its
                                   zone counters `sin_datos`, `errores` and `diferidas` (the signal of the Open-Meteo 429s)
    smn:corridas:{estado}          one per "SMN only" run, by its final state
    smn:{contador}                 the SMN counters (`despacho.CONTADORES_SMN`, `smn_avisos`...) and, when it sent,
                                   the sending counters of an SMN run
    suscripciones:altas            new subscriptions (a renewal or a change of zone is not an alta)
    suscripciones:bajas            deletions asked for through `POST /api/alertas/baja` that deleted something

The subscriptions deleted by the dispatch (gone, invalid or expired) are already `vencidos`. The counter names after the
prefix are EXACTLY the names of the HTTP response, so a panel maps one onto the other. Only whole numbers: never an id,
an endpoint, a zone or a key (the keys of the done-sets carry zones; these do not).

Why a hash per day and not a key per counter: a run writes only its counters different from zero (`HINCRBY`, atomic on
the server) and asks for the expiry ONCE per run (`EXPIRE ... NX`, 40 days, set by the first write of the day and never
stretched), so an SMN run without alerts costs 1 counting command plus the expiry; a key per counter would need its own
expiry per key, and the panel would have to know every name in advance (`HGETALL` reads a whole day in one command and
discovers new counters by itself). The hash is also what the Upstash console shows as one object.

Counting is a SIDE EFFECT of the run or the request that it describes: `contar_*` never raises. Upstash failing (or a
bug in this module) logs one WARNING without data and the caller goes on exactly as if nothing had happened; the first
failed command stops the counting (no 5 s per field on a dead Upstash). The routers count at the END of each path, with
the result already computed: the counting never sits between a run and its sends.

The day is the day of Argentina (fixed -03:00, the same offset `regla.py` and `despacho.py` use), not the UTC day: a run
at 23:30 in Argentina belongs to that day. This module never reads the wall clock: `ahora` is injected by the caller.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from app.core.upstash import UpstashRedis
from app.services.alertas import evaluacion
from app.services.alertas.despacho import CONTADORES_ENVIO, CONTADORES_SMN
from app.services.alertas.despacho_lluvia import CONTADORES_LLUVIA

logger = logging.getLogger(__name__)

PREFIJO = "alertas:metricas"
RETENCION_DIAS = 40
RETENCION_SEGUNDOS = RETENCION_DIAS * 24 * 60 * 60  # 3.456.000 s

TIPO_PRONOSTICO = "pronostico"  # the forecast run (`evaluacion.evaluar`)
TIPO_SMN = "smn"  # the "SMN only" run (`evaluacion.evaluar_smn`)

CAMPO_ALTAS = "suscripciones:altas"
CAMPO_BAJAS = "suscripciones:bajas"

# The states a run can end in: the closed list of the system (`apagado` is answered by the router and is not a run).
# The state becomes part of a field name, so only these reach it; any other is counted as `ESTADO_DESCONOCIDO`.
ESTADOS_CONOCIDOS = frozenset({
    evaluacion.ESTADO_EVALUADA,
    evaluacion.ESTADO_EVALUADA_INCOMPLETA,
    evaluacion.ESTADO_APAGADO_A_MITAD,
    evaluacion.ESTADO_EN_CURSO,
    evaluacion.ESTADO_FUERA_DE_VENTANA,
    evaluacion.ESTADO_SIN_VAPID,
    evaluacion.ESTADO_UPSTASH_NO_DISPONIBLE,
})
ESTADO_DESCONOCIDO = "desconocido"

# The counters of a run that are persisted, by their response name. Of the zone counters of the forecast run
# (`evaluacion.CONTADORES`) only these three are kept: `sin_datos`, `errores` and `diferidas` are the signal of the
# Open-Meteo 429s; the rest stay in the log line only. The SMN response has no field with these names (its own are
# `smn_sin_datos`, `smn_errores`), so the one set serves both kinds of run.
_CONTADORES_ZONA_PERSISTIDOS = ("sin_datos", "errores", "diferidas")
_CONTADORES_PERSISTIDOS = (
    frozenset(CONTADORES_ENVIO) | frozenset(CONTADORES_SMN) | frozenset(_CONTADORES_ZONA_PERSISTIDOS) | frozenset(CONTADORES_LLUVIA)
)
_MAX_LECTURAS_SIMULTANEAS = 10  # the fan-out of a range read is bounded, like the SCARDs of the evaluation

_AR = timezone(timedelta(hours=-3))  # Argentina has no DST; the same offset `regla.py` uses


class ResultadoDeCorrida(Protocol):
    """What a run hands back (`ResultadoEvaluacion` or `ResultadoEvaluacionSmn`): its state and its response."""

    estado: str

    def como_respuesta(self) -> dict[str, str | int]: ...


# ---------------------------------------------------------------------------
# Keys and fields (pure)
# ---------------------------------------------------------------------------


def dia_de(ahora: datetime) -> date:
    """The Argentine day of `ahora`. A naive `ahora` is refused: it would be read in the server's time zone."""
    if ahora.tzinfo is None or ahora.utcoffset() is None:
        raise ValueError("ahora needs a time zone")
    return ahora.astimezone(_AR).date()


def clave_del_dia(dia: date) -> str:
    return f"{PREFIJO}:{dia.isoformat()}"


def incrementos_de_corrida(tipo: str, resultado: ResultadoDeCorrida) -> dict[str, int]:
    """The fields a run adds to its day: its state (always; one outside `ESTADOS_CONOCIDOS` is `desconocido`, never
    its own text) and its persisted counters different from zero, in the order of the response. A `bool` is not a
    counter. Pure: nothing is written here."""
    estado = resultado.estado if resultado.estado in ESTADOS_CONOCIDOS else ESTADO_DESCONOCIDO
    campos = {f"{tipo}:corridas:{estado}": 1}
    for nombre, valor in resultado.como_respuesta().items():
        if nombre in _CONTADORES_PERSISTIDOS and isinstance(valor, int) and not isinstance(valor, bool) and valor > 0:
            campos[f"{tipo}:{nombre}"] = valor
    return campos


# ---------------------------------------------------------------------------
# Writing (never raises)
# ---------------------------------------------------------------------------


async def _registrar(redis: UpstashRedis, ahora: datetime, campos: Mapping[str, int]) -> None:
    """One HINCRBY per field, then the expiry of the day (only if the key still has none). The key exists after the
    first increment, so the EXPIRE has something to attach to."""
    clave = clave_del_dia(dia_de(ahora))
    for campo, valor in campos.items():
        await redis.hincrby(clave, campo, valor)
    await redis.expire_si_falta(clave, RETENCION_SEGUNDOS)


async def _contar(redis: UpstashRedis, ahora: datetime, campos: Mapping[str, int]) -> None:
    try:
        await _registrar(redis, ahora, campos)
    except Exception as exc:  # noqa: BLE001 - counting is a side effect: it never breaks what it counts (a cancellation is not an Exception: it propagates)
        # Only the class of the error: a message could carry a key, and these warnings are what the log export keeps.
        logger.warning("alertas: metrics could not be recorded exc_type=%s", type(exc).__name__)


async def contar_corrida(redis: UpstashRedis, tipo: str, resultado: ResultadoDeCorrida, ahora: datetime) -> None:
    """Count one run of `tipo` (`TIPO_PRONOSTICO` or `TIPO_SMN`) on the Argentine day of `ahora`. Never raises."""
    try:
        campos = incrementos_de_corrida(tipo, resultado)
    except Exception as exc:  # noqa: BLE001 - a bug here must not reach the run either
        logger.warning("alertas: metrics could not be recorded exc_type=%s", type(exc).__name__)
        return
    await _contar(redis, ahora, campos)


async def contar_alta(redis: UpstashRedis, ahora: datetime) -> None:
    """Count one NEW subscription. Never raises."""
    await _contar(redis, ahora, {CAMPO_ALTAS: 1})


async def contar_baja(redis: UpstashRedis, ahora: datetime) -> None:
    """Count one deletion asked for by the person (that deleted something). Never raises."""
    await _contar(redis, ahora, {CAMPO_BAJAS: 1})


# ---------------------------------------------------------------------------
# Reading (for the admin panel)
# ---------------------------------------------------------------------------


def _como_enteros(clave: str, campos: Mapping[str, str]) -> dict[str, int]:
    """The fields of a day as integers. A value that is not a number is skipped with a WARNING (the field name is not
    sensitive): one odd field must not hide the rest of the day."""
    contadores: dict[str, int] = {}
    for campo, valor in campos.items():
        try:
            contadores[campo] = int(valor)
        except (TypeError, ValueError):
            logger.warning("alertas: metrics field is not a number key=%s field=%s", clave, campo)
    return contadores


async def leer_dia(redis: UpstashRedis, dia: date) -> dict[str, int]:
    """The counters of one day (one HGETALL). A day without data is an empty dict.

    Raises:
        UpstashUnavailableError: Upstash did not answer or answered something odd.
    """
    clave = clave_del_dia(dia)
    return _como_enteros(clave, await redis.hgetall(clave))


async def leer_rango(redis: UpstashRedis, desde: date, hasta: date) -> dict[str, dict[str, int]]:
    """The counters of every day from `desde` to `hasta` (both included), keyed by ISO day, in order; the days without
    data are empty dicts. One HGETALL per day, at most `_MAX_LECTURAS_SIMULTANEAS` in flight.

    Raises:
        ValueError: `hasta` is before `desde`, or the range is longer than the retention (`RETENCION_DIAS`).
        UpstashUnavailableError: Upstash did not answer or answered something odd (for any day).
    """
    dias = (hasta - desde).days + 1
    if dias < 1:
        raise ValueError("hasta is before desde")
    if dias > RETENCION_DIAS:
        raise ValueError(f"a range is at most {RETENCION_DIAS} days")
    fechas = [desde + timedelta(days=i) for i in range(dias)]
    semaforo = asyncio.Semaphore(_MAX_LECTURAS_SIMULTANEAS)

    async def leer(dia: date) -> dict[str, int]:
        async with semaforo:
            return await leer_dia(redis, dia)

    lecturas = await asyncio.gather(*(leer(dia) for dia in fechas), return_exceptions=True)
    for lectura in lecturas:
        if isinstance(lectura, BaseException):
            raise lectura  # every read finished before this: no call is left running
    return {dia.isoformat(): contadores for dia, contadores in zip(fechas, lecturas)}  # type: ignore[misc]
