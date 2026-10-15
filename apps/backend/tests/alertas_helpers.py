"""Shared helpers for the alert-evaluation tests (FRA-355, PR5b).

Used by `test_alertas_pronostico.py`, `test_alertas_evaluacion.py`, `test_alertas_con_clave.py`,
`test_alertas_evaluar.py` and `test_alertas_evaluar_router.py`. Nothing here is a test and nothing is collected from this
module: a test file imports the helpers and fixtures it uses by name (`estado_de_alertas_limpio` is autouse once imported).

- time: `AHORA` (a fixed review moment) and `reloj_de_openmeteo` (the clock that stamps `fetched_at` inside the parser);
- Open-Meteo: `payload_horario` (an hourly payload), `TORMENTA` / `CALMA`, `respuestas_por_zona`;
- Upstash: `suscribir` (subscribers straight into the fake), `comandos`, and `UpstashRedis` subclasses that fail or
  count on purpose;
- the HTTP endpoint: `llamar_evaluar` and the fixtures that set the flags and the signing keys.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
import respx
from httpx import AsyncClient

import app.services.openmeteo as om_module
from app.core import usage_counter
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.upstash import UpstashRedis, UpstashUnavailableError, configure_redis
from app.services.alertas import despacho, envio, evaluacion, firma_qstash
from app.services.alertas import suscripcion as svc
from app.services.alertas.zonas import zona_por_slug
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL, nuevo_receptor
from tests.qstash_helpers import CLAVE_ACTUAL, CLAVE_SIGUIENTE, URL_EVALUAR, firmar

# ---------------------------------------------------------------------------
# Constants (names that are a contract, not a detail)
# ---------------------------------------------------------------------------

AR = timezone(timedelta(hours=-3))
# Wednesday 14 October 2026, 10:30 in Argentina: the 10 h review, window = 10:00 .. 24:00 of the 14th.
AHORA = datetime(2026, 10, 14, 10, 30, tzinfo=AR)
DIA0 = datetime(2026, 10, 14, 0, 0, tzinfo=AR)  # where Open-Meteo's two-day series starts

CLAVE_LOCK = "alertas:lock:evaluar"
CLAVE_LOCK_SMN = "alertas:lock:evaluar-smn"  # FRA-359 (T4): the lock of the "SMN only" run, its own
CLAVE_APAGADO = "alertas:apagado"  # the name used in the Upstash console
OM_URL = "https://api.open-meteo.com/v1/forecast"
RUTA = "/api/alertas/evaluar"
CABECERA = "Upstash-Signature"
CUERPO = b'{"origen":"qstash","regla":"tormenta"}'
CUERPO_SMN = b'{"modo":"smn"}'  # FRA-359 (T4): the body the SMN schedule sends (the signature covers it)
NO_AUTORIZADO = {"detail": "no_autorizado"}

# The counters (and only the counters) that the HTTP response may carry next to `estado`.
CONTADORES_HTTP = (
    "zonas_con_suscriptores",
    "evaluadas",
    "con_tormenta",
    "sin_tormenta",
    "sin_datos",
    "errores",
    "diferidas",
    "desconocidas",
)
# PR5c: what a run that SENDS adds to the response (counts only: never ids, endpoints, keys or texts).
CONTADORES_ENVIO_HTTP = (
    "avisadas",
    "ya_avisadas",
    "enviados",
    "vencidos",
    "fallidos",
    "diferidos",
    "reintentadas",
)
# FRA-359 (T4): what the "SMN only" run answers next to `estado` (pairs zone × alert, whole numbers only).
CONTADORES_SMN_HTTP = (
    "smn_sin_datos",
    "smn_avisos",
    "smn_avisadas",
    "smn_ya_avisadas",
    "smn_omitidas",
    "smn_errores",
)
AHORA_21H = datetime(2026, 10, 14, 21, 10, tzinfo=AR)  # the review that looks at TOMORROW (the 15th)
CLAVE_ENVIADOS_HOY = "alertas:enviado:cordoba:hoy:2026-10-14"  # the SET of ids already reached
CLAVE_ENVIADOS_MANANA = "alertas:enviado:cordoba:manana:2026-10-15"


# ---------------------------------------------------------------------------
# Open-Meteo payloads and clock
# ---------------------------------------------------------------------------


def payload_horario(
    *,
    horas: int = 48,
    codigos: Mapping[int, int | None] | None = None,
    cape: Mapping[int, float | None] | None = None,
    codigo_base: int | None = 1,
    cape_base: float | None = 100.0,
) -> dict:
    """An Open-Meteo hourly payload from 00:00 of the 14th. `codigos`/`cape` set values by hour index
    (0 = 00:00 of the 14th, 24 = 00:00 of the 15th); the rest is calm (code 1, CAPE 100 J/kg)."""
    tiempos = [(DIA0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(horas)]
    weather_code: list[int | None] = [codigo_base] * horas
    cape_lista: list[float | None] = [cape_base] * horas
    for indice, valor in (codigos or {}).items():
        weather_code[indice] = valor
    for indice, valor in (cape or {}).items():
        cape_lista[indice] = valor
    return {"hourly": {"time": tiempos, "weather_code": weather_code, "cape": cape_lista}, "elevation": 120.0}


TORMENTA = payload_horario(codigos={15: 95})
CALMA = payload_horario()


@pytest.fixture
def reloj_de_openmeteo(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Freeze the clock the hourly parser uses for `fetched_at` (it stamps `datetime.now(timezone.utc)` while
    parsing). `reloj.instante` is the moment "we fetched it"; the default is AHORA, so the data is brand new."""
    reloj = SimpleNamespace(instante=AHORA)

    class _Datetime(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            return reloj.instante.astimezone(tz) if tz is not None else reloj.instante.replace(tzinfo=None)

    monkeypatch.setattr(om_module, "datetime", _Datetime)
    return reloj


def respuestas_por_zona(respuestas: Mapping[str, object], por_defecto: object = None):
    """A `respond` for `FakeOpenMeteoSource` that answers by the coordinates of each zone."""
    por_coordenadas = {(zona_por_slug(slug).lat, zona_por_slug(slug).lon): r for slug, r in respuestas.items()}
    return lambda params: por_coordenadas.get((params["latitude"], params["longitude"]), por_defecto)


class FuenteQueSeCuelga:
    """An Open-Meteo source that answers `respuestas` by zone and NEVER answers the zones in `cuelgan` (it waits for
    an hour). For the run-deadline tests: the deadline, not the source, must end the run."""

    def __init__(self, respuestas: Mapping[str, object], cuelgan: set[str]) -> None:
        self._respuestas = respuestas_por_zona(respuestas)
        self._cuelgan = {(zona_por_slug(s).lat, zona_por_slug(s).lon) for s in cuelgan}
        self.calls: list[dict] = []

    async def get_json(self, params, failure_message, *log_args):  # noqa: ANN001, ANN201
        self.calls.append(dict(params))
        if (params["latitude"], params["longitude"]) in self._cuelgan:
            await asyncio.sleep(3600)
        return self._respuestas(params)


# ---------------------------------------------------------------------------
# Upstash
# ---------------------------------------------------------------------------


@pytest.fixture
def redis(fake_upstash) -> UpstashRedis:
    return UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)


def suscribir(fake_upstash, *slugs: str, cantidad: int = 1) -> None:
    """Register `cantidad` synthetic subscribers in each zone, straight into the fake's sets."""
    for slug in slugs:
        fake_upstash.sets.setdefault("alertas:zonas", set()).add(slug)
        fake_upstash.sets.setdefault(f"alertas:zona:{slug}", set()).update(
            f"ID-SECRETO-{slug}-{i:03d}" for i in range(cantidad)
        )


def comandos(fake_upstash) -> list[str]:
    return [comando[0] for comando in fake_upstash.commands]


def conteo_del_dia(dia: str, *campos: tuple[str, int]) -> list[list[str]]:
    """The commands the router adds AFTER a run (or an alta/baja) for the daily counters of FRA-360: one HINCRBY per
    field different from zero on the hash of the Argentine day `dia` (`YYYY-MM-DD`), then its 40-day expiry (NX)."""
    clave = f"alertas:metricas:{dia}"
    return [["HINCRBY", clave, campo, str(valor)] for campo, valor in campos] + [["EXPIRE", clave, "3456000", "NX"]]


def lineas_de_resumen(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The one summary line (state and counters) that a FORECAST run of the evaluation logs (never the SMN one)."""
    return [
        r for r in caplog.records
        if r.name == evaluacion.logger.name and r.getMessage().startswith("alertas: evaluation estado=")
    ]


def lineas_de_resumen_smn(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The one summary line of an "SMN only" run (FRA-359, T4): distinct from the forecast's on purpose."""
    return [
        r for r in caplog.records
        if r.name == evaluacion.logger.name and r.getMessage().startswith("alertas: smn evaluation estado=")
    ]


class RedisConFalla(UpstashRedis):
    """An `UpstashRedis` whose chosen commands fail like an unreachable Upstash."""

    def __init__(self, *fallan: str) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._fallan = set(fallan)

    async def _call_body(self, *command: str, require_result: bool = False):
        if command[0] in self._fallan:
            raise UpstashUnavailableError("caido")
        return await super()._call_body(*command, require_result=require_result)


class RedisSinSet(UpstashRedis):
    """The run lock (SET NX) cannot be taken: Upstash does not answer it."""

    async def set_nx(self, key: str, value: str, ex: int) -> bool:
        raise UpstashUnavailableError("caido")


class LecturaQueSeRompe(UpstashRedis):
    """The kill key reads fine `buenas` times and then Upstash stops answering."""

    def __init__(self, buenas: int) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._buenas = buenas

    async def read_strict(self, key: str) -> str | None:
        if key != CLAVE_APAGADO:  # only the kill key is counted; a subscription record reads normally
            return await super().read_strict(key)
        if self._buenas <= 0:
            raise UpstashUnavailableError("caido")
        self._buenas -= 1
        return await super().read_strict(key)


class RedisConLecturaDudosa(UpstashRedis):
    """Upstash answering 200 WITHOUT `result` to the GET of a subscription record (`solo` limits it to one id). The first
    `normales` such reads answer normally. A plain `read` turns that answer into None ("no record"); `read_strict`
    refuses it, like the real client does."""

    def __init__(self, solo: str | None = None, normales: int = 0) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._solo, self._normales, self.lecturas = solo, normales, 0

    async def _call_body(self, *command: str, require_result: bool = False):
        if command[0] == "GET" and command[1].startswith("alertas:sub:") and (
            self._solo is None or command[1].endswith(self._solo)
        ):
            self.lecturas += 1
            if self.lecturas > self._normales:
                if require_result:
                    raise UpstashUnavailableError("sin_result")
                return None
        return await super()._call_body(*command, require_result=require_result)


class RedisEnMemoria(UpstashRedis):
    """Upstash without HTTP: the lock is free, the kill key is absent and the given zones have one subscriber."""

    def __init__(self, *slugs: str) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._slugs = frozenset(slugs)

    async def set_nx(self, key: str, value: str, ex: int) -> bool:
        return True

    async def read_strict(self, key: str) -> str | None:
        return None

    async def smembers(self, key: str) -> frozenset[str]:
        return self._slugs

    async def scard(self, key: str) -> int:
        return 1


class RedisQueMideConcurrencia(UpstashRedis):
    """Counts how many SCARDs are in flight at the same time (the fan-out over the zones must stay bounded)."""

    def __init__(self) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._en_vuelo = 0
        self.max_simultaneos = 0

    async def scard(self, key: str) -> int:
        self._en_vuelo += 1
        self.max_simultaneos = max(self.max_simultaneos, self._en_vuelo)
        try:
            await asyncio.sleep(0.005)  # long enough for the other SCARDs of the fan-out to start
            return await super().scard(key)
        finally:
            self._en_vuelo -= 1


@pytest.fixture
def open_meteo_real(monkeypatch):
    """The real HTTP source (pause and budget included) with Open-Meteo answered by respx."""
    monkeypatch.setattr(usage_counter, "record", lambda proveedor: None)
    with respx.mock(assert_all_called=False) as router:
        yield router.get(OM_URL).mock(return_value=httpx.Response(200, json=CALMA))


# ---------------------------------------------------------------------------
# The HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def estado_de_alertas_limpio(monkeypatch):
    """Rate limiter, signing keys, URL, both flags off and no Upstash configured: the starting point of every test."""
    limiter.reset()
    firma_qstash.reset_aviso_de_configuracion_para_tests()
    configure_redis(None)
    monkeypatch.setattr(settings, "qstash_current_signing_key", CLAVE_ACTUAL)
    monkeypatch.setattr(settings, "qstash_next_signing_key", CLAVE_SIGUIENTE)
    monkeypatch.setattr(settings, "alertas_evaluar_url", URL_EVALUAR)
    monkeypatch.setattr(settings, "alertas_envio_activo", False)
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", False)
    yield
    limiter.reset()
    configure_redis(None)


@pytest.fixture
def envio_activo(monkeypatch):
    monkeypatch.setattr(settings, "alertas_envio_activo", True)


@pytest.fixture
def en_seco(monkeypatch):
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", True)


@pytest.fixture
def evaluador_inerte(monkeypatch):
    """The PR5a evaluator: does nothing and answers `listo`. For the tests that look only at the router."""

    async def evaluar_inerte(redis, ahora, *, enviar=False, reloj=None):
        return evaluacion.ResultadoEvaluacion(estado="listo")

    monkeypatch.setattr(evaluacion, "evaluar", evaluar_inerte)


async def llamar_evaluar(client: AsyncClient, cuerpo: bytes = CUERPO, firma: str | None = "auto", **headers):
    """POST /api/alertas/evaluar signed like QStash (`firma="auto"`), unsigned (`None`) or with the given signature."""
    cabeceras = {"Content-Type": "application/json", **headers}
    if firma == "auto":
        firma = firmar(cuerpo)
    if firma is not None:
        cabeceras[CABECERA] = firma
    return await client.post(RUTA, content=cuerpo, headers=cabeceras)


# ---------------------------------------------------------------------------
# Sending (PR5c): real subscriptions, a recording stand-in for `envio.enviar`, no real waiting
# ---------------------------------------------------------------------------


def endpoint_de(slug: str, i: int) -> str:
    return f"https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-{slug}-{i:03d}"


async def registrar(redis: UpstashRedis, slug: str, cantidad: int = 1) -> list[str]:
    """Store `cantidad` REAL subscriptions (valid keys, so the real sender can encrypt to them); return their ids."""
    ids: list[str] = []
    for i in range(cantidad):
        receptor = nuevo_receptor(endpoint_de(slug, i))
        ids.append(await svc.alta(redis, svc.Suscripcion(receptor.endpoint, receptor.p256dh, receptor.auth, slug)))
    return ids


def respuestas_en_orden(respuestas: Mapping[str, list[object]]) -> Callable[[dict], object]:
    """A `respond` for `FakeOpenMeteoSource`: each zone gets its list of answers in order (the last one repeats).
    `respond.cuenta` says how many times each zone was asked."""
    cuenta: Counter[str] = Counter()
    slug_de = {(zona_por_slug(s).lat, zona_por_slug(s).lon): s for s in respuestas}

    def respond(params: dict) -> object:
        slug = slug_de[(params["latitude"], params["longitude"])]
        lista = respuestas[slug]
        valor = lista[min(cuenta[slug], len(lista) - 1)]
        cuenta[slug] += 1
        return valor

    respond.cuenta = cuenta  # type: ignore[attr-defined]
    return respond


@pytest.fixture
def esperas(own_caches, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Nothing waits for real: `despacho._dormir` records the seconds it was asked to wait and returns at once. Like the
    real wait, it lets the 15 s failure memory of the Open-Meteo caches expire."""
    registro: list[float] = []

    async def dormir(segundos: float) -> None:
        registro.append(segundos)
        for cache in own_caches.caches.values():
            cache._failure_cache.clear()

    monkeypatch.setattr(despacho, "_dormir", dormir)
    return registro


class RelojDeTest:
    """The wall clock of a run, driven by the test: `ahora` only moves when the test (or a fake send) moves it."""

    def __init__(self, inicio: datetime) -> None:
        self.ahora = inicio

    def __call__(self) -> datetime:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora = self.ahora + timedelta(seconds=segundos)


class DesfaseDelBucle:
    """The monotonic clock of the run deadline (`despacho._monotonico`): the event loop's clock plus an offset that
    the test moves. The offset only ever makes time pass faster, so the real `asyncio.timeout_at` stays consistent."""

    def __init__(self) -> None:
        self.desfase = 0.0

    def avanzar(self, segundos: float) -> None:
        self.desfase += segundos


@pytest.fixture
def reloj_del_bucle(monkeypatch: pytest.MonkeyPatch) -> DesfaseDelBucle:
    """Time for the run deadline passes only when a test says so (no test waits for a real deadline)."""
    desfase = DesfaseDelBucle()
    monkeypatch.setattr(despacho, "_monotonico", lambda: asyncio.get_running_loop().time() + desfase.desfase)
    return desfase


class PushFalso:
    """Stands in for `envio.enviar`: records every call, answers by subscription id and measures concurrency.

    `resultados[sub_id]` is the list of answers for that subscription in order (the last repeats; default ENVIADA); an
    exception instance in the list is raised. `al_llamar(n)` runs on the n-th call. `cesiones` makes each call yield
    to the event loop that many times (so the calls of a batch overlap, with no real waiting). `avance` is what each
    call adds to `reloj_del_bucle` (the run deadline's clock) and to `reloj` (the wall clock of the run), in seconds.
    A `Resultado.VENCIDA` answer deletes the subscription only if `borrar` is true, as the real `enviar` does.
    """

    def __init__(self, fake_upstash, redis: UpstashRedis) -> None:
        self._fake = fake_upstash
        self._redis = redis
        self.llamadas: list[SimpleNamespace] = []
        self.resultados: dict[str, list[object]] = {}
        self.al_llamar: Callable[[int], None] | None = None
        self.cesiones = 0
        self.avance = 0.0
        self.bucle: DesfaseDelBucle | None = None
        self.reloj: RelojDeTest | None = None
        self.en_vuelo = 0
        self.max_en_vuelo = 0
        self.vencida_borra = True

    def hechos(self) -> int:
        """How many ids are recorded as already reached, in all the done-sets, at this moment."""
        return sum(len(v) for k, v in self._fake.sets.items() if k.startswith("alertas:enviado:"))

    async def __call__(  # noqa: ANN001
        self, redis, sub_id, registro, payload, *, zona, fecha, ttl=None, vapid=None, borrar=True
    ):
        previas = sum(1 for c in self.llamadas if c.sub_id == sub_id)
        self.llamadas.append(
            SimpleNamespace(
                sub_id=sub_id, registro=registro, payload=json.loads(payload), zona=zona, fecha=fecha, ttl=ttl,
                vapid=vapid, borrar=borrar, hechos=self.hechos(),
            )
        )
        if self.al_llamar:
            self.al_llamar(len(self.llamadas))
        if self.avance:
            if self.bucle is not None:
                self.bucle.avanzar(self.avance)
            if self.reloj is not None:
                self.reloj.avanzar(self.avance)
        self.en_vuelo += 1
        self.max_en_vuelo = max(self.max_en_vuelo, self.en_vuelo)
        try:
            for _ in range(self.cesiones):
                await asyncio.sleep(0)
        finally:
            self.en_vuelo -= 1
        lista = self.resultados.get(sub_id, [envio.Resultado.ENVIADA])
        resultado = lista[min(previas, len(lista) - 1)]
        if isinstance(resultado, BaseException):
            raise resultado
        if resultado is envio.Resultado.VENCIDA and self.vencida_borra and borrar:
            await svc.baja(self._redis, sub_id)
        return resultado

    def a(self, sub_id: str) -> list[SimpleNamespace]:
        return [c for c in self.llamadas if c.sub_id == sub_id]


@pytest.fixture
def push(monkeypatch: pytest.MonkeyPatch, fake_upstash, redis: UpstashRedis, vapid_efimera) -> PushFalso:
    """`envio.enviar` replaced by a recording fake, with a VAPID key loaded (the run refuses to send without one)."""
    falso = PushFalso(fake_upstash, redis)
    monkeypatch.setattr(envio, "enviar", falso)
    return falso


class LecturaQueFallaUnaVez(UpstashRedis):
    """The kill key fails to read on the `n`-th read only (a blip); every other read answers normally."""

    def __init__(self, n: int) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._n, self.lecturas = n, 0

    async def read_strict(self, key: str) -> str | None:
        if key != CLAVE_APAGADO:  # only the kill key is counted; a subscription record reads normally
            return await super().read_strict(key)
        self.lecturas += 1
        if self.lecturas == self._n:
            raise UpstashUnavailableError("caido")
        return await super().read_strict(key)


async def correr(
    redis: UpstashRedis, ahora: datetime = AHORA, reloj: Callable[[], datetime] | None = None
) -> evaluacion.ResultadoEvaluacion:
    """A run that SENDS (what the router does when `interruptor.envio_activo` is true)."""
    return await evaluacion.evaluar(redis, ahora, enviar=True, reloj=reloj)
