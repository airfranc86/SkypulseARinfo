"""Scheduled alert evaluation, DRY RUN (FRA-355, PR5b).

`POST /api/alertas/evaluar` calls `evaluar(redis, ahora)` after QStash's signature was verified and the switch was
read. A run:

1. refuses a naive `ahora` (the rule would read it in the server's time zone) and looks up the review window
   (`regla.ventana`): outside the review hours and in the silence (22 to 7 h) the state is `fuera_de_ventana`, and
   neither Upstash nor Open-Meteo is touched;
2. takes the run lock `alertas:lock:evaluar` (SET NX EX): taken = `en_curso`; Upstash failing = `upstash_no_disponible`
   (a 200 either way, so QStash does not retry). The lock is NEVER released: a plain DEL could free the lock of
   another run; it expires by itself, and it outlasts both the QStash signature and the run deadline;
3. reads the zones that have subscribers (`alertas:zonas` ∩ the catalog, then SCARD of each zone's set, at most 10 at a
   time: only the COUNT, never an id). The zones with more subscribers go first (ties: catalog order), at most
   `alertas_max_zonas_por_corrida` per run; the rest are `diferidas`;
4. asks ECMWF for each zone (`pronostico.pronostico_de_zona`) UNDER THE FIXED JOB CLIENT KEY, so the global Open-Meteo
   budget still applies, and applies the storm rule. A storm in fresh data is a storm even if some hour has a hole;
   "no storm" is concluded only if every hour of the window has BOTH `weather_code` and `cape`; otherwise, and for any
   data that is missing or stale, the zone is `sin_datos`, never "no storm". An unexpected exception (also inside the
   rule) is an `errores` zone, not an exception of the run;
5. reads the kill key `alertas:apagado` again before EVERY zone (`interruptor.clave_de_apagado_ausente`, fail
   closed): present or unreadable stops the run with `apagado_a_mitad`. The zones not reached are `diferidas`;
6. stops at the run deadline (`alertas_plazo_corrida_segundos`, below the lock expiry): state `evaluada_incompleta`,
   the zones not reached (also the one in flight) are `diferidas`, not `sin_datos`;
7. counts and logs ONE line with the counters (a WARNING when there is `sin_datos`, `errores` or a deadline).

The result has two layers. The state and the integer counters (`CONTADORES`) are what the response and the log
carry. `ResultadoEvaluacion.zonas` is the per-zone detail for the CALLER (the sender of the next stage): it never
reaches the response or the log.

It never sends a notification (this module does not import the sender), never deletes or prunes anything, never reads
a subscription record and never reads the wall clock: `ahora` is injected by the caller and carries a time zone.

FOR THE SENDER (5c): send only when `interruptor.envio_activo` is true, read again right before each send. NEVER
decide it from `evaluacion_permitida`: that one also lets the DRY RUN evaluate, which must send nothing.

Zones are evaluated one after the other inside the request, which is fine for a handful of zones and bounded by the
deadline. With many zones this becomes `BackgroundTasks` (or several calls) so the answer to QStash stays fast; that is
a decision for when there are many zones, not for this stage.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.core.client_context import ALERTAS_JOB_CLIENT_KEY, con_clave_de_cliente
from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas import interruptor, pronostico, regla
from app.services.alertas.regla import ResultadoRegla
from app.services.alertas.zonas import ZONAS, Zona

logger = logging.getLogger(__name__)

CLAVE_LOCK = "alertas:lock:evaluar"
CLAVE_ZONAS = "alertas:zonas"  # set of slugs with at least one subscriber (written by `suscripcion.alta`)

ESTADO_APAGADO = "apagado"  # answered by the router: both flags off, kill key present or unreadable
ESTADO_EVALUADA = "evaluada"
ESTADO_FUERA_DE_VENTANA = "fuera_de_ventana"
ESTADO_EN_CURSO = "en_curso"
ESTADO_UPSTASH_NO_DISPONIBLE = "upstash_no_disponible"
ESTADO_APAGADO_A_MITAD = "apagado_a_mitad"
ESTADO_EVALUADA_INCOMPLETA = "evaluada_incompleta"  # the run deadline hit: the zones not reached are `diferidas`

# The counters that the HTTP response may carry next to `estado` (an explicit whitelist: a new field of the result
# never reaches the response unless it is added here). Zones, never subscribers.
CONTADORES = (
    "zonas_con_suscriptores",
    "evaluadas",
    "con_tormenta",
    "sin_tormenta",
    "sin_datos",
    "errores",
    "diferidas",
    "desconocidas",
)

# Only a run that got as far as listing the zones has counters worth sending back.
_ESTADOS_CON_CONTADORES = frozenset({ESTADO_EVALUADA, ESTADO_EVALUADA_INCOMPLETA, ESTADO_APAGADO_A_MITAD})

# What happened to each zone of the catalog that has an entry in `alertas:zonas`.
VEREDICTO_CON_TORMENTA = "con_tormenta"
VEREDICTO_SIN_TORMENTA = "sin_tormenta"
VEREDICTO_SIN_DATOS = "sin_datos"  # no usable data: NOT "no storm"
VEREDICTO_ERROR = "error"  # unexpected exception while evaluating it
VEREDICTO_DIFERIDA = "diferida"  # not evaluated in this run (over the cap, deadline, or the run was stopped)
VEREDICTO_SIN_SUSCRIPTORES = "sin_suscriptores"  # listed in `alertas:zonas` but its subscriber set is empty

AVISO_HOY = "hoy"
AVISO_MANANA = "manana"

_AR = timezone(timedelta(hours=-3))  # Argentina has no DST; the same offset `regla.py` uses
_MAX_SCARD_SIMULTANEOS = 10  # the fan-out over the zones is bounded: at most this many SCARDs in flight


def clave_de_zona(slug: str) -> str:
    """The set of subscriber ids of a zone (written by `suscripcion.alta`). Only its size is ever read here."""
    return f"alertas:zona:{slug}"


@dataclass(frozen=True)
class ZonaEvaluada:
    """What the run found out about one zone: the detail the sender of the next stage (5c) needs.

    It is for the CALLER of `evaluar` only. It never reaches the HTTP response or the logs: those carry the counters.
    `revision`, `aviso`, `fecha_objetivo` and `ventana` are set only for `con_tormenta`: the rule's result, the kind of
    notice ("hoy" for the revisions of 7 to 19 h, "manana" for the one at 21 h), the date the notice is about (what
    the dedupe and the push Topic need) and the review window in epoch seconds.
    """

    slug: str
    veredicto: str
    suscriptores: int  # SCARD of the zone's subscriber set; 0 lets the caller prune `alertas:zonas`
    revision: ResultadoRegla | None = None
    aviso: str | None = None
    fecha_objetivo: date | None = None
    ventana: tuple[int, int] | None = None


@dataclass(frozen=True)
class ResultadoEvaluacion:
    """What happened in a run: `estado`, integer counters (zones, never subscribers) and, for the caller, `zonas`."""

    estado: str
    zonas_con_suscriptores: int = 0  # known zones with at least one subscriber (before the cap)
    evaluadas: int = 0  # zones asked about in this run: con_tormenta + sin_tormenta + sin_datos + errores
    con_tormenta: int = 0
    sin_tormenta: int = 0
    sin_datos: int = 0  # no usable data (failed, refused or stale): NOT "no storm"
    errores: int = 0  # unexpected exception while evaluating the zone (a bug, not a lack of data)
    diferidas: int = 0  # with subscribers but not evaluated in this run: over the cap, deadline or stopped run
    desconocidas: int = 0  # slugs in `alertas:zonas` that are not in the catalog (ignored, never pruned)
    # Per-zone detail for the caller (5c). Not part of the equality, not in the repr, never in the response or the log.
    zonas: tuple[ZonaEvaluada, ...] = field(default=(), repr=False, compare=False)

    def como_respuesta(self) -> dict[str, str | int]:
        """The JSON the endpoint answers: the state and, if the run looked at the zones, the counters. Nothing else."""
        respuesta: dict[str, str | int] = {"estado": self.estado}
        if self.estado in _ESTADOS_CON_CONTADORES:
            respuesta.update({nombre: getattr(self, nombre) for nombre in CONTADORES})
        return respuesta


@dataclass(frozen=True)
class _ZonaConocida:
    """A catalog zone listed in `alertas:zonas`, with the size of its subscriber set."""

    zona: Zona
    indice: int  # position in the catalog: the tie-break of the order
    suscriptores: int


# ---------------------------------------------------------------------------
# The switch: both flags and the kill key
# ---------------------------------------------------------------------------


async def evaluacion_permitida(redis: UpstashRedis | None) -> bool:
    """True if the evaluation may run: `alertas_envio_activo` OR `alertas_evaluar_en_seco` is on, AND the kill key
    `alertas:apagado` does not exist (unreadable = off). With both flags off Upstash is not touched.

    Either flag only lets the run EVALUATE; in the PR5b nothing is ever sent whichever is on. The sender of the next
    stage must NOT use this to decide whether to send (it also allows the dry run): it uses `interruptor.envio_activo`.
    """
    if not (settings.alertas_envio_activo or settings.alertas_evaluar_en_seco):
        return False
    return await interruptor.clave_de_apagado_ausente(redis)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _cerrar(resultado: ResultadoEvaluacion) -> ResultadoEvaluacion:
    """Log the one line of the run (state and counters only; a WARNING if anything was off) and hand the result back."""
    algo_fallo = resultado.sin_datos or resultado.errores or resultado.estado == ESTADO_EVALUADA_INCOMPLETA
    logger.log(
        logging.WARNING if algo_fallo else logging.INFO,
        "alertas: evaluation estado=%s zonas_con_suscriptores=%d evaluadas=%d con_tormenta=%d sin_tormenta=%d "
        "sin_datos=%d errores=%d diferidas=%d desconocidas=%d",
        resultado.estado,
        resultado.zonas_con_suscriptores,
        resultado.evaluadas,
        resultado.con_tormenta,
        resultado.sin_tormenta,
        resultado.sin_datos,
        resultado.errores,
        resultado.diferidas,
        resultado.desconocidas,
    )
    return resultado


async def _listar_zonas(redis: UpstashRedis) -> tuple[list[_ZonaConocida], int]:
    """The known zones of `alertas:zonas` sorted by (-subscribers, catalog index), and how many slugs are unknown.

    Reads set sizes only; a slug that is not in the catalog is counted and left alone.
    """
    slugs = await redis.smembers(CLAVE_ZONAS)
    conocidas = [(indice, zona) for indice, zona in enumerate(ZONAS) if zona.slug in slugs]
    semaforo = asyncio.Semaphore(_MAX_SCARD_SIMULTANEOS)

    async def contar(zona: Zona) -> int:
        async with semaforo:
            return await redis.scard(clave_de_zona(zona.slug))

    cuentas = await asyncio.gather(*(contar(zona) for _, zona in conocidas), return_exceptions=True)
    for cuenta in cuentas:
        if isinstance(cuenta, BaseException):
            raise cuenta  # every SCARD finished before this: no call is left running
    listadas = [
        _ZonaConocida(zona=zona, indice=indice, suscriptores=cuenta)
        for (indice, zona), cuenta in zip(conocidas, cuentas)
    ]
    listadas.sort(key=lambda z: (-z.suscriptores, z.indice))
    return listadas, len(slugs) - len(conocidas)


def _aviso_de(ahora: datetime, ventana: tuple[int, int]) -> tuple[str, date]:
    """The kind of notice of the review and the date it is about: the 21 h review looks at tomorrow, the others at today."""
    fecha = datetime.fromtimestamp(ventana[0], _AR).date()
    return (AVISO_MANANA if fecha > ahora.astimezone(_AR).date() else AVISO_HOY), fecha


async def _evaluar_zona(
    conocida: _ZonaConocida, ahora: datetime, ventana: tuple[int, int], aviso: str, fecha: date
) -> ZonaEvaluada:
    zona = conocida.zona

    def veredicto(valor: str, **detalle) -> ZonaEvaluada:
        return ZonaEvaluada(slug=zona.slug, veredicto=valor, suscriptores=conocida.suscriptores, **detalle)

    try:
        serie = await pronostico.pronostico_de_zona(zona, ahora)
        if serie is None:
            return veredicto(VEREDICTO_SIN_DATOS)
        revision = regla.evaluar_revision(serie, ahora)
        if revision is None:  # cannot happen (the window exists), but never read it as calm
            return veredicto(VEREDICTO_SIN_DATOS)
        if revision.hay_tormenta:  # positive evidence counts even if some other hour has a hole
            return veredicto(VEREDICTO_CON_TORMENTA, revision=revision, aviso=aviso, fecha_objetivo=fecha, ventana=ventana)
        if pronostico.cubre_ventana(serie, ventana):
            return veredicto(VEREDICTO_SIN_TORMENTA)
        return veredicto(VEREDICTO_SIN_DATOS)  # no storm in the data we have, but the data has holes: not "calm"
    except Exception:  # noqa: BLE001 - one zone failing must not hide the others, and it is NOT "no storm"
        logger.exception("alertas: unexpected error evaluating a zone zone=%s", zona.slug)
        return veredicto(VEREDICTO_ERROR)


def _resultado(estado: str, zonas: tuple[ZonaEvaluada, ...], desconocidas: int) -> ResultadoEvaluacion:
    cuenta = Counter(z.veredicto for z in zonas)
    evaluadas = sum(
        cuenta[v] for v in (VEREDICTO_CON_TORMENTA, VEREDICTO_SIN_TORMENTA, VEREDICTO_SIN_DATOS, VEREDICTO_ERROR)
    )
    diferidas = cuenta[VEREDICTO_DIFERIDA]
    return ResultadoEvaluacion(
        estado=estado,
        zonas_con_suscriptores=evaluadas + diferidas,
        evaluadas=evaluadas,
        con_tormenta=cuenta[VEREDICTO_CON_TORMENTA],
        sin_tormenta=cuenta[VEREDICTO_SIN_TORMENTA],
        sin_datos=cuenta[VEREDICTO_SIN_DATOS],
        errores=cuenta[VEREDICTO_ERROR],
        diferidas=diferidas,
        desconocidas=desconocidas,
        zonas=zonas,
    )


def _sin_evaluar(conocida: _ZonaConocida, veredicto: str) -> ZonaEvaluada:
    return ZonaEvaluada(slug=conocida.zona.slug, veredicto=veredicto, suscriptores=conocida.suscriptores)


async def evaluar(redis: UpstashRedis, ahora: datetime) -> ResultadoEvaluacion:
    """Evaluate the review of `ahora` for every zone with subscribers and count the results. Sends nothing.

    Raises:
        ValueError: `ahora` has no time zone (nothing is touched).
    """
    pronostico.exigir_hora_con_zona(ahora)
    ventana = regla.ventana(ahora)
    if ventana is None:
        return _cerrar(ResultadoEvaluacion(estado=ESTADO_FUERA_DE_VENTANA))

    try:
        lock_tomado = await redis.set_nx(CLAVE_LOCK, uuid.uuid4().hex, ex=settings.alertas_lock_ttl_segundos)
    except UpstashUnavailableError:
        logger.warning("alertas: Upstash did not answer taking the run lock; nothing is evaluated")
        return _cerrar(ResultadoEvaluacion(estado=ESTADO_UPSTASH_NO_DISPONIBLE))
    if not lock_tomado:
        return _cerrar(ResultadoEvaluacion(estado=ESTADO_EN_CURSO))
    # The lock stays: it is not released with DEL (that could free another run's lock), it expires by itself.

    try:
        listadas, desconocidas = await _listar_zonas(redis)
    except UpstashUnavailableError:
        logger.warning("alertas: Upstash did not answer listing the zones; nothing is evaluated")
        return _cerrar(ResultadoEvaluacion(estado=ESTADO_UPSTASH_NO_DISPONIBLE))

    con_suscriptores = [z for z in listadas if z.suscriptores > 0]
    a_evaluar = con_suscriptores[: settings.alertas_max_zonas_por_corrida]
    sobre_el_tope = con_suscriptores[len(a_evaluar):]
    aviso, fecha = _aviso_de(ahora, ventana)

    estado = ESTADO_EVALUADA
    hechas: list[ZonaEvaluada] = []
    # The fixed job key keeps the GLOBAL Open-Meteo cap applying (no key would switch the whole budget off).
    with con_clave_de_cliente(ALERTAS_JOB_CLIENT_KEY):
        try:
            async with asyncio.timeout(settings.alertas_plazo_corrida_segundos):
                for conocida in a_evaluar:
                    if not await interruptor.clave_de_apagado_ausente(redis):
                        estado = ESTADO_APAGADO_A_MITAD
                        break
                    hechas.append(await _evaluar_zona(conocida, ahora, ventana, aviso, fecha))
        except TimeoutError:
            estado = ESTADO_EVALUADA_INCOMPLETA  # the zone in flight was cancelled: it is not in `hechas`

    zonas = (
        tuple(hechas)
        + tuple(_sin_evaluar(z, VEREDICTO_DIFERIDA) for z in a_evaluar[len(hechas):])  # deadline or stopped run
        + tuple(_sin_evaluar(z, VEREDICTO_DIFERIDA) for z in sobre_el_tope)  # over the cap
        + tuple(_sin_evaluar(z, VEREDICTO_SIN_SUSCRIPTORES) for z in listadas if z.suscriptores == 0)
    )
    return _cerrar(_resultado(estado, zonas, desconocidas))
