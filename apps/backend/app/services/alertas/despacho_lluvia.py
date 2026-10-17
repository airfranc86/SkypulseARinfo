"""The persistent-rain notice (opt-in) as a plan for `despacho.despachar_plan` (lluvia, PR 3a).

Sending is the same as for a storm (batches, cuts, retry, breaker, done-set): this module only PREPARES the plan, with what is
different:

- the text (`textos.texto_lluvia_hoy` / `texto_lluvia_manana`, a DRAFT the owner approves) with the franjas of the day of
  the notice that the rain windows cover;
- the recipients: the members of the rain index `alertas:zona:{slug}:lluvia` (a subset of the zone's set). The sender
  re-reads every record before sending (`PlanDeZona.lluvia`), so a stale id of the index never gets a notice;
- its own marks, so it never replaces nor blocks the storm notice: the done-set
  `alertas:enviado:{slug}:lluvia-{hoy|manana}:{fecha}`, the push Topic `envio.topic_lluvia` and the tag `envio.tag_lluvia`.
  One rain notice per zone, notice and date: a later review of the same day finds everybody already reached.

The expiry of the notice of TODAY is midnight (Argentina); tomorrow's keeps the usual TTL (it is read the next morning).
Nothing sensitive goes into a log line: no id, endpoint, text or zone.
"""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.core.upstash import UpstashRedis
from app.services.alertas import despacho, envio
from app.services.alertas import suscripcion as svc
from app.services.alertas.regla import ResultadoLluvia
from app.services.alertas.textos import franjas_de_lluvia, texto_lluvia_hoy, texto_lluvia_manana
from app.services.alertas.zonas import zona_por_slug

logger = logging.getLogger(__name__)

_AR = timezone(timedelta(hours=-3))  # Argentina has no DST; the same offset `regla.py` uses


def aviso_de_lluvia(aviso: str) -> str:
    """The notice level of a rain notice (`lluvia-hoy` / `lluvia-manana`): the part of its done-set key that tells it from the storm's."""
    return f"lluvia-{aviso}"


def _vence(aviso: str, fecha: date) -> datetime | None:
    """When the notice stops being useful: midnight at the end of its day for TODAY's; None (the usual TTL) for tomorrow's."""
    if aviso != despacho.AVISO_HOY:
        return None
    return datetime(fecha.year, fecha.month, fecha.day, tzinfo=_AR) + timedelta(days=1)


async def preparar_zona_lluvia(
    redis: UpstashRedis, *, slug: str, resultado: ResultadoLluvia, aviso: str, fecha: date
) -> despacho.PlanDeZona:
    """Read what the zone has to send as a rain notice: the text, the members of the rain index and the done-set (SMEMBERS
    twice, nothing written). `aviso` is `despacho.AVISO_HOY` or `AVISO_MANANA`. Any failure (the text, either read) is an
    `error` plan: the zone is not notified (fail-closed)."""
    nivel = aviso_de_lluvia(aviso)
    try:
        zona = zona_por_slug(slug)
        if zona is None or aviso not in (despacho.AVISO_HOY, despacho.AVISO_MANANA):
            raise ValueError("zona o aviso desconocido")
        franjas = franjas_de_lluvia(resultado, fecha)
        mensaje = texto_lluvia_hoy(zona, franjas) if aviso == despacho.AVISO_HOY else texto_lluvia_manana(zona, franjas)
        payload = envio.construir_payload(mensaje, tag=envio.tag_lluvia(slug, fecha))
    except ValueError:
        logger.warning("alertas: the rain notice could not be built; the zone is not notified")
        return despacho.PlanDeZona(slug, nivel, fecha, error=True, lluvia=True)
    clave = despacho.clave_de_enviados(slug, nivel, fecha)
    propio = despacho.AvisoSmn(
        topic=envio.topic_lluvia(slug, fecha),
        clave_enviados=clave,
        ttl_enviados=despacho.ENVIADOS_TTL_SEGUNDOS,
        vence=_vence(aviso, fecha),
    )
    plan = await despacho.leer_plan(
        redis, slug=slug, aviso=nivel, fecha=fecha, payload=payload, clave_enviados=clave, smn=propio,
        indice=svc.clave_de_zona_lluvia(slug),
    )
    return dataclasses.replace(plan, lluvia=True)


# The counters a rain run adds to the response and the log. Their own tuple, NEXT to `despacho.CONTADORES_ENVIO` and never
# inside it: with the flag off the response and the log keep their exact shape. Whole numbers only, never an id or a text.
CONTADORES_LLUVIA = (
    "lluvia_zonas",
    "lluvia_errores",
    "lluvia_avisadas",
    "lluvia_ya_avisadas",
    "lluvia_enviados",
    "lluvia_vencidos",
    "lluvia_fallidos",
    "lluvia_diferidos",
)


@dataclass(frozen=True)
class ZonaConLluvia:
    """A zone the run found persistent rain in (and no storm): what the rain notice needs."""

    slug: str
    resultado: ResultadoLluvia


@dataclass(frozen=True)
class EnvioDeLluvia:
    """What the rain part of a run did, as integers: `zonas` (zones with rain and no storm), `errores` (zones the notice could
    not be built or dispatched for), `resumen` (the sender's counters, SEPARATE from the storm's so a rain failure never
    shows up as a storm failure) and `corte` (why the run stopped, None = it did not)."""

    resumen: despacho.ResumenEnvio = dataclasses.field(default_factory=despacho.ResumenEnvio)
    zonas: int = 0
    errores: int = 0
    corte: str | None = None

    def como_respuesta(self) -> dict[str, int]:
        r = self.resumen
        return {
            "lluvia_zonas": self.zonas,
            "lluvia_errores": self.errores,
            "lluvia_avisadas": r.avisadas,
            "lluvia_ya_avisadas": r.ya_avisadas,
            "lluvia_enviados": r.enviados,
            "lluvia_vencidos": r.vencidos,
            "lluvia_fallidos": r.fallidos,
            "lluvia_diferidos": r.diferidos,
        }


async def despachar_lluvia(
    redis: UpstashRedis,
    zonas: Sequence[ZonaConLluvia],
    *,
    vapid: despacho.ClaveVapid,
    plazo: despacho.Plazo,
    reloj: Callable[[], datetime],
    aviso: str,
    fecha: date,
    disyuntor: despacho.DisyuntorDeBajas,
) -> EnvioDeLluvia:
    """Send the rain notice to the zones found with rain. Like the storm's dispatch: the send switch is read once, every zone
    is PREPARED first (reads only) so the time left is shared in proportion to what each has to send, then dispatched one after
    the other. It shares the circuit breaker of the RUN (`disyuntor`: one per run, with its ceiling of deletions; a breaker
    the storm already tripped stays tripped, and a new one would let a proxy answering 404 to everything wipe the rain
    subscribers) but has its OWN summary: a rain failure never shows up as a storm failure. Never raises: a zone that cannot
    be handled counts in `errores`."""
    if not zonas:
        return EnvioDeLluvia()
    corte = await despacho.corte_por_interruptor(redis)
    if corte is not None:
        return EnvioDeLluvia(zonas=len(zonas), corte=corte)
    planes: list[despacho.PlanDeZona] = []
    for zona in zonas:
        try:
            plan = await preparar_zona_lluvia(redis, slug=zona.slug, resultado=zona.resultado, aviso=aviso, fecha=fecha)
        except Exception as exc:  # noqa: BLE001 - one zone failing must not hide the others; only the class is logged
            logger.warning("alertas: unexpected error preparing a rain zone exc_type=%s", type(exc).__name__)
            plan = despacho.PlanDeZona(zona.slug, aviso_de_lluvia(aviso), fecha, error=True, lluvia=True)
        planes.append(plan)
    resumen = despacho.ResumenEnvio()
    errores = 0
    por_enviar = sum(len(plan.pendientes) for plan in planes)
    for plan in planes:
        pendientes = len(plan.pendientes)
        if corte is not None:
            resumen = resumen.sumar(despacho.ResumenEnvio(diferidos=pendientes))
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
        except Exception as exc:  # noqa: BLE001 - one zone failing must not hide the others; only the class is logged
            logger.warning("alertas: unexpected error dispatching a rain zone exc_type=%s", type(exc).__name__)
            despachada = despacho.DespachoDeZona(despacho.ResumenEnvio(), error=True)
        por_enviar -= pendientes
        resumen = resumen.sumar(despachada.resumen)
        errores += 1 if despachada.error else 0
        corte = despachada.corte
    detenido = corte in (despacho.CORTE_APAGADO, despacho.CORTE_ILEGIBLE)
    # What the rain sends left waiting to be deleted is decided with the totals of the whole run (the shared breaker keeps
    # the storm's counts: the storm's own pending deletions were already decided when it closed).
    descartadas = min(await disyuntor.cerrar_corrida(redis, plazo, detenido), resumen.vencidos)
    resumen = resumen.sumar(despacho.ResumenEnvio(vencidos=-descartadas, fallidos=descartadas))
    return EnvioDeLluvia(resumen=resumen, zonas=len(zonas), errores=errores, corte=corte)
