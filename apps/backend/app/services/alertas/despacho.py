"""Per-zone sending of the scheduled alerts (FRA-355, PR5c).

`evaluacion.evaluar(redis, ahora, enviar=True)` evaluates the zones first and then hands every zone it found a storm in to
this module. The sender (`envio.enviar`) is touched ONLY here; `evaluacion.py` never imports it. For one zone:

1. `preparar_zona`: the text (`texto_aviso_hoy` / `texto_aviso_manana` with the franjas and, inside the same notice, the
   hail franjas), the zone's members (SMEMBERS) and the ids ALREADY REACHED today (the done-set). `pendientes` is the
   difference. Upstash failing on either read = the zone is NOT notified (fail-closed) and counts as an error;
2. `despachar_plan`: batches of `ENVIOS_POR_LOTE` sends in parallel, over the pendientes only. BEFORE every batch (the
   first included) the zone's time cap, the run deadline and the send switch are checked (an unreadable kill key is read
   one more time before it cuts); what is left is `diferidos`, still pending for the next run. AFTER every batch the ids
   that were reached are recorded in the done-set, before the next batch goes out;
3. ONE final tanda: the transient failures of the whole zone are collected, the run waits once and retries them
   together. Nobody sleeps inside a batch.

The done-set is the dedupe (it replaced the one-mark-per-zone of the first version): the Redis SET
`alertas:enviado:{zona}:{aviso}:{fecha}` holds the ids already reached (36 h expiry, set once with `EXPIRE ... NX`), so
a run that is cut, times out or crashes simply leaves the rest pending for the next run, and the people already reached
are never notified twice. A batch whose SADD fails stops the zone (we do not keep sending without recording); a crash
between a push and its SADD can repeat at most one batch, which the devices collapse (same `tag`, same `Topic`).

Per subscriber, what each answer of the sender means (`envio.Resultado`):

- `ENVIADA`: delivered and recorded. `VENCIDA` (404/410): gone. `INVALIDA`, or a record that cannot be read or does not
  pass the subscription validation (a key off the curve, an endpoint outside the push hosts): it can never succeed. Both
  are recorded (nothing to send them) and DELETED (counted as `vencidos`: there is no separate counter), but only
  through the circuit breaker below.
- `ERROR` (network, timeout, 408/425/429/5xx): transient. Retried once, in the final tanda; if it fails again `fallidos`
  and NOT recorded: the next run tries it again.
- `RECHAZADA` (any other refusal, 4xx or 3xx): NOT retried in this run, NOT deleted (it could be our VAPID key) and NOT
  recorded, so every run tries it once more while the notice lasts; `fallidos`. There is no count of consecutive
  rejections on purpose.
- a record that now belongs to ANOTHER zone (the person changed city; the old set kept the id): taken out of this zone's
  set and not sent to. Counted as nothing.
- no record at all (Upstash CONFIRMED it with a null result, twice): an expired id, cleaned from the indexes
  (`limpiar_id_vencido`), `vencidos`. A doubtful read (no `result`, an odd answer) is NOT "no record": `fallidos`, nothing
  is cleaned or recorded, and the next run tries again (`registro_de` and `limpiar_id_vencido` read strictly).

Circuit breaker (`DisyuntorDeBajas`, ONE per run). It counts, over the whole run, the sends (`total`) and the "gone"
answers (`VENCIDA` + `INVALIDA`, `bajas`); it trips when `total >= 4` and `bajas * 2 > total`, or when a single batch of at
least four is more than half gone (an outage that starts late in a healthy run). Deletions are DEFERRED: they are collected
during the batches and decided when the zone closes and again when the run ends, with the run's totals, so tiny zones
(1 to 3 subscribers) and the 1-id tail of a batch are protected too. Tripped: nothing is deleted for the rest of the run,
the deferred ones are dropped (they count as `fallidos`, not `vencidos`) and one WARNING says so, without data. A proxy
answering 404 for everything must not wipe the subscriptions. On top of it `MAX_BAJAS_POR_CORRIDA` is an absolute ceiling
per run: past it no more subscriptions are deleted (the rest count as `fallidos` and wait for another run).

Time. The time left in the run is shared among the zones that still have something to SEND, in proportion to their
pendientes with a floor (`tope_para_zona`), so one big or poisoned zone cannot starve the ones after it. Reaching the cap
of a zone ends THAT zone; reaching the run deadline ends the run. The notice of today expires at midnight (`ttl_de_aviso`)
and the run never outlasts 22:00 in Argentina (`segundos_hasta_el_silencio`).

An official SMN notice (FRA-359, `avisos_smn`) goes through the same `despachar_plan`: its plan is read by `leer_plan`
with a text already built and carries an `AvisoSmn` (its own push Topic, its own done-set `alertas:smn:enviado:...` with
its own expiry, and when the notice expires). Everything else (batches, cuts, retries, the breaker, the stale members)
is shared; a plan without one is the forecast notice, exactly as before.

Nothing sensitive leaves this module: no id, endpoint, text, key or zone goes into a log line or into the counters.
`Plazo` reads the event loop's monotonic clock, not the wall clock.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from py_vapid import Vapid

from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas import envio, interruptor, umbrales
from app.services.alertas import suscripcion as svc
from app.services.alertas.regla import ResultadoRegla
from app.services.alertas.textos import Mensaje, franjas_de, franjas_granizo, texto_aviso_hoy, texto_aviso_manana
from app.services.alertas.zonas import zona_por_slug

logger = logging.getLogger(__name__)

ClaveVapid = Vapid  # so `evaluacion.py` can name the type without importing the sender's libraries

AVISO_HOY = "hoy"  # the revisions of 7 to 19 h: the rest of today
AVISO_MANANA = "manana"  # the revision of 21 h: tomorrow
AVISO_SMN = "smn"  # an official SMN notice (FRA-359): its own Topic, done-set and TTLs, carried by `AvisoSmn`

CORTE_APAGADO = "apagado"  # the kill key is present (or the flag is off): an operator stopped it on purpose
CORTE_ILEGIBLE = "ilegible"  # the kill key could not be read, twice: fail-closed, but nobody ordered it
CORTE_PLAZO = "plazo"  # the run deadline (or, inside a zone, its cap) passed

# The done-set outlives the day it is about (the date is in the key, so a set never blocks another day) and a run that
# crosses midnight; it is not a TTL to tune.
ENVIADOS_TTL_SEGUNDOS = 36 * 60 * 60
# Sends in flight at the same time, and also the sends between two checks of the kill key and the deadline.
ENVIOS_POR_LOTE = 10
# One retry of the transient failures of a zone, after this short wait (once per zone, in a final tanda).
ESPERA_REINTENTO_SEGUNDOS = 2.0
# The wait before the second pass over the zones without data. It must be longer than the 15 s the forecast cache
# remembers a failed call (otherwise the second pass would be answered from that memory without asking Open-Meteo).
ESPERA_SEGUNDA_PASADA_SEGUNDOS = 20.0
# The breaker looks at runs/batches of at least this many sends, and trips when more than half of them were "gone".
LOTE_MINIMO_DEL_DISYUNTOR = 4
# The absolute ceiling of subscriptions deleted in ONE run (all its zones): the proportional breaker lets through about as
# many deletions as healthy sends there were before an outage; past this number the rest are dropped (counted as `fallidos`).
MAX_BAJAS_POR_CORRIDA = 25
# A TTL of 0 is refused by Apple: even a notice sent a second before midnight asks the push service to keep it a minute.
TTL_MINIMO_SEGUNDOS = 60
# The least a zone with something to send gets of the time left (never more than what is left).
TOPE_MINIMO_DE_ZONA_SEGUNDOS = 15.0

_AR = timezone(timedelta(hours=-3))  # Argentina has no DST; the same offset `regla.py` uses

(_ENVIADO, _VENCIDO, _FALLIDO, _REINTENTAR, _GONE, _INVALIDO, _OMITIDO) = (
    "enviado", "vencido", "fallido", "reintentar", "gone", "invalido", "omitido",
)
# Outcomes after which there is nothing more to send to the id in this notice: they go into the done-set. (`_GONE` and
# `_INVALIDO` are turned into `_VENCIDO` before this is looked at: they are recorded too, deleted or not.)
_HECHOS = frozenset({_ENVIADO, _VENCIDO, _OMITIDO})

# The counters a sending run adds to the response. An explicit whitelist: only whole numbers, never an id or a text.
CONTADORES_ENVIO = (
    "avisadas",
    "ya_avisadas",
    "enviados",
    "vencidos",
    "fallidos",
    "diferidos",
    "reintentadas",
)


@dataclass(frozen=True)
class ResumenEnvio:
    """What a sending run did, as integers. Zones: `avisadas` (at least one recipient was reached in this run),
    `ya_avisadas` (no pendientes: everybody was reached before), `reintentadas` (zones that entered the second pass).
    Notifications: `enviados`, `vencidos` (gone for good: the push service, the 180-day expiry or an invalid record;
    removed), `fallidos` (not delivered, kept, still pending), `diferidos` (not tried because the run or the zone was
    cut, still pending)."""

    avisadas: int = 0
    ya_avisadas: int = 0
    enviados: int = 0
    vencidos: int = 0
    fallidos: int = 0
    diferidos: int = 0
    reintentadas: int = 0

    def sumar(self, otro: ResumenEnvio) -> ResumenEnvio:
        """A new summary with both added up (neither input changes)."""
        return ResumenEnvio(**{n: getattr(self, n) + getattr(otro, n) for n in CONTADORES_ENVIO})

    def como_respuesta(self) -> dict[str, int]:
        return {nombre: getattr(self, nombre) for nombre in CONTADORES_ENVIO}


# The counters of the sending of OFFICIAL SMN alerts (FRA-359). Their own tuple, NEXT to `CONTADORES_ENVIO` and never
# inside it: the response and the log line of the forecast run keep their exact shape (tests pin it), and a run that
# only checks the SMN (S2) adds these. The unit is the pair (zone, alert): a zone with two alerts counts twice. The
# people reached by an SMN push are counted by the sender as always (`ResumenEnvio`): no second set of per-subscriber
# counters. An explicit whitelist: whole numbers only, never a zone, a key or a text.
CONTADORES_SMN = (
    "smn_sin_datos",
    "smn_avisos",
    "smn_avisadas",
    "smn_ya_avisadas",
    "smn_omitidas",
    "smn_errores",
)


@dataclass(frozen=True)
class ResumenSmn:
    """What the SMN part of a run did, as integers (FRA-359). `smn_sin_datos` is 1 when the SMN feed could not be
    verified (`available=False`: "we do not know", never "no alerts"; nothing was sent or marked). Pairs (zone, alert):
    `smn_avisos` (notifiable storm alerts found over the zones with subscribers), `smn_avisadas` (at least one person
    was reached in this run), `smn_ya_avisadas` (already dispatched before: the dedupe key of T1 said so),
    `smn_omitidas` (not sent on purpose: the night rule of S7), `smn_errores` (the text, a read or a record of progress
    failed: the pair is not notified, fail-closed)."""

    smn_sin_datos: int = 0
    smn_avisos: int = 0
    smn_avisadas: int = 0
    smn_ya_avisadas: int = 0
    smn_omitidas: int = 0
    smn_errores: int = 0

    def sumar(self, otro: ResumenSmn) -> ResumenSmn:
        """A new summary with both added up (neither input changes)."""
        return ResumenSmn(**{n: getattr(self, n) + getattr(otro, n) for n in CONTADORES_SMN})

    def como_respuesta(self) -> dict[str, int]:
        return {nombre: getattr(self, nombre) for nombre in CONTADORES_SMN}

    def como_log(self) -> tuple[str, tuple[int, ...]]:
        """The fragment for the summary line of a run, in the shape of the existing counters (`nombre=%d ...`) and its
        arguments, so the caller appends it to the line with `" " + formato` and `argumentos`."""
        formato = " ".join(f"{nombre}=%d" for nombre in CONTADORES_SMN)
        return formato, tuple(getattr(self, nombre) for nombre in CONTADORES_SMN)


@dataclass(frozen=True)
class DespachoDeZona:
    """The outcome of one zone: what was counted, whether the RUN must stop (`corte`) and whether the zone could not
    be handled at all (`error`: the text, the reads or a record of progress failed)."""

    resumen: ResumenEnvio
    corte: str | None = None
    error: bool = False


@dataclass(frozen=True)
class AvisoSmn:
    """How an official SMN notice (FRA-359) is sent and recorded, instead of the forecast notice of (`aviso`, `fecha`):
    its own push `topic` (`envio.topic_smn`, so it never replaces the forecast push of the day), its own done-set
    (`clave_enviados`, whose expiry `ttl_enviados` is set once, like the forecast's) and when the notice expires
    (`vence`: the push service keeps an undelivered copy until then, never longer than usual). Built by `avisos_smn`;
    this module only reads it."""

    topic: str
    clave_enviados: str
    ttl_enviados: int
    vence: datetime | None = None


@dataclass(frozen=True)
class PlanDeZona:
    """What a zone has to send, read before anything is sent (so the time can be shared by what each zone has to do)."""

    slug: str
    aviso: str
    fecha: date
    payload: str = ""
    miembros: int = 0
    pendientes: tuple[str, ...] = ()
    error: bool = False
    # Set only for an official SMN notice (`AVISO_SMN`). None = the forecast notice of `aviso` and `fecha`, as always.
    smn: AvisoSmn | None = None


def _monotonico() -> float:
    """The clock of the run deadline: the event loop's monotonic clock. A function so the tests can move it."""
    return asyncio.get_running_loop().time()


@dataclass(frozen=True)
class Plazo:
    """A deadline on the monotonic clock (`limite`)."""

    limite: float

    @classmethod
    def desde_ahora(cls, segundos: float) -> Plazo:
        return cls(limite=_monotonico() + segundos)

    def restante(self) -> float:
        return self.limite - _monotonico()

    def vencido(self) -> bool:
        return self.restante() <= 0

    def recortado(self, segundos: float) -> Plazo:
        """A deadline that is this one, or `segundos` from now if that comes first."""
        return Plazo(limite=min(self.limite, _monotonico() + segundos))


@dataclass
class DisyuntorDeBajas:
    """Stops deleting subscriptions for the rest of a run when too many come back "gone" (see the module docstring).

    One per run, and mutable on purpose: it is the run's memory of what it saw and of what is waiting to be deleted.
    """

    abierto: bool = False
    total: int = 0
    bajas: int = 0
    borradas: int = 0  # the deletions actually made in this run, against `MAX_BAJAS_POR_CORRIDA`
    _a_borrar: list[tuple[str, str]] = field(default_factory=list)

    def registrar(self, total: int, bajas: int) -> None:
        """Add a finished batch to the run's totals and trip if the run, or this batch alone, is more than half gone."""
        self.total += total
        self.bajas += bajas
        if self.abierto:
            return
        en_el_lote = total >= LOTE_MINIMO_DEL_DISYUNTOR and bajas * 2 > total
        en_la_corrida = self.total >= LOTE_MINIMO_DEL_DISYUNTOR and self.bajas * 2 > self.total
        if en_el_lote or en_la_corrida:
            self.abierto = True
            logger.warning("alertas: too many gone subscriptions in this run; deletion is paused for the rest of the run")

    def diferir(self, slug: str, ids: Sequence[str]) -> None:
        self._a_borrar.extend((slug, sub_id) for sub_id in ids)

    async def cerrar_zona(self, redis: UpstashRedis, plazo: Plazo | None = None, detenido: bool = False) -> int:
        """A zone is closed: delete what is waiting if the run has enough evidence that it is healthy. Returns how many
        deletions were DROPPED (they are not `vencidos` after all): the breaker is open, the run was stopped
        (`detenido`: the kill key is present or unreadable), the run deadline passed or Upstash stopped answering."""
        return await self._resolver(redis, False, plazo, detenido)

    async def cerrar_corrida(self, redis: UpstashRedis, plazo: Plazo | None = None, detenido: bool = False) -> int:
        """The run is over: what is still waiting is decided with the run's totals. Returns the dropped ones."""
        return await self._resolver(redis, True, plazo, detenido)

    async def _resolver(self, redis: UpstashRedis, definitivo: bool, plazo: Plazo | None, detenido: bool) -> int:
        if not self._a_borrar:
            return 0
        if self.abierto or detenido:  # a stopped run deletes nothing, like an open breaker; they are tried in a later run
            descartadas = len(self._a_borrar)
            self._a_borrar.clear()
            return descartadas
        if self.total < LOTE_MINIMO_DEL_DISYUNTOR and not definitivo:  # too little seen to judge: wait, unless it is the end
            return 0
        pendientes, self._a_borrar = self._a_borrar, []
        for i, (slug, sub_id) in enumerate(pendientes):
            if self.borradas >= MAX_BAJAS_POR_CORRIDA:
                logger.warning("alertas: the cap of deletions per run was reached; the rest are tried in a later run")
                return len(pendientes) - i
            if (plazo is not None and plazo.vencido()) or not await _borrar(redis, sub_id, slug):
                # Out of time, or Upstash stopped answering (a call can take 5 s): drop the rest, a later run retries them.
                return len(pendientes) - i
            self.borradas += 1
        return 0


# ---------------------------------------------------------------------------
# Small pieces
# ---------------------------------------------------------------------------


async def _dormir(segundos: float) -> None:
    await asyncio.sleep(segundos)


async def esperar(segundos: float) -> None:
    """Wait `segundos`. The one place waiting happens, so the tests can replace it."""
    await _dormir(segundos)


def _ahora_real() -> datetime:
    return datetime.now(timezone.utc)


def cargar_vapid() -> ClaveVapid | None:
    """The VAPID key ready to sign, or None if there is none usable (the caller answers `sin_vapid`). Also None if the
    encryption self-test fails: with a broken library nothing is sent and, above all, nothing is deleted."""
    try:
        vapid = envio.cargar_vapid()
    except envio.VapidNoDisponibleError:
        return None
    return vapid if envio.autoprueba_de_cifrado() else None


def clave_de_enviados(slug: str, aviso: str, fecha: date) -> str:
    """The done-set of a notice: one per zone, notice level and target date. It holds the ids already reached."""
    return f"alertas:enviado:{slug}:{aviso}:{fecha:%Y-%m-%d}"


def segundos_hasta_el_silencio(ahora: datetime) -> float:
    """Seconds from `ahora` to 22:00 in Argentina (the start of the silence); 0 once it has started. The 21 h run must
    not keep sending after that."""
    local = ahora.astimezone(_AR)
    silencio = local.replace(hour=umbrales.SILENCIO_DESDE_H, minute=0, second=0, microsecond=0)
    return max(0.0, (silencio - local).total_seconds())


def ttl_de_aviso(aviso: str, ahora: datetime) -> int:
    """How long the push service keeps a notice it cannot deliver. The notice of TODAY is worthless after midnight
    (Argentina), so it expires then (never more than the usual 12 h, never less than a minute). Tomorrow's keeps the
    usual TTL: it is read the next morning."""
    if aviso == AVISO_MANANA:
        return envio.TTL_ALERTA_SEGUNDOS
    local = ahora.astimezone(_AR)
    medianoche = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(TTL_MINIMO_SEGUNDOS, min(envio.TTL_ALERTA_SEGUNDOS, int((medianoche - local).total_seconds())))


def ttl_hasta(vence: datetime | None, ahora: datetime) -> int:
    """How long the push service keeps an official SMN notice it cannot deliver: until the notice expires (`vence`),
    never more than the usual 12 h and never less than a minute. Without an expiry, the usual TTL. A naive `vence` is
    read as UTC (the CAP feed carries offsets: a guard, not the expected path)."""
    if vence is None:
        return envio.TTL_ALERTA_SEGUNDOS
    if vence.tzinfo is None:
        vence = vence.replace(tzinfo=timezone.utc)
    return max(TTL_MINIMO_SEGUNDOS, min(envio.TTL_ALERTA_SEGUNDOS, int((vence - ahora).total_seconds())))


def tope_para_zona(restante: float, pendientes: int, pendientes_restantes: int) -> float:
    """How many seconds a zone may take: the time left shared in proportion to its pendientes among the zones that still
    have something to send (`pendientes_restantes` includes this zone's), never less than the floor and never more than
    what is left. A big zone gets a big share (not the smallest one), a small one still gets its floor."""
    if restante <= 0:
        return 0.0
    parte = restante * pendientes / max(pendientes_restantes, 1)
    return min(restante, max(TOPE_MINIMO_DE_ZONA_SEGUNDOS, parte))


def _mensaje(slug: str, revision: ResultadoRegla, aviso: str) -> Mensaje:
    """The approved text for the notice: today or tomorrow, with the franjas and the hail inside the same notice."""
    zona = zona_por_slug(slug)
    if zona is None:
        raise ValueError("zona desconocida")
    franjas, granizo = franjas_de(revision), franjas_granizo(revision)
    if aviso == AVISO_HOY:
        return texto_aviso_hoy(zona, franjas, granizo=granizo)
    if aviso == AVISO_MANANA:
        return texto_aviso_manana(zona, franjas, granizo=granizo)
    raise ValueError("aviso desconocido")


async def _hay_corte(redis: UpstashRedis, plazo: Plazo) -> str | None:
    """Why the sending must stop before anything more, or None. The deadline first (it reads nothing); then the send
    switch (the flag AND the kill key, fail-closed). If the switch says no because the key could not be read, the key is
    read ONE more time before cutting: a blip of Upstash must not stop a run that nobody stopped."""
    if plazo.vencido():
        return CORTE_PLAZO
    return await corte_por_interruptor(redis)


async def corte_por_interruptor(redis: UpstashRedis) -> str | None:
    """Why the send switch (the flag AND the kill key, fail-closed) says stop, or None. The part of `_hay_corte` that reads
    Upstash; the evaluation uses it once before it starts the dispatch."""
    if await interruptor.envio_activo(redis):
        return None
    if not settings.alertas_envio_activo:
        return CORTE_APAGADO
    estado = await interruptor.estado_de_la_clave(redis)
    if estado == interruptor.CLAVE_AUSENTE:
        return None
    return CORTE_APAGADO if estado == interruptor.CLAVE_PRESENTE else CORTE_ILEGIBLE


# ---------------------------------------------------------------------------
# One subscriber
# ---------------------------------------------------------------------------


async def _intento(
    redis: UpstashRedis, vapid: ClaveVapid, sub_id: str, registro: str, payload: str, slug: str, fecha: date, ttl: int,
    topic: str | None = None,
) -> tuple[str, str | None]:
    """One attempt. `(_REINTENTAR, registro)` is the only answer that is worth another one. `topic` is the push Topic of
    an official SMN notice; without it the sender derives the forecast Topic from the zone and the date, as always."""
    # The Topic is passed only when there is one: a forecast send keeps calling the sender exactly as before.
    propio = {} if topic is None else {"topic": topic}
    try:
        # `borrar=False`: the sender reports a 404/410 but does not delete; this module deletes, behind the breaker.
        resultado = await envio.enviar(
            redis, sub_id, registro, payload, zona=slug, fecha=fecha, ttl=ttl, vapid=vapid, borrar=False, **propio
        )
    except Exception as exc:  # noqa: BLE001 - one subscriber must not stop the zone; only the class name is logged
        logger.warning("alertas: a send failed unexpectedly exc_type=%s", type(exc).__name__)
        return _FALLIDO, None
    if resultado is envio.Resultado.ENVIADA:
        return _ENVIADO, None
    if resultado is envio.Resultado.VENCIDA:
        return _GONE, None
    if resultado is envio.Resultado.INVALIDA:
        return _INVALIDO, None
    if resultado is envio.Resultado.ERROR:
        return _REINTENTAR, registro
    return _FALLIDO, None  # RECHAZADA: not retried, not deleted, not recorded (see the module docstring)


async def _borrar(redis: UpstashRedis, sub_id: str, slug: str) -> bool:
    """Delete a subscription that is gone or can never work (idempotent). `baja` finds the zone set in the record; a
    record that cannot be read has none, so the id is also taken out of the set it was found in."""
    try:
        await svc.baja(redis, sub_id)
        await redis.srem(svc.clave_de_zona(slug), sub_id)
    except (UpstashUnavailableError, svc.SuscripcionInvalida):
        logger.warning("alertas: a subscription to remove could not be deleted; it will be tried again")
        return False
    return True


async def _sin_registro(redis: UpstashRedis, sub_id: str, slug: str) -> str:
    """An id of the zone's set with no record: expired (180 days). Take it out of the indexes."""
    try:
        limpiado = await svc.limpiar_id_vencido(redis, sub_id, slug)
    except svc.LecturaDudosa:
        logger.warning("alertas: the re-read of an expired id was doubtful; nothing is cleaned, it will be tried again")
        return _FALLIDO  # not confirmed gone: not recorded as reached, not removed from the indexes
    except (UpstashUnavailableError, svc.SuscripcionInvalida):
        logger.warning("alertas: an expired id could not be cleaned from the indexes")
        return _VENCIDO  # the record IS gone; only the index cleanup failed
    # False: the person subscribed again between the read and the cleanup; there was no record to send to this time.
    return _VENCIDO if limpiado else _FALLIDO


async def _sacar_de_la_zona(redis: UpstashRedis, sub_id: str, slug: str) -> None:
    try:
        await redis.srem(svc.clave_de_zona(slug), sub_id)
    except UpstashUnavailableError:
        logger.warning("alertas: a stale member could not be taken out of a zone's set")


async def _enviar_uno(
    redis: UpstashRedis, vapid: ClaveVapid, plazo: Plazo, sub_id: str, payload: str, slug: str, fecha: date, ttl: int,
    topic: str | None = None,
) -> tuple[str, str | None]:
    """First attempt for one id: read and judge the record, then send. Returns an outcome and, for a transient failure,
    the record to retry with."""
    try:
        registro = await svc.registro_de(redis, sub_id)
    except (UpstashUnavailableError, svc.SuscripcionInvalida):
        logger.warning("alertas: a subscription record could not be read; nothing is sent to it")
        return _FALLIDO, None
    if registro is None:
        return await _sin_registro(redis, sub_id, slug), None
    suscripcion = envio.leer_registro(registro)
    if suscripcion is None:  # unreadable, or it no longer passes the validation (key off the curve, host outside the list)
        return _INVALIDO, None
    if suscripcion.zona != slug:  # a stale member: the person moved to another city
        await _sacar_de_la_zona(redis, sub_id, slug)
        return _OMITIDO, None
    return await _intento(redis, vapid, sub_id, registro, payload, slug, fecha, ttl, topic)


async def _reintentar_uno(
    redis: UpstashRedis, vapid: ClaveVapid, plazo: Plazo, sub_id: str, payload: str, slug: str, fecha: date, ttl: int,
    registro: str, topic: str | None = None,
) -> tuple[str, str | None]:
    """The single retry of a transient failure: whatever it answers is final."""
    estado, _ = await _intento(redis, vapid, sub_id, registro, payload, slug, fecha, ttl, topic)
    return (_FALLIDO, None) if estado == _REINTENTAR else (estado, None)


# ---------------------------------------------------------------------------
# One zone
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Lote:
    """A counted batch: the summary, the ids to retry (with their records) and the ids to record as done."""

    resumen: ResumenEnvio
    reintentar: tuple[tuple[str, str], ...]
    hechos: tuple[str, ...]


def _contar_lote(
    ids: Sequence[str], resultados: Sequence[object], disyuntor: DisyuntorDeBajas, slug: str
) -> _Lote:
    """Count a finished batch. Nothing is deleted here: the ids that are gone or invalid are handed to the breaker."""
    normales: list[tuple[str, str | None]] = []
    for resultado in resultados:
        if isinstance(resultado, asyncio.CancelledError):
            raise resultado
        if isinstance(resultado, BaseException):  # never raised: it becomes one more failed send, class name only
            logger.warning("alertas: a send ended with an exception exc_type=%s", type(resultado).__name__)
            normales.append((_FALLIDO, None))
        else:
            normales.append(resultado)  # type: ignore[arg-type]
    estados = [estado for estado, _ in normales]
    # A send that was judged (not a stale member, not an id without a record) counts for the breaker's totals.
    juzgados = sum(1 for estado in estados if estado not in (_OMITIDO, _VENCIDO))
    disyuntor.registrar(juzgados, sum(1 for estado in estados if estado in (_GONE, _INVALIDO)))
    cuenta: Counter[str] = Counter()
    reintentar: list[tuple[str, str]] = []
    hechos: list[str] = []
    a_borrar: list[str] = []
    for sub_id, (estado, registro) in zip(ids, normales):
        if estado in (_GONE, _INVALIDO):
            a_borrar.append(sub_id)
            estado = _VENCIDO  # counted as gone for good; if the breaker drops the deletion it is turned into `fallidos`
        if estado in _HECHOS:
            hechos.append(sub_id)
        if estado == _REINTENTAR and registro is not None:
            reintentar.append((sub_id, registro))
        else:
            cuenta[estado] += 1
    disyuntor.diferir(slug, a_borrar)
    resumen = ResumenEnvio(enviados=cuenta[_ENVIADO], vencidos=cuenta[_VENCIDO], fallidos=cuenta[_FALLIDO])
    return _Lote(resumen, tuple(reintentar), tuple(hechos))


async def _anotar(redis: UpstashRedis, clave: str, ids: Sequence[str], ttl: int = ENVIADOS_TTL_SEGUNDOS) -> bool:
    """Record the ids that were reached (one SADD for the batch, and the expiry `ttl` set once). False if Upstash
    failed: the caller stops the zone, because sending without recording would repeat people on the next run."""
    if not ids:
        return True
    try:
        await redis.sadd(clave, *ids)
        await redis.expire_si_falta(clave, ttl)
    except UpstashUnavailableError:
        logger.warning("alertas: Upstash did not answer recording who was reached; the zone stops here")
        return False
    return True


@dataclass(frozen=True)
class _ResultadoDeZona:
    resumen: ResumenEnvio
    corte: str | None = None
    error: bool = False


async def _enviar_a_todos(
    redis: UpstashRedis, vapid: ClaveVapid, plazo: Plazo, ids: Sequence[str], payload: str, slug: str, fecha: date,
    ttl: int, disyuntor: DisyuntorDeBajas, clave: str, ttl_enviados: int = ENVIADOS_TTL_SEGUNDOS,
    topic: str | None = None,
) -> _ResultadoDeZona:
    """Batches of `ENVIOS_POR_LOTE`. Before EACH batch (the first too) the zone cap, the deadline and the send switch are
    checked; after each, the ids reached are recorded (in the done-set `clave`, whose expiry `ttl_enviados` is set
    once) before the next one goes out. The transient failures wait for ONE final tanda (one wait, then all of them
    together). `topic` is the push Topic of an official SMN notice; None = the forecast's."""
    resumen = ResumenEnvio()
    pendientes: list[tuple[str, str]] = []
    lotes = [ids[i : i + ENVIOS_POR_LOTE] for i in range(0, len(ids), ENVIOS_POR_LOTE)]
    for n, lote in enumerate(lotes):
        corte = await _hay_corte(redis, plazo)
        if corte is not None:
            sin_probar = sum(len(resto) for resto in lotes[n:])
            return _ResultadoDeZona(resumen.sumar(ResumenEnvio(fallidos=len(pendientes), diferidos=sin_probar)), corte)
        resultados = await asyncio.gather(
            *(_enviar_uno(redis, vapid, plazo, i, payload, slug, fecha, ttl, topic) for i in lote),
            return_exceptions=True,
        )
        contado = _contar_lote(lote, resultados, disyuntor, slug)
        resumen, pendientes = resumen.sumar(contado.resumen), pendientes + list(contado.reintentar)
        if not await _anotar(redis, clave, contado.hechos, ttl_enviados):
            sin_probar = sum(len(resto) for resto in lotes[n + 1 :])
            return _ResultadoDeZona(resumen.sumar(ResumenEnvio(fallidos=len(pendientes), diferidos=sin_probar)), error=True)
    if not pendientes:
        return _ResultadoDeZona(resumen)
    corte = await _hay_corte(redis, plazo)
    if corte is not None:
        return _ResultadoDeZona(resumen.sumar(ResumenEnvio(fallidos=len(pendientes))), corte)
    await esperar(ESPERA_REINTENTO_SEGUNDOS)
    tandas = [pendientes[i : i + ENVIOS_POR_LOTE] for i in range(0, len(pendientes), ENVIOS_POR_LOTE)]
    for n, tanda in enumerate(tandas):
        if n > 0:
            corte = await _hay_corte(redis, plazo)
            if corte is not None:
                resto = sum(len(t) for t in tandas[n:])
                return _ResultadoDeZona(resumen.sumar(ResumenEnvio(fallidos=resto)), corte)
        resultados = await asyncio.gather(
            *(_reintentar_uno(redis, vapid, plazo, i, payload, slug, fecha, ttl, r, topic) for i, r in tanda),
            return_exceptions=True,
        )
        contado = _contar_lote([i for i, _ in tanda], resultados, disyuntor, slug)
        resumen = resumen.sumar(contado.resumen)
        if not await _anotar(redis, clave, contado.hechos, ttl_enviados):
            resto = sum(len(t) for t in tandas[n + 1 :])
            return _ResultadoDeZona(resumen.sumar(ResumenEnvio(fallidos=resto)), error=True)
    return _ResultadoDeZona(resumen)


async def leer_plan(
    redis: UpstashRedis, *, slug: str, aviso: str, fecha: date, payload: str, clave_enviados: str,
    smn: AvisoSmn | None = None,
) -> PlanDeZona:
    """Read what the zone has to send for a notice whose `payload` is already built: the members and the done-set
    `clave_enviados` (SMEMBERS twice, nothing written). Either read failing is an `error` plan: the zone is not notified
    (fail-closed)."""
    try:
        miembros = await redis.smembers(svc.clave_de_zona(slug))
    except UpstashUnavailableError:
        logger.warning("alertas: Upstash did not answer reading the recipients; the zone is not notified")
        return PlanDeZona(slug, aviso, fecha, error=True, smn=smn)
    if not miembros:
        return PlanDeZona(slug, aviso, fecha, payload, smn=smn)  # nobody left: nothing to send
    try:
        hechos = await redis.smembers(clave_enviados)
    except UpstashUnavailableError:
        logger.warning("alertas: Upstash did not answer reading who was reached; the zone is not notified")
        return PlanDeZona(slug, aviso, fecha, error=True, smn=smn)
    return PlanDeZona(slug, aviso, fecha, payload, len(miembros), tuple(sorted(miembros - hechos)), smn=smn)


async def preparar_zona(
    redis: UpstashRedis, *, slug: str, revision: ResultadoRegla, aviso: str, fecha: date
) -> PlanDeZona:
    """Read what the zone has to send: the text, the members and the done-set (SMEMBERS twice, nothing written). Any
    failure (the text, either read) is an `error` plan: the zone is not notified (fail-closed)."""
    try:
        payload = envio.construir_payload(_mensaje(slug, revision, aviso), tag=envio.tag_de(slug, fecha))
    except ValueError:
        logger.warning("alertas: the notice could not be built; the zone is not notified")
        return PlanDeZona(slug, aviso, fecha, error=True)
    return await leer_plan(
        redis, slug=slug, aviso=aviso, fecha=fecha, payload=payload, clave_enviados=clave_de_enviados(slug, aviso, fecha)
    )


def _destino(plan: PlanDeZona, ahora: datetime) -> tuple[int, str, int, str | None]:
    """The push TTL, the done-set, its expiry and the push Topic of a plan: the forecast's (derived from `aviso`, `fecha`
    and the zone, exactly as before) or the official SMN notice's (carried by `plan.smn`)."""
    if plan.smn is None:
        clave = clave_de_enviados(plan.slug, plan.aviso, plan.fecha)
        return ttl_de_aviso(plan.aviso, ahora), clave, ENVIADOS_TTL_SEGUNDOS, None
    return ttl_hasta(plan.smn.vence, ahora), plan.smn.clave_enviados, plan.smn.ttl_enviados, plan.smn.topic


async def despachar_plan(
    redis: UpstashRedis,
    plan: PlanDeZona,
    *,
    vapid: ClaveVapid,
    plazo: Plazo,
    reloj: Callable[[], datetime] | None = None,
    tope_de_zona: float | None = None,
    disyuntor: DisyuntorDeBajas | None = None,
) -> DespachoDeZona:
    """Send to the pendientes of a prepared zone. Never raises (a failure becomes `error` or a counter).

    `tope_de_zona` is the most this zone may take, in seconds (see `tope_para_zona`); `reloj` gives the wall-clock time
    for the TTL of the notice.
    """
    if plan.error:
        return DespachoDeZona(ResumenEnvio(), error=True)
    if plan.miembros == 0:
        return DespachoDeZona(ResumenEnvio())
    if not plan.pendientes:
        return DespachoDeZona(ResumenEnvio(ya_avisadas=1))
    if plazo.vencido():
        return DespachoDeZona(ResumenEnvio(diferidos=len(plan.pendientes)), corte=CORTE_PLAZO)
    disyuntor = disyuntor or DisyuntorDeBajas()
    plazo_de_zona = plazo if tope_de_zona is None else plazo.recortado(tope_de_zona)
    ttl, clave, ttl_enviados, topic = _destino(plan, (reloj or _ahora_real)())
    hecho = await _enviar_a_todos(
        redis, vapid, plazo_de_zona, plan.pendientes, plan.payload, plan.slug, plan.fecha, ttl, disyuntor, clave,
        ttl_enviados, topic,
    )
    detenido = hecho.corte in (CORTE_APAGADO, CORTE_ILEGIBLE)
    descartadas = await disyuntor.cerrar_zona(redis, plazo, detenido)  # deletions are decided when the zone is closed
    resumen = hecho.resumen.sumar(ResumenEnvio(vencidos=-descartadas, fallidos=descartadas))
    if resumen.enviados > 0:
        resumen = resumen.sumar(ResumenEnvio(avisadas=1))
    # The cap of the zone ends THIS zone only; the run stops only if the run's own deadline (or the switch) says so.
    corte = None if hecho.corte == CORTE_PLAZO and not plazo.vencido() else hecho.corte
    return DespachoDeZona(resumen, corte=corte, error=hecho.error)


async def despachar_zona(
    redis: UpstashRedis,
    *,
    vapid: ClaveVapid,
    plazo: Plazo,
    slug: str,
    suscriptores: int,
    revision: ResultadoRegla,
    aviso: str,
    fecha: date,
    reloj: Callable[[], datetime] | None = None,
    tope_de_zona: float | None = None,
    disyuntor: DisyuntorDeBajas | None = None,
) -> DespachoDeZona:
    """`preparar_zona` and `despachar_plan` in one call (the run prepares all its zones first, to share the time).

    `suscriptores` is the size of the zone's set counted when the zones were listed: it is what `diferidos` reports if
    the run deadline has already passed (then nothing is read at all).
    """
    if plazo.vencido():
        return DespachoDeZona(ResumenEnvio(diferidos=suscriptores), corte=CORTE_PLAZO)
    plan = await preparar_zona(redis, slug=slug, revision=revision, aviso=aviso, fecha=fecha)
    return await despachar_plan(
        redis, plan, vapid=vapid, plazo=plazo, reloj=reloj, tope_de_zona=tope_de_zona, disyuntor=disyuntor
    )


async def podar_zonas_vacias(redis: UpstashRedis, slugs: Sequence[str]) -> None:
    """Take the zones with no subscribers out of `alertas:zonas`. The set is counted again right before the SREM and once
    more right after it (a person may have subscribed in between): if it has someone now, the zone is put back with SADD.
    A failure leaves the zone listed: the next run tries again."""
    for slug in slugs:
        try:
            clave = svc.clave_de_zona(slug)
            if await redis.scard(clave) != 0:
                continue
            await redis.srem(svc.CLAVE_ZONAS, slug)
            if await redis.scard(clave) > 0:
                await redis.sadd(svc.CLAVE_ZONAS, slug)
        except UpstashUnavailableError:
            logger.warning("alertas: an empty zone could not be taken out of the index; it stays listed")
            return
