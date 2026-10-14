"""Scheduled alert evaluation, and the sending when asked to (FRA-355, PR5b and PR5c).

`POST /api/alertas/evaluar` calls `evaluar(redis, ahora, enviar=...)` after QStash's signature was verified and the
switch was read. A run:

1. refuses a naive `ahora` (the rule would read it in the server's time zone) and looks up the review window
   (`regla.ventana`): outside the review hours and in the silence (22 to 7 h) the state is `fuera_de_ventana`, and
   neither Upstash nor Open-Meteo is touched;
2. if it must SEND, loads the VAPID key; without a usable one the state is `sin_vapid` and nothing else happens;
3. takes the run lock `alertas:lock:evaluar` (SET NX EX): taken = `en_curso`; Upstash failing = `upstash_no_disponible`
   (a 200 either way, so QStash does not retry). The lock is NEVER released: a plain DEL could free the lock of
   another run; it expires by itself, and it outlasts both the QStash signature and the run deadline;
4. reads the zones that have subscribers (`alertas:zonas` ∩ the catalog, then SCARD of each zone's set, at most 10 at a
   time: only the COUNT, never an id). The zones with more subscribers go first (ties: catalog order), at most
   `alertas_max_zonas_por_corrida` per run; the rest are `diferidas`;
5. asks ECMWF for each zone (`pronostico.pronostico_de_zona`) UNDER THE FIXED JOB CLIENT KEY, so the global Open-Meteo
   budget still applies, and applies the storm rule. A storm in fresh data is a storm even if some hour has a hole;
   "no storm" is concluded only if every hour of the window has BOTH `weather_code` and `cape`; otherwise, and for any
   data that is missing or stale, the zone is `sin_datos`, never "no storm". An unexpected exception (also inside the
   rule) is an `errores` zone, not an exception of the run;
6. the kill key `alertas:apagado` (fail closed) is read by the router at the start of the run and, when the run sends,
   once more before the dispatch starts (`despacho.corte_por_interruptor`) and before every batch of sends; present or
   unreadable stops the sending with `apagado_a_mitad`. Evaluating the zones (read-only) does not read it per zone;
7. stops at the run deadline (`alertas_plazo_corrida_segundos`, below the lock expiry): state `evaluada_incompleta`,
   the zones not reached (also the one in flight) are `diferidas`, not `sin_datos`;
8. counts and logs ONE line with the counters (a WARNING when there is `sin_datos`, `errores`, a failed send or a
   deadline).

When the run SENDS (`enviar=True`, which only the router sets, and only when `interruptor.envio_activo` is true):

- the zones are evaluated FIRST (read-only); then the zones found with a storm are prepared (their text, members and the
  ids already reached today: reads only) and dispatched one after the other by `despacho` (batches of sends, each batch
  recorded in the zone's done-set before the next one; see that module). Preparing them all first lets the time left be
  shared among the zones that still have something to send, in proportion to their pendientes, so one big zone cannot
  starve the rest. If the run is cut while evaluating (kill key, deadline) nothing is sent: the storms found stay pending;
- the freshness of each forecast is judged against the clock of that moment (`reloj`), not against `ahora`, and the
  run never outlasts 22:00 in Argentina;
- the zones left `sin_datos` get ONE second pass (evaluated and dispatched the same way), after a short wait
  (`despacho.ESPERA_SEGUNDA_PASADA_SEGUNDOS`, longer than the cache's memory of a failed call), through the same budget,
  freshness, kill key and deadline. The final result of a zone is the one of the second pass, and the counters show it. If
  the deadline leaves no room for the second pass the zones stay `sin_datos` and the state is `evaluada_incompleta`;
- the subscriptions that are gone or invalid are deleted at the END (the circuit breaker of `despacho` decides with the
  totals of the whole run); the zones left with an empty subscriber set are taken out of `alertas:zonas`. Unknown slugs
  are never pruned. A run stopped by the kill key prunes nothing.

A dry run (`enviar=False`, the default) sends nothing, takes no mark, reads no subscription, waits for nothing and
prunes nothing: it only counts. NEVER decide to send from `evaluacion_permitida` (it also allows the dry run).

The result has two layers. The state and the integer counters (`CONTADORES`, plus `despacho.CONTADORES_ENVIO` for a
run that sends) are what the response and the log carry. `ResultadoEvaluacion.zonas` is the per-zone detail for the
CALLER: it never reaches the response or the log.

This module does not import the sender (`despacho` does) and never reads the wall clock: `ahora` is injected by the
caller and carries a time zone; the run deadline is `despacho.Plazo`.

Zones are evaluated one after the other inside the request, which is fine for a handful of zones and bounded by the
deadline. With many zones this becomes `BackgroundTasks` (or several calls) so the answer to QStash stays fast; that is
a decision for when there are many zones, not for this stage.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.core.client_context import ALERTAS_JOB_CLIENT_KEY, con_clave_de_cliente
from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas import despacho, interruptor, pronostico, regla
from app.services.alertas import suscripcion as svc
from app.services.alertas.despacho import AVISO_HOY, AVISO_MANANA, ResumenEnvio
from app.services.alertas.regla import ResultadoRegla
from app.services.alertas.zonas import ZONAS, Zona

logger = logging.getLogger(__name__)

CLAVE_LOCK = "alertas:lock:evaluar"
CLAVE_ZONAS = svc.CLAVE_ZONAS  # set of slugs with at least one subscriber (written by `suscripcion.alta`)

ESTADO_APAGADO = "apagado"  # answered by the router: both flags off, kill key present or unreadable
ESTADO_EVALUADA = "evaluada"
ESTADO_FUERA_DE_VENTANA = "fuera_de_ventana"
ESTADO_EN_CURSO = "en_curso"
ESTADO_UPSTASH_NO_DISPONIBLE = "upstash_no_disponible"
ESTADO_APAGADO_A_MITAD = "apagado_a_mitad"
ESTADO_EVALUADA_INCOMPLETA = "evaluada_incompleta"  # the run deadline hit: the zones not reached are `diferidas`
ESTADO_SIN_VAPID = "sin_vapid"  # asked to send but there is no usable VAPID key: nothing was touched

# The counters that the HTTP response may carry next to `estado` (an explicit whitelist: a new field of the result
# never reaches the response unless it is added here). Zones, never subscribers. A run that sends adds
# `despacho.CONTADORES_ENVIO` (also whole numbers: never ids, endpoints or texts).
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
VEREDICTO_ERROR = "error"  # unexpected exception while evaluating it, or a storm that could not be dispatched
VEREDICTO_DIFERIDA = "diferida"  # not evaluated in this run (over the cap, deadline, or the run was stopped)
VEREDICTO_SIN_SUSCRIPTORES = "sin_suscriptores"  # listed in `alertas:zonas` but its subscriber set is empty

_AR = timezone(timedelta(hours=-3))  # Argentina has no DST; the same offset `regla.py` uses
_MAX_SCARD_SIMULTANEOS = 10  # the fan-out over the zones is bounded: at most this many SCARDs in flight


def clave_de_zona(slug: str) -> str:
    """The set of subscriber ids of a zone (written by `suscripcion.alta`). Only its size is read here."""
    return svc.clave_de_zona(slug)


@dataclass(frozen=True)
class ZonaEvaluada:
    """What the run found out about one zone: the detail the caller of `evaluar` can use.

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
    # What the sending did. None for a dry run (and for a run that never got as far as the zones).
    envio: ResumenEnvio | None = None
    # Per-zone detail for the caller. Not part of the equality, not in the repr, never in the response or the log.
    zonas: tuple[ZonaEvaluada, ...] = field(default=(), repr=False, compare=False)

    def como_respuesta(self) -> dict[str, str | int]:
        """The JSON the endpoint answers: the state and, if the run looked at the zones, the counters. Nothing else."""
        respuesta: dict[str, str | int] = {"estado": self.estado}
        if self.estado in _ESTADOS_CON_CONTADORES:
            respuesta.update({nombre: getattr(self, nombre) for nombre in CONTADORES})
            if self.envio is not None:
                respuesta.update(self.envio.como_respuesta())
        return respuesta


@dataclass(frozen=True)
class _ZonaConocida:
    """A catalog zone listed in `alertas:zonas`, with the size of its subscriber set."""

    zona: Zona
    indice: int  # position in the catalog: the tie-break of the order
    suscriptores: int


@dataclass(frozen=True)
class _Corrida:
    """What every zone of one run shares."""

    redis: UpstashRedis
    ahora: datetime
    ventana: tuple[int, int]
    aviso: str
    fecha: date
    plazo: despacho.Plazo
    vapid: despacho.ClaveVapid | None  # None = dry run
    reloj: Callable[[], datetime]  # the wall clock, read once per zone (the freshness reference and the notice TTL)
    disyuntor: despacho.DisyuntorDeBajas  # one per run: the memory of "too many gone subscriptions in one batch"

    @property
    def enviar(self) -> bool:
        return self.vapid is not None


# ---------------------------------------------------------------------------
# The switch: both flags and the kill key
# ---------------------------------------------------------------------------


async def evaluacion_permitida(redis: UpstashRedis | None) -> bool:
    """True if the evaluation may run: `alertas_envio_activo` OR `alertas_evaluar_en_seco` is on, AND the kill key
    `alertas:apagado` does not exist (unreadable = off). With both flags off Upstash is not touched.

    Either flag only lets the run EVALUATE. The router decides whether the run also SENDS with `interruptor.envio_activo`
    and with nothing else: this one also allows the dry run, which must send nothing.
    """
    if not (settings.alertas_envio_activo or settings.alertas_evaluar_en_seco):
        return False
    return await interruptor.clave_de_apagado_ausente(redis)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _cerrar(resultado: ResultadoEvaluacion) -> ResultadoEvaluacion:
    """Log the one line of the run (state and counters only; a WARNING if anything was off) and hand the result back."""
    envio = resultado.envio
    algo_fallo = (
        resultado.sin_datos
        or resultado.errores
        or resultado.estado in (ESTADO_EVALUADA_INCOMPLETA, ESTADO_SIN_VAPID)
        or (envio is not None and envio.fallidos)
    )
    formato = (
        "alertas: evaluation estado=%s zonas_con_suscriptores=%d evaluadas=%d con_tormenta=%d sin_tormenta=%d "
        "sin_datos=%d errores=%d diferidas=%d desconocidas=%d"
    )
    argumentos: list[str | int] = [
        resultado.estado,
        resultado.zonas_con_suscriptores,
        resultado.evaluadas,
        resultado.con_tormenta,
        resultado.sin_tormenta,
        resultado.sin_datos,
        resultado.errores,
        resultado.diferidas,
        resultado.desconocidas,
    ]
    if envio is not None:
        formato += " " + " ".join(f"{nombre}=%d" for nombre in despacho.CONTADORES_ENVIO)
        argumentos += [getattr(envio, nombre) for nombre in despacho.CONTADORES_ENVIO]
    logger.log(logging.WARNING if algo_fallo else logging.INFO, formato, *argumentos)
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
    conocida: _ZonaConocida, ahora: datetime, ventana: tuple[int, int], aviso: str, fecha: date, referencia: datetime
) -> ZonaEvaluada:
    zona = conocida.zona

    def veredicto(valor: str, **detalle) -> ZonaEvaluada:
        return ZonaEvaluada(slug=zona.slug, veredicto=valor, suscriptores=conocida.suscriptores, **detalle)

    try:
        serie = await pronostico.pronostico_de_zona(zona, ahora, referencia)
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
        # The traceback says what broke; the zone is not named (a zone with subscribers is not for the logs).
        logger.exception("alertas: unexpected error evaluating a zone")
        return veredicto(VEREDICTO_ERROR)


def _resultado(
    estado: str, zonas: tuple[ZonaEvaluada, ...], desconocidas: int, envio: ResumenEnvio | None
) -> ResultadoEvaluacion:
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
        envio=envio,
        zonas=zonas,
    )


def _sin_evaluar(conocida: _ZonaConocida, veredicto: str) -> ZonaEvaluada:
    return ZonaEvaluada(slug=conocida.zona.slug, veredicto=veredicto, suscriptores=conocida.suscriptores)


async def _evaluar_paso(conocida: _ZonaConocida, corrida: _Corrida) -> tuple[ZonaEvaluada | None, str | None]:
    """One zone's evaluation: the deadline check, then the forecast and the rule (bounded by the run deadline). Read-only.
    It does NOT read the kill key: evaluating sends nothing, and the key is read before the dispatch starts (`_pasada`) and
    before every batch. Returns the verdict (None if the run was cut before it was known) and why the run stops."""
    if corrida.plazo.vencido():
        return None, despacho.CORTE_PLAZO
    try:
        async with asyncio.timeout_at(corrida.plazo.limite):  # only the READ-ONLY evaluation is ever cancelled
            # The freshness of the forecast is judged against the clock of THIS moment, not against `ahora`: the sends of
            # the zones before this one may have taken minutes, and what is fetched now is stamped with the later time.
            zona = await _evaluar_zona(
                conocida, corrida.ahora, corrida.ventana, corrida.aviso, corrida.fecha, corrida.reloj()
            )
    except TimeoutError:
        return None, despacho.CORTE_PLAZO  # the zone in flight is not known: it stays `diferida`
    return zona, None


async def _despachar(
    tormentas: Sequence[ZonaEvaluada], corrida: _Corrida
) -> tuple[dict[str, ZonaEvaluada], ResumenEnvio, str | None]:
    """Send to the zones that were found with a storm. First every zone is PREPARED (its text, members and who was
    already reached: reads only), so the time left can be shared among the zones that still have something to send, in
    proportion to it; then they are dispatched one after the other. A zone that cannot be handled becomes an `error`
    zone; a run cut leaves the rest of the zones `diferidos`."""
    assert corrida.vapid is not None
    planes: list[tuple[ZonaEvaluada, despacho.PlanDeZona]] = []
    for zona in tormentas:
        try:
            plan = await despacho.preparar_zona(
                corrida.redis, slug=zona.slug, revision=zona.revision, aviso=zona.aviso, fecha=zona.fecha_objetivo
            )
        except Exception as exc:  # noqa: BLE001 - one zone failing must not hide the others; only the class is logged
            logger.warning("alertas: unexpected error preparing a zone exc_type=%s", type(exc).__name__)
            plan = despacho.PlanDeZona(zona.slug, zona.aviso or "", zona.fecha_objetivo, error=True)  # type: ignore[arg-type]
        planes.append((zona, plan))
    hechas: dict[str, ZonaEvaluada] = {}
    envio = ResumenEnvio()
    corte: str | None = None
    por_enviar = sum(len(plan.pendientes) for _, plan in planes)
    for zona, plan in planes:
        pendientes = len(plan.pendientes)
        hechas[zona.slug] = zona
        if corte is not None:
            envio = envio.sumar(ResumenEnvio(diferidos=pendientes))
            continue
        try:
            despachada = await despacho.despachar_plan(
                corrida.redis,
                plan,
                vapid=corrida.vapid,
                plazo=corrida.plazo,
                reloj=corrida.reloj,
                tope_de_zona=despacho.tope_para_zona(corrida.plazo.restante(), pendientes, por_enviar),
                disyuntor=corrida.disyuntor,
            )
        except Exception as exc:  # noqa: BLE001 - one zone failing must not hide the others; only the class is logged
            logger.warning("alertas: unexpected error dispatching a zone exc_type=%s", type(exc).__name__)
            despachada = despacho.DespachoDeZona(ResumenEnvio(), error=True)
        por_enviar -= pendientes
        envio = envio.sumar(despachada.resumen)
        if despachada.error:  # the storm is real but it could not be dispatched: an error of the zone, never silent
            hechas[zona.slug] = ZonaEvaluada(slug=zona.slug, veredicto=VEREDICTO_ERROR, suscriptores=zona.suscriptores)
        corte = despachada.corte
    return hechas, envio, corte


async def _pasada(
    candidatas: Sequence[_ZonaConocida], corrida: _Corrida
) -> tuple[dict[str, ZonaEvaluada], ResumenEnvio, int, str | None]:
    """Evaluate each candidate until the run is cut and, if it sends, dispatch the zones with a storm. Returns the verdicts
    that became known (by slug), what was sent, how many zones took their turn (the one that hit the cut included) and
    why the run stopped (None = it did not)."""
    hechas: dict[str, ZonaEvaluada] = {}
    tormentas: list[ZonaEvaluada] = []
    turnos = 0
    corte: str | None = None
    for conocida in candidatas:
        turnos += 1
        zona, corte = await _evaluar_paso(conocida, corrida)
        if zona is not None:
            hechas[conocida.zona.slug] = zona
            if corrida.enviar and zona.veredicto == VEREDICTO_CON_TORMENTA:
                tormentas.append(zona)
        if corte is not None:
            break
    envio = ResumenEnvio()
    if tormentas and corte is None:  # the kill key is read once more before the first zone is prepared for sending
        corte = await despacho.corte_por_interruptor(corrida.redis)
    if tormentas and corte is not None:  # found a storm but the run was cut before it could send: still pending
        envio = ResumenEnvio(diferidos=sum(z.suscriptores for z in tormentas))
    elif tormentas:
        enviadas, envio, corte = await _despachar(tormentas, corrida)
        hechas.update(enviadas)
    return hechas, envio, turnos, corte


def _estado_de_corte(corte: str | None) -> str:
    if corte in (despacho.CORTE_APAGADO, despacho.CORTE_ILEGIBLE):
        return ESTADO_APAGADO_A_MITAD
    return ESTADO_EVALUADA_INCOMPLETA if corte == despacho.CORTE_PLAZO else ESTADO_EVALUADA


async def evaluar(
    redis: UpstashRedis, ahora: datetime, *, enviar: bool = False, reloj: Callable[[], datetime] | None = None
) -> ResultadoEvaluacion:
    """Evaluate the review of `ahora` for every zone with subscribers and count the results.

    With `enviar=False` (the default) nothing is sent, marked, read from a subscription or pruned. With `enviar=True`
    the zones with a storm are notified (see the module docstring); only the router sets it, after
    `interruptor.envio_activo` said yes.

    `ahora` fixes the window, the kind of notice and the target date for the whole run. `reloj` (the router passes the
    wall clock) is read per zone: it is the reference for the freshness of each forecast, the time of the notice TTL and the
    22:00 cut of the run. Without it, `ahora` stands in (a test, or a caller that does not send for minutes).

    Raises:
        ValueError: `ahora` has no time zone (nothing is touched).
    """
    pronostico.exigir_hora_con_zona(ahora)
    ventana = regla.ventana(ahora)
    if ventana is None:
        return _cerrar(ResultadoEvaluacion(estado=ESTADO_FUERA_DE_VENTANA))

    vapid = None
    if enviar:
        vapid = despacho.cargar_vapid()
        if vapid is None:
            logger.warning("alertas: sending is on but there is no usable VAPID key; nothing is evaluated")
            return _cerrar(ResultadoEvaluacion(estado=ESTADO_SIN_VAPID))

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

    reloj = reloj or (lambda: ahora)
    # The run never outlasts 22:00 (Argentina): the 21 h run must not keep sending once the silence has started.
    segundos = min(settings.alertas_plazo_corrida_segundos, despacho.segundos_hasta_el_silencio(reloj()))
    plazo = despacho.Plazo.desde_ahora(segundos)
    corrida = _Corrida(redis, ahora, ventana, aviso, fecha, plazo, vapid, reloj, despacho.DisyuntorDeBajas())
    # The fixed job key keeps the GLOBAL Open-Meteo cap applying (no key would switch the whole budget off).
    with con_clave_de_cliente(ALERTAS_JOB_CLIENT_KEY):
        hechas, envio, _, corte = await _pasada(a_evaluar, corrida)
        reintentadas = 0
        sin_datos = [
            c for c in a_evaluar if c.zona.slug in hechas and hechas[c.zona.slug].veredicto == VEREDICTO_SIN_DATOS
        ]
        if corrida.enviar and corte is None and sin_datos:
            if plazo.restante() > despacho.ESPERA_SEGUNDA_PASADA_SEGUNDOS:
                await despacho.esperar(despacho.ESPERA_SEGUNDA_PASADA_SEGUNDOS)
                segunda, envio_2, reintentadas, corte = await _pasada(sin_datos, corrida)
                hechas, envio = {**hechas, **segunda}, envio.sumar(envio_2)
            else:
                corte = despacho.CORTE_PLAZO  # no room for the second pass: the zones stay `sin_datos`, visibly

    if corrida.enviar:  # what is still waiting to be deleted is decided with the totals of the whole run
        # Only what was counted as `vencidos` can be turned into `fallidos` (a zone aborted by an unexpected exception
        # lost its counters, but its deferred deletions are still here).
        detenido = corte in (despacho.CORTE_APAGADO, despacho.CORTE_ILEGIBLE)
        descartadas = min(await corrida.disyuntor.cerrar_corrida(redis, plazo, detenido), envio.vencidos)
        envio = envio.sumar(ResumenEnvio(vencidos=-descartadas, fallidos=descartadas))

    if corrida.enviar and corte not in (despacho.CORTE_APAGADO, despacho.CORTE_ILEGIBLE):
        await despacho.podar_zonas_vacias(redis, [z.zona.slug for z in listadas if z.suscriptores == 0])

    zonas = (
        tuple(hechas[z.zona.slug] for z in a_evaluar if z.zona.slug in hechas)
        + tuple(_sin_evaluar(z, VEREDICTO_DIFERIDA) for z in a_evaluar if z.zona.slug not in hechas)  # deadline / stop
        + tuple(_sin_evaluar(z, VEREDICTO_DIFERIDA) for z in sobre_el_tope)  # over the cap
        + tuple(_sin_evaluar(z, VEREDICTO_SIN_SUSCRIPTORES) for z in listadas if z.suscriptores == 0)
    )
    resumen = envio.sumar(ResumenEnvio(reintentadas=reintentadas)) if corrida.enviar else None
    return _cerrar(_resultado(_estado_de_corte(corte), zonas, desconocidas, resumen))
