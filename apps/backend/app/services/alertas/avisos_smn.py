"""Official SMN storm alerts pushed per zone (FRA-359, T3): the cross with the subscribers and the dispatch.

`evaluar_avisos_smn(redis, ahora, vapid=...)` is the SMN counterpart of `evaluacion.evaluar`: it never calls Open-Meteo.
One run:

1. lists the zones with subscribers (`alertas:zonas` ∩ the catalog: ONE SMEMBERS; a slug outside the catalog is
   ignored). No SCARD: a zone without an alert costs nothing more, and the members of a zone with one are read by the
   plan anyway;
2. asks the SMN feed, zone by zone, for the alerts whose polygon contains the zone's point (`get_smn_alertas(lat,
   lon)`: in memory, Upstash is not touched) and keeps the storm alerts of level amarillo or above that are not expired
   (`es_aviso_de_tormenta_notificable`, T1). `available=False` means "we do not know", never "no alerts" (S6): for that
   zone nothing is sent and nothing is marked, and `smn_sin_datos` says so, once per run. Other types (wind, rain, snow)
   are never sent (S8). An alert that starts later is sent as soon as it is published; the text says since when it is
   in force (L8);
3. the unit from here on is the PAIR (zone, alert), identified by the dedupe key of T1 (zone, type, level, start):
   the same alert listed twice by the feed is one pair, the same alert with its text rewritten is the same pair, a
   rise from amarillo to naranja is another pair. A pair the night rule omits (`se_omite_de_noche`, the plug of T5:
   today it omits nothing) is counted and left alone;
4. each pair is PREPARED like a forecast zone (`despacho.leer_plan`: its text of T2, the members and the ids already
   reached: reads only) and DISPATCHED through the same path (`despacho.despachar_plan`: batches, the kill key and the
   deadline before every batch, the record of progress after every batch, one retry of the transient failures, the
   circuit breaker of the deletions, the stale members). What differs is carried by `despacho.AvisoSmn`: the Topic and
   the tag of T2 (so an SMN push never replaces the forecast push of the day, nor the reverse) and its own done-set.

The done-set of a pair is `alertas:smn:enviado:{zona}:{nivel}:{topic}` (`clave_de_enviados_smn`): the ids already
reached for THAT alert, with an expiry set once (`EXPIRE ... NX`, like the forecast's) that outlives `fecha_hasta` by
`MARGEN_ENVIADOS_SMN_SEGUNDOS` (an alert the SMN extends keeps its key and must not be sent again) and never passes
`ENVIADOS_SMN_TTL_MAXIMO_SEGUNDOS` (a feed error far in the future must not pin a key for months). Its keyspace is its
own: it never meets the forecast done-sets `alertas:enviado:{zona}:{aviso}:{fecha}` nor the run lock
`alertas:lock:evaluar`. An id is recorded ONLY after its send was accepted (or the subscription is gone or invalid, as the
forecast does): a transient failure, a rejection or a run cut leave it pending for the next run, and the same person is
never notified twice of the same alert.

Two runs at the same time are kept apart by the run lock `alertas:lock:evaluar`, which the CALLER holds (as
`evaluacion.evaluar` does: SET NX EX, never released): this function does not take it, so a run that is already inside
`evaluar` can call it too. The lock, not a mark per key, is the guard on purpose: a per-key SET NX would have to live
as long as the dispatch of the pair (minutes) and a crash in the middle would block the next run until it expired,
leaving people unnotified; with the lock the worst case is the forecast's (a crash between a push and its record repeats
at most one batch, which the devices collapse: same `tag`, same `Topic`).

A dry run (`vapid=None`) only counts the alerts found: it reads no member, sends nothing and marks nothing. Nothing
sensitive leaves this module: no id, endpoint, text, key or zone goes into a log line or into the counters.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.upstash import UpstashRedis
from app.schemas.smn_alertas import SmnAlerta, SmnAlertasResponse
from app.services.alertas import despacho, envio
from app.services.alertas import suscripcion as svc
from app.services.alertas.despacho import AVISO_SMN, AvisoSmn, PlanDeZona, ResumenEnvio, ResumenSmn
from app.services.alertas.mensajes_smn import texto_aviso_smn
from app.services.alertas.zonas import ZONAS, Zona
from app.services.smn_alertas import ClaveDedupe, clave_dedupe, es_aviso_de_tormenta_notificable, get_smn_alertas

logger = logging.getLogger(__name__)

# The done-sets of the SMN pairs live here, apart from `alertas:enviado:` (the forecast) and `alertas:lock:` (the run).
PREFIJO_ENVIADOS_SMN = "alertas:smn:enviado:"
# How long the done-set of a pair outlives `fecha_hasta`: the same as the forecast done-set outlives its day. An alert
# the SMN extends keeps its dedupe key (`fecha_hasta` is not part of it) and must find its done-set still there.
MARGEN_ENVIADOS_SMN_SEGUNDOS = despacho.ENVIADOS_TTL_SEGUNDOS
# The most a done-set may live: a `fecha_hasta` far in the future (a feed error) must not pin a key for months.
ENVIADOS_SMN_TTL_MAXIMO_SEGUNDOS = 7 * 24 * 60 * 60

_AR = timezone(timedelta(hours=-3))  # Argentina has no DST; the same offset the rest of the alerts use

ObtenerAvisos = Callable[[float, float], Awaitable[SmnAlertasResponse]]
Omision = Callable[[SmnAlerta, datetime], bool]


@dataclass(frozen=True)
class ResultadoSmn:
    """What a run of the SMN alerts did: the counters of the pairs (`smn`), what the sender did to the people (`envio`,
    the same counters as the forecast run) and why the run stopped early (`corte`: a `despacho.CORTE_*`, or None).
    The caller (the evaluation of T4) maps `corte` to the state of the response, as it does for the forecast."""

    smn: ResumenSmn
    envio: ResumenEnvio
    corte: str | None = None


@dataclass(frozen=True)
class _Par:
    """One (zone, alert) pair found over a zone with subscribers, with its dedupe key and the zone's catalog index."""

    zona: Zona
    indice: int
    alerta: SmnAlerta
    clave: ClaveDedupe


# ---------------------------------------------------------------------------
# Small pieces
# ---------------------------------------------------------------------------


def clave_de_enviados_smn(clave: ClaveDedupe) -> str:
    """The done-set of one (zone, alert) pair: the ids already reached for THAT alert. It names the zone and the level
    (readable in the console) and ends with the push Topic of the alert (`envio.topic_smn`: 32 base64url characters
    derived from the whole dedupe key), so the key, the Topic and the tag always agree."""
    return f"{PREFIJO_ENVIADOS_SMN}{clave[0]}:{clave[2]}:{envio.topic_smn(clave)}"


def _en_utc(momento: datetime) -> datetime:
    """A naive datetime is read as UTC (the CAP feed carries offsets: a guard, not the expected path)."""
    return momento.replace(tzinfo=timezone.utc) if momento.tzinfo is None else momento


def ttl_de_enviados_smn(alerta: SmnAlerta, ahora: datetime) -> int:
    """The expiry of the done-set of a pair: the time left until `fecha_hasta` plus the margin, never more than the
    ceiling. Without an expiry (or one already passed), the margin alone."""
    if alerta.fecha_hasta is None:
        return MARGEN_ENVIADOS_SMN_SEGUNDOS
    restante = max(0, int((_en_utc(alerta.fecha_hasta) - ahora).total_seconds()))
    return min(ENVIADOS_SMN_TTL_MAXIMO_SEGUNDOS, restante + MARGEN_ENVIADOS_SMN_SEGUNDOS)


def se_omite_de_noche(alerta: SmnAlerta, ahora: datetime) -> bool:
    """Whether an alert is NOT sent at this hour. The plug of the night rule of S7 (T5: from 22 to 5 h in Argentina
    only the red alerts go out); today nothing is omitted. T5 replaces this function, and only this function: the run
    counts an omitted pair as `smn_omitidas` and neither reads, sends nor marks anything for it."""
    return False


# ---------------------------------------------------------------------------
# The cross: zones with subscribers × alerts over their point
# ---------------------------------------------------------------------------


async def _zonas_con_suscriptores(redis: UpstashRedis) -> list[tuple[int, Zona]]:
    """The catalog zones listed in `alertas:zonas`, in catalog order (one SMEMBERS; an unknown slug is left alone).

    Raises:
        UpstashUnavailableError: the index could not be read (nothing was touched).
    """
    slugs = await redis.smembers(svc.CLAVE_ZONAS)
    return [(indice, zona) for indice, zona in enumerate(ZONAS) if zona.slug in slugs]


@dataclass(frozen=True)
class _Cruce:
    pares: tuple[_Par, ...]
    sin_datos: bool  # the feed could not be verified for at least one zone: "we do not know"
    errores: int  # zones whose alerts could not be read at all (an unexpected exception)


async def _cruzar(zonas: Sequence[tuple[int, Zona]], obtener: ObtenerAvisos, ahora: datetime) -> _Cruce:
    """The notifiable (zone, alert) pairs over the zones, one per dedupe key (the feed may list the same alert twice)."""
    pares: list[_Par] = []
    vistas: set[ClaveDedupe] = set()
    sin_datos, errores = False, 0
    for indice, zona in zonas:
        try:
            respuesta = await obtener(zona.lat, zona.lon)
        except Exception as exc:  # noqa: BLE001 - one zone failing must not hide the others; only the class is logged
            logger.warning("alertas: unexpected error reading the SMN alerts of a zone exc_type=%s", type(exc).__name__)
            errores += 1
            continue
        if not respuesta.available:  # "we do not know": nothing is sent or marked for this zone (S6)
            sin_datos = True
            continue
        for alerta in respuesta.alertas:
            if not es_aviso_de_tormenta_notificable(alerta, ahora):
                continue
            clave = clave_dedupe(zona.slug, alerta)
            if clave not in vistas:
                vistas.add(clave)
                pares.append(_Par(zona, indice, alerta, clave))
    return _Cruce(tuple(pares), sin_datos, errores)


# ---------------------------------------------------------------------------
# One pair
# ---------------------------------------------------------------------------


async def preparar_aviso_smn(redis: UpstashRedis, *, zona: Zona, alerta: SmnAlerta, ahora: datetime) -> PlanDeZona:
    """Read what a pair has to send: the text of T2 with its tag, then the members and the done-set of the pair
    (`despacho.leer_plan`: reads only). A text that cannot be built, or a failed read, is an `error` plan."""
    clave = clave_dedupe(zona.slug, alerta)
    fecha = ahora.astimezone(_AR).date()
    try:
        payload = envio.construir_payload(texto_aviso_smn(zona, alerta, ahora=ahora), tag=envio.tag_smn(clave))
    except ValueError:
        logger.warning("alertas: the SMN notice could not be built; the pair is not notified")
        return PlanDeZona(zona.slug, AVISO_SMN, fecha, error=True)
    aviso = AvisoSmn(
        topic=envio.topic_smn(clave),
        clave_enviados=clave_de_enviados_smn(clave),
        ttl_enviados=ttl_de_enviados_smn(alerta, ahora),
        vence=alerta.fecha_hasta,
    )
    return await despacho.leer_plan(
        redis, slug=zona.slug, aviso=AVISO_SMN, fecha=fecha, payload=payload, clave_enviados=aviso.clave_enviados,
        smn=aviso,
    )


async def _preparar(redis: UpstashRedis, pares: Sequence[_Par], ahora: datetime) -> list[tuple[_Par, PlanDeZona]]:
    """Every pair prepared (reads only), the ones with more to send first (ties: catalog order), so the time left can be
    shared in proportion to what each one has to do."""
    planes: list[tuple[_Par, PlanDeZona]] = []
    for par in pares:
        try:
            plan = await preparar_aviso_smn(redis, zona=par.zona, alerta=par.alerta, ahora=ahora)
        except Exception as exc:  # noqa: BLE001 - one pair failing must not hide the others; only the class is logged
            logger.warning("alertas: unexpected error preparing an SMN pair exc_type=%s", type(exc).__name__)
            plan = PlanDeZona(par.zona.slug, AVISO_SMN, ahora.astimezone(_AR).date(), error=True)
        planes.append((par, plan))
    planes.sort(key=lambda p: (-len(p[1].pendientes), p[0].indice))
    return planes


@dataclass(frozen=True)
class _Despacho:
    smn: ResumenSmn
    envio: ResumenEnvio
    corte: str | None
    vacias: tuple[str, ...]  # zones whose subscriber set was empty at send time (candidates to prune)


def _contar_par(plan: PlanDeZona, despachada: despacho.DespachoDeZona) -> ResumenSmn:
    """What one dispatched pair adds to the SMN counters."""
    if despachada.error:
        return ResumenSmn(smn_errores=1)
    if plan.miembros == 0:
        return ResumenSmn()  # nobody left in the zone: nothing to count
    if not plan.pendientes:
        return ResumenSmn(smn_ya_avisadas=1)
    return ResumenSmn(smn_avisadas=despachada.resumen.avisadas)  # 1 if somebody was reached in this run


async def _despachar(
    redis: UpstashRedis,
    planes: Sequence[tuple[_Par, PlanDeZona]],
    *,
    vapid: despacho.ClaveVapid,
    plazo: despacho.Plazo,
    reloj: Callable[[], datetime],
    disyuntor: despacho.DisyuntorDeBajas,
    corte: str | None,
) -> _Despacho:
    """Dispatch the prepared pairs one after the other through `despacho.despachar_plan`. A run already cut (`corte`),
    or cut by a pair, leaves the rest of the pairs `diferidos` (their pendientes are still pending)."""
    smn, envio_total = ResumenSmn(), ResumenEnvio()
    vacias: list[str] = []
    por_enviar = sum(len(plan.pendientes) for _, plan in planes)
    for par, plan in planes:
        pendientes = len(plan.pendientes)
        if corte is not None:
            envio_total = envio_total.sumar(ResumenEnvio(diferidos=pendientes))
            continue
        try:
            despachada = await despacho.despachar_plan(
                redis,
                plan,
                vapid=vapid,
                plazo=plazo,
                reloj=reloj,
                tope_de_zona=despacho.tope_para_zona(plazo.restante(), pendientes, por_enviar),
                disyuntor=disyuntor,
            )
        except Exception as exc:  # noqa: BLE001 - one pair failing must not hide the others; only the class is logged
            logger.warning("alertas: unexpected error dispatching an SMN pair exc_type=%s", type(exc).__name__)
            despachada = despacho.DespachoDeZona(ResumenEnvio(), error=True)
        por_enviar -= pendientes
        smn, envio_total = smn.sumar(_contar_par(plan, despachada)), envio_total.sumar(despachada.resumen)
        if not plan.error and plan.miembros == 0:
            vacias.append(par.zona.slug)
        corte = despachada.corte
    return _Despacho(smn, envio_total, corte, tuple(vacias))


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


async def evaluar_avisos_smn(
    redis: UpstashRedis,
    ahora: datetime,
    *,
    vapid: despacho.ClaveVapid | None,
    reloj: Callable[[], datetime] | None = None,
    plazo: despacho.Plazo | None = None,
    obtener_avisos: ObtenerAvisos = get_smn_alertas,
    omitir: Omision = se_omite_de_noche,
) -> ResultadoSmn:
    """Cross the SMN alerts in force with the zones that have subscribers and send the notifiable pairs through the
    dispatch of the forecast push (see the module docstring). Never calls Open-Meteo.

    `ahora` (time-zone aware) decides which alerts are in force and the text; `reloj` (the wall clock, read per pair)
    gives the push TTLs, `ahora` stands in without it. `plazo` is the run deadline; without it, the configured one
    (`alertas_plazo_corrida_segundos`). `vapid=None` is a dry run: the pairs are counted and nothing else happens.
    `obtener_avisos` and `omitir` exist for the tests and for T5 (the night rule).

    The caller holds the run lock `alertas:lock:evaluar` (as `evaluacion.evaluar` does) and maps `corte` to a state.

    Raises:
        ValueError: `ahora` has no time zone (nothing is touched).
        UpstashUnavailableError: the index of zones could not be read (nothing is touched).
    """
    if ahora.tzinfo is None:
        raise ValueError("ahora necesita zona horaria")
    reloj = reloj or (lambda: ahora)
    cruce = await _cruzar(await _zonas_con_suscriptores(redis), obtener_avisos, ahora)
    smn = ResumenSmn(smn_sin_datos=int(cruce.sin_datos), smn_avisos=len(cruce.pares), smn_errores=cruce.errores)
    if vapid is None:  # a dry run: the pairs are counted, nothing is read, sent or marked
        return ResultadoSmn(smn, ResumenEnvio())
    a_enviar: list[_Par] = []
    for par in cruce.pares:
        if omitir(par.alerta, ahora):
            smn = smn.sumar(ResumenSmn(smn_omitidas=1))
        else:
            a_enviar.append(par)
    if not a_enviar:
        return ResultadoSmn(smn, ResumenEnvio())

    plazo = plazo or despacho.Plazo.desde_ahora(settings.alertas_plazo_corrida_segundos)
    planes = await _preparar(redis, a_enviar, ahora)
    # The kill key is read once more right before the first send (and before every batch, inside the dispatch).
    corte = await despacho.corte_por_interruptor(redis)
    disyuntor = despacho.DisyuntorDeBajas()
    hecho = await _despachar(redis, planes, vapid=vapid, plazo=plazo, reloj=reloj, disyuntor=disyuntor, corte=corte)
    envio_total = hecho.envio
    # What is still waiting to be deleted is decided with the totals of the whole run; only what was counted as
    # `vencidos` can be turned into `fallidos`.
    detenido = hecho.corte in (despacho.CORTE_APAGADO, despacho.CORTE_ILEGIBLE)
    descartadas = min(await disyuntor.cerrar_corrida(redis, plazo, detenido), envio_total.vencidos)
    envio_total = envio_total.sumar(ResumenEnvio(vencidos=-descartadas, fallidos=descartadas))
    if hecho.vacias and not detenido:  # a run stopped by the kill key prunes nothing, like the forecast
        await despacho.podar_zonas_vacias(redis, hecho.vacias)
    return ResultadoSmn(smn.sumar(hecho.smn), envio_total, hecho.corte)
