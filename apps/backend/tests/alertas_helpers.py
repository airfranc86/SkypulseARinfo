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
import logging
from collections.abc import Mapping
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
from app.services.alertas import evaluacion, firma_qstash
from app.services.alertas.zonas import zona_por_slug
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.qstash_helpers import CLAVE_ACTUAL, CLAVE_SIGUIENTE, URL_EVALUAR, firmar

# ---------------------------------------------------------------------------
# Constants (names that are a contract, not a detail)
# ---------------------------------------------------------------------------

AR = timezone(timedelta(hours=-3))
# Wednesday 14 October 2026, 10:30 in Argentina: the 10 h review, window = 10:00 .. 24:00 of the 14th.
AHORA = datetime(2026, 10, 14, 10, 30, tzinfo=AR)
DIA0 = datetime(2026, 10, 14, 0, 0, tzinfo=AR)  # where Open-Meteo's two-day series starts

CLAVE_LOCK = "alertas:lock:evaluar"
CLAVE_APAGADO = "alertas:apagado"  # the name used in the Upstash console
OM_URL = "https://api.open-meteo.com/v1/forecast"
RUTA = "/api/alertas/evaluar"
CABECERA = "Upstash-Signature"
CUERPO = b'{"origen":"qstash","regla":"tormenta"}'
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


def lineas_de_resumen(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The one summary line (state and counters) that a run of the evaluation logs."""
    return [r for r in caplog.records if r.name == evaluacion.logger.name and "evaluation estado=" in r.getMessage()]


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
        if self._buenas <= 0:
            raise UpstashUnavailableError("caido")
        self._buenas -= 1
        return await super().read_strict(key)


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

    async def evaluar_inerte(redis, ahora):
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
