"""Daily counters of the push alerts in Upstash (FRA-360, T11, part 1): `services/alertas/metricas.py`.

One HASH per Argentine day, `alertas:metricas:{YYYY-MM-DD}`, with one field per counter (`HINCRBY`, atomic) and a 40-day
expiry set once (`EXPIRE ... NX`). Only the counters different from zero are written, so an SMN run without alerts costs
ONE counting command plus the expiry. Counting is a side effect: Upstash failing (or the module itself failing) only
logs a WARNING and never changes a response, a run, a send or a subscription. The router counts the forecast and SMN
runs, the new subscriptions (a renewal is not an alta) and the deletions asked for (an unknown id is not a baja); the
subscriptions deleted by the dispatch are already the `vencidos` counter of the run. Upstash is the fake of conftest.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from httpx import AsyncClient

from app.core.upstash import UpstashRedis, UpstashUnavailableError, configure_redis
from app.routers import alertas as router_alertas
from app.services.alertas import avisos_smn, evaluacion, metricas
from app.services.alertas import suscripcion as svc
from app.services.alertas.despacho import ResumenEnvio, ResumenSmn
from app.services.alertas.evaluacion import ResultadoEvaluacion, ResultadoEvaluacionSmn
from app.services.alertas.suscripcion import id_de_endpoint
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name; estado_de_alertas_limpio is autouse)
    AHORA,
    AR,
    CALMA,
    CLAVE_APAGADO,
    CUERPO,
    CUERPO_SMN,
    RedisConFalla,
    en_seco,
    envio_activo,
    estado_de_alertas_limpio,
    lineas_de_resumen,
    lineas_de_resumen_smn,
    llamar_evaluar,
    redis,
    registrar,
    reloj_de_openmeteo,
    respuestas_por_zona,
    suscribir,
)
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.test_alertas_avisos_smn import AMARILLO, avisos_por_zona, push  # noqa: F401  (`push` is a fixture)
from tests.test_alertas_suscripcion import AUTH, P256DH

pytestmark = pytest.mark.integration

UTC = timezone.utc
DIA = date(2026, 10, 14)
CLAVE_DIA = "alertas:metricas:2026-10-14"
CLAVE_DIA_SIGUIENTE = "alertas:metricas:2026-10-15"
TTL_40_DIAS = 40 * 24 * 60 * 60  # 3.456.000 s
EXPIRE_DIA = ["EXPIRE", CLAVE_DIA, str(TTL_40_DIAS), "NX"]
AHORA_SMN = datetime(2026, 10, 14, 13, 0, tzinfo=AR)  # the yellow alert of Córdoba is in force
AVISO = "alertas: metrics could not be recorded"
RUTA_ALTA = "/api/alertas/suscripcion"
RUTA_BAJA = "/api/alertas/baja"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-metricas-001"
# What the SMN run answers when it sends the alert in force to the two subscribers of Córdoba (pinned by FRA-359).
RESPUESTA_SMN_ENVIADA = {
    "estado": "evaluada", "smn_sin_datos": 0, "smn_avisos": 1, "smn_avisadas": 1, "smn_ya_avisadas": 0,
    "smn_omitidas": 0, "smn_errores": 0, "avisadas": 1, "ya_avisadas": 0, "enviados": 2, "vencidos": 0,
    "fallidos": 0, "diferidos": 0, "reintentadas": 0,
}
LINEA_SMN_ENVIADA = (
    "alertas: smn evaluation estado=evaluada smn_sin_datos=0 smn_avisos=1 smn_avisadas=1 smn_ya_avisadas=0 "
    "smn_omitidas=0 smn_errores=0 avisadas=1 ya_avisadas=0 enviados=2 vencidos=0 fallidos=0 diferidos=0 reintentadas=0"
)


def hincrbys(fake_upstash) -> list[list[str]]:
    return [c for c in fake_upstash.commands if c[0] == "HINCRBY"]


def de_metricas(fake_upstash) -> list[list[str]]:
    """Every command that touched a metrics key."""
    return [c for c in fake_upstash.commands if len(c) > 1 and c[1].startswith(metricas.PREFIJO)]


def avisos(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith(AVISO)]


def _cuerpo_alta(endpoint: str = ENDPOINT, zona: str = "cordoba") -> dict:
    return {"endpoint": endpoint, "keys": {"p256dh": P256DH, "auth": AUTH}, "zona": zona}


@pytest.fixture
def reloj_del_router(monkeypatch: pytest.MonkeyPatch):
    """The router's clock pinned at AHORA (10:30 in Argentina, the 10 h review), handed over in UTC like the real one."""
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA.astimezone(UTC))


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The SMN feed (the yellow alert of Córdoba) injected through the real plumbing, and the router's clock at 13 h."""
    estado = SimpleNamespace(obtener=avisos_por_zona({"cordoba": [AMARILLO]}))
    original = avisos_smn.evaluar_avisos_smn

    async def con_feed(redis_, ahora, **kwargs):
        return await original(redis_, ahora, obtener_avisos=estado.obtener, **kwargs)

    monkeypatch.setattr(avisos_smn, "evaluar_avisos_smn", con_feed)
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA_SMN.astimezone(UTC))
    return estado


# ---------------------------------------------------------------------------
# [S1, S2, S3] What a run writes: its state, and only the counters different from zero
# ---------------------------------------------------------------------------


async def test_a_dry_forecast_run_counts_its_state_and_nothing_else_in_the_hash_of_the_day(redis, fake_upstash) -> None:
    resultado = ResultadoEvaluacion(estado="evaluada", zonas_con_suscriptores=2, evaluadas=2, sin_tormenta=2)
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, resultado, AHORA)

    assert fake_upstash.hashes == {CLAVE_DIA: {"pronostico:corridas:evaluada": "1"}}
    assert fake_upstash.commands == [["HINCRBY", CLAVE_DIA, "pronostico:corridas:evaluada", "1"], EXPIRE_DIA]
    assert fake_upstash.ttls[CLAVE_DIA] == TTL_40_DIAS


async def test_a_forecast_run_that_sent_adds_the_sending_counters_that_are_not_zero(redis, fake_upstash) -> None:
    envio = ResumenEnvio(avisadas=1, enviados=3, fallidos=2)
    resultado = ResultadoEvaluacion(estado="evaluada", zonas_con_suscriptores=1, evaluadas=1, con_tormenta=1, envio=envio)
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, resultado, AHORA)

    assert fake_upstash.hashes[CLAVE_DIA] == {
        "pronostico:corridas:evaluada": "1",
        "pronostico:avisadas": "1",
        "pronostico:enviados": "3",
        "pronostico:fallidos": "2",
    }
    # Four counters, one EXPIRE: the zeros (`ya_avisadas`, `vencidos`, ...) are not written.
    assert [c[0] for c in fake_upstash.commands] == ["HINCRBY"] * 4 + ["EXPIRE"]


async def test_an_smn_run_without_alerts_costs_one_counting_command_plus_the_expiry(redis, fake_upstash) -> None:
    await metricas.contar_corrida(redis, metricas.TIPO_SMN, ResultadoEvaluacionSmn(estado="evaluada"), AHORA_SMN)

    assert fake_upstash.commands == [["HINCRBY", CLAVE_DIA, "smn:corridas:evaluada", "1"], EXPIRE_DIA]
    assert fake_upstash.hashes == {CLAVE_DIA: {"smn:corridas:evaluada": "1"}}


async def test_an_smn_run_with_an_alert_counts_the_smn_and_the_sending_counters(redis, fake_upstash) -> None:
    resultado = ResultadoEvaluacionSmn(
        estado="evaluada", smn=ResumenSmn(smn_avisos=1, smn_avisadas=1), envio=ResumenEnvio(avisadas=1, enviados=2)
    )
    await metricas.contar_corrida(redis, metricas.TIPO_SMN, resultado, AHORA_SMN)

    assert fake_upstash.hashes[CLAVE_DIA] == {
        "smn:corridas:evaluada": "1",
        "smn:smn_avisos": "1",
        "smn:smn_avisadas": "1",
        "smn:avisadas": "1",
        "smn:enviados": "2",
    }
    assert [c[0] for c in fake_upstash.commands] == ["HINCRBY"] * 5 + ["EXPIRE"]


@pytest.mark.parametrize("estado", ["en_curso", "fuera_de_ventana", "upstash_no_disponible", "sin_vapid"])
async def test_a_run_that_never_reached_the_zones_counts_its_state_only(redis, fake_upstash, estado: str) -> None:
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, ResultadoEvaluacion(estado=estado), AHORA)
    await metricas.contar_corrida(redis, metricas.TIPO_SMN, ResultadoEvaluacionSmn(estado=estado), AHORA)

    assert fake_upstash.hashes[CLAVE_DIA] == {f"pronostico:corridas:{estado}": "1", f"smn:corridas:{estado}": "1"}


async def test_a_cut_run_counts_its_state_and_what_it_sent_before_the_cut(redis, fake_upstash) -> None:
    envio = ResumenEnvio(avisadas=1, enviados=4, diferidos=6)
    resultado = ResultadoEvaluacion(estado="apagado_a_mitad", evaluadas=2, con_tormenta=2, envio=envio)
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, resultado, AHORA)

    assert fake_upstash.hashes[CLAVE_DIA] == {
        "pronostico:corridas:apagado_a_mitad": "1",
        "pronostico:avisadas": "1",
        "pronostico:enviados": "4",
        "pronostico:diferidos": "6",
    }


async def test_the_forecast_zone_counters_that_are_not_zero_are_counted_too(redis, fake_upstash) -> None:
    """`sin_datos`, `errores` and `diferidas` are the signal of the 429s of Open-Meteo: they are persisted when not zero."""
    resultado = ResultadoEvaluacion(estado="evaluada_incompleta", zonas_con_suscriptores=6, evaluadas=3, sin_datos=2, errores=1, diferidas=3)
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, resultado, AHORA)

    assert fake_upstash.hashes[CLAVE_DIA] == {
        "pronostico:corridas:evaluada_incompleta": "1",
        "pronostico:sin_datos": "2",
        "pronostico:errores": "1",
        "pronostico:diferidas": "3",
    }
    assert [c[0] for c in fake_upstash.commands] == ["HINCRBY"] * 4 + ["EXPIRE"]


async def test_the_other_zone_counters_of_the_forecast_run_are_still_not_persisted(redis, fake_upstash) -> None:
    resultado = ResultadoEvaluacion(
        estado="evaluada", zonas_con_suscriptores=5, evaluadas=4, con_tormenta=1, sin_tormenta=3, desconocidas=2
    )
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, resultado, AHORA)

    assert fake_upstash.hashes == {CLAVE_DIA: {"pronostico:corridas:evaluada": "1"}}


@pytest.mark.parametrize("estado", ["x:y\nz", "listo", "", "Evaluada", "evaluada\n", "evaluada:extra", "a" * 200])
async def test_a_state_outside_the_closed_list_is_counted_under_a_fixed_field(redis, fake_upstash, estado: str) -> None:
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, ResultadoEvaluacion(estado=estado), AHORA)
    await metricas.contar_corrida(redis, metricas.TIPO_SMN, ResultadoEvaluacionSmn(estado=estado), AHORA)

    assert fake_upstash.hashes == {CLAVE_DIA: {"pronostico:corridas:desconocido": "1", "smn:corridas:desconocido": "1"}}


def test_the_closed_list_of_states_is_exactly_the_states_a_run_can_end_in() -> None:
    assert metricas.ESTADOS_CONOCIDOS == frozenset({
        "evaluada", "evaluada_incompleta", "apagado_a_mitad", "en_curso", "fuera_de_ventana", "sin_vapid",
        "upstash_no_disponible",
    })  # `apagado` is answered by the router and is not a run: it is not counted


@pytest.mark.parametrize("valor", [True, False])
async def test_a_bool_is_never_a_counter(redis, fake_upstash, valor: bool) -> None:
    envio = ResumenEnvio(avisadas=valor, enviados=2)
    resultado = ResultadoEvaluacion(estado="evaluada", sin_datos=valor, envio=envio)
    assert metricas.incrementos_de_corrida(metricas.TIPO_PRONOSTICO, resultado) == {
        "pronostico:corridas:evaluada": 1, "pronostico:enviados": 2,
    }
    await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, resultado, AHORA)

    assert fake_upstash.hashes == {CLAVE_DIA: {"pronostico:corridas:evaluada": "1", "pronostico:enviados": "2"}}
    assert not any("True" in " ".join(c) or "False" in " ".join(c) for c in fake_upstash.commands)


async def test_runs_of_the_same_day_add_up_field_by_field(redis, fake_upstash) -> None:
    for _ in range(3):
        await metricas.contar_corrida(redis, metricas.TIPO_SMN, ResultadoEvaluacionSmn(estado="evaluada"), AHORA_SMN)
    await metricas.contar_corrida(redis, metricas.TIPO_SMN, ResultadoEvaluacionSmn(estado="en_curso"), AHORA_SMN)
    await metricas.contar_corrida(
        redis, metricas.TIPO_SMN, ResultadoEvaluacionSmn(estado="evaluada", smn=ResumenSmn(smn_avisos=2)), AHORA_SMN
    )

    assert fake_upstash.hashes[CLAVE_DIA] == {"smn:corridas:evaluada": "4", "smn:corridas:en_curso": "1", "smn:smn_avisos": "2"}


async def test_altas_and_bajas_are_counted_under_their_own_fields(redis, fake_upstash) -> None:
    await metricas.contar_alta(redis, AHORA)
    await metricas.contar_alta(redis, AHORA)
    await metricas.contar_baja(redis, AHORA)

    assert fake_upstash.hashes[CLAVE_DIA] == {"suscripciones:altas": "2", "suscripciones:bajas": "1"}
    assert fake_upstash.commands[:2] == [["HINCRBY", CLAVE_DIA, "suscripciones:altas", "1"], EXPIRE_DIA]


# ---------------------------------------------------------------------------
# [S5] The day is the Argentine day (-03:00), whatever the time zone of `ahora`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ahora", "clave"),
    [
        (datetime(2026, 10, 15, 2, 59, 59, tzinfo=UTC), CLAVE_DIA),  # 23:59:59 of the 14th in Argentina
        (datetime(2026, 10, 15, 3, 0, 0, tzinfo=UTC), CLAVE_DIA_SIGUIENTE),  # 00:00:00 of the 15th
        (datetime(2026, 10, 14, 23, 59, 59, tzinfo=AR), CLAVE_DIA),
        (datetime(2026, 10, 15, 0, 0, 0, tzinfo=AR), CLAVE_DIA_SIGUIENTE),
        (datetime(2026, 10, 14, 23, 30, tzinfo=timezone(timedelta(hours=-5))), CLAVE_DIA_SIGUIENTE),  # 01:30 AR
    ],
    ids=["23:59:59-ar-in-utc", "00:00:00-ar-in-utc", "23:59:59-ar", "00:00:00-ar", "other-offset"],
)
async def test_the_counter_goes_to_the_argentine_day_of_the_moment(redis, fake_upstash, ahora: datetime, clave: str) -> None:
    await metricas.contar_alta(redis, ahora)
    assert list(fake_upstash.hashes) == [clave]
    assert metricas.clave_del_dia(metricas.dia_de(ahora)) == clave


async def test_a_naive_moment_is_refused_and_nothing_is_counted(redis, fake_upstash, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    with pytest.raises(ValueError):
        metricas.dia_de(datetime(2026, 10, 14, 10, 30))
    await metricas.contar_alta(redis, datetime(2026, 10, 14, 10, 30))  # the side effect swallows it, with a WARNING
    assert fake_upstash.commands == [] and [r.levelno for r in avisos(caplog)] == [logging.WARNING]


# ---------------------------------------------------------------------------
# [S3] Expiry: 40 days, set once, never stretched; and the fields are atomic increments (two runs at once add up)
# ---------------------------------------------------------------------------


async def test_the_expiry_is_set_once_and_a_later_count_does_not_stretch_it(redis, fake_upstash) -> None:
    await metricas.contar_alta(redis, AHORA)
    assert fake_upstash.ttls[CLAVE_DIA] == TTL_40_DIAS == metricas.RETENCION_SEGUNDOS
    fake_upstash.ttls[CLAVE_DIA] = 100  # time passed
    await metricas.contar_baja(redis, AHORA)
    assert fake_upstash.ttls[CLAVE_DIA] == 100  # EXPIRE ... NX: the key already had one
    assert [c for c in fake_upstash.commands if c[0] == "EXPIRE"] == [EXPIRE_DIA, EXPIRE_DIA]


async def test_a_cut_between_hincrby_and_expire_is_repaired_by_the_next_write_and_never_stretched(redis, fake_upstash) -> None:
    original, estado = fake_upstash._run, {"fallar": True}

    def run(name, args):
        if name == "EXPIRE" and args[0].startswith(metricas.PREFIJO) and estado["fallar"]:
            estado["fallar"] = False
            raise httpx.ReadTimeout("corte")
        return original(name, args)

    fake_upstash._run = run
    await metricas.contar_alta(redis, AHORA)
    assert CLAVE_DIA not in fake_upstash.ttls  # the cut left the key without expiry...
    await metricas.contar_baja(redis, AHORA)
    assert fake_upstash.ttls[CLAVE_DIA] == TTL_40_DIAS  # ...and the next write of the day repairs it
    fake_upstash.ttls[CLAVE_DIA] = 100
    await metricas.contar_alta(redis, AHORA)
    assert fake_upstash.ttls[CLAVE_DIA] == 100  # and it is never stretched afterwards


async def test_the_expiry_is_asked_after_the_first_increment_so_the_key_exists(redis, fake_upstash) -> None:
    await metricas.contar_corrida(redis, metricas.TIPO_SMN, ResultadoEvaluacionSmn(estado="evaluada"), AHORA_SMN)
    assert [c[0] for c in fake_upstash.commands] == ["HINCRBY", "EXPIRE"]
    assert fake_upstash.ttls[CLAVE_DIA] == TTL_40_DIAS  # an EXPIRE before the key exists would have set nothing


async def test_a_forecast_run_and_an_smn_run_counted_at_the_same_time_both_add_up(redis, fake_upstash) -> None:
    pronostico = ResultadoEvaluacion(estado="evaluada", envio=ResumenEnvio(avisadas=1, enviados=5))
    smn = ResultadoEvaluacionSmn(estado="evaluada", smn=ResumenSmn(smn_avisos=1), envio=ResumenEnvio(avisadas=1, enviados=2))
    await asyncio.gather(
        metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, pronostico, AHORA),
        metricas.contar_corrida(redis, metricas.TIPO_SMN, smn, AHORA),
        metricas.contar_alta(redis, AHORA),
        metricas.contar_alta(redis, AHORA),
    )
    assert fake_upstash.hashes[CLAVE_DIA] == {
        "pronostico:corridas:evaluada": "1",
        "pronostico:avisadas": "1",
        "pronostico:enviados": "5",
        "smn:corridas:evaluada": "1",
        "smn:smn_avisos": "1",
        "smn:avisadas": "1",
        "smn:enviados": "2",
        "suscripciones:altas": "2",
    }
    assert fake_upstash.ttls[CLAVE_DIA] == TTL_40_DIAS


# ---------------------------------------------------------------------------
# [S4] Counting is a side effect: Upstash failing, or the module failing, only warns
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("falla", ["HINCRBY", "EXPIRE"])
async def test_upstash_failing_to_count_only_logs_a_warning_without_data(fake_upstash, caplog, falla: str) -> None:
    caplog.set_level(logging.DEBUG)
    redis_roto = RedisConFalla(falla)
    resultado = ResultadoEvaluacionSmn(estado="evaluada", smn=ResumenSmn(smn_avisos=1))

    assert await metricas.contar_corrida(redis_roto, metricas.TIPO_SMN, resultado, AHORA_SMN) is None
    assert await metricas.contar_alta(redis_roto, AHORA) is None
    assert await metricas.contar_baja(redis_roto, AHORA) is None

    registros = avisos(caplog)
    assert [r.levelno for r in registros] == [logging.WARNING] * 3
    assert all("exc_type=UpstashUnavailableError" in r.getMessage() for r in registros)
    assert not any(CLAVE_DIA in r.getMessage() or "smn_avisos" in r.getMessage() for r in registros)
    if falla == "HINCRBY":  # the first increment failed: nothing else is tried (no 5 s per field on a dead Upstash)
        assert fake_upstash.commands == []


async def test_an_exception_inside_the_module_does_not_propagate(redis, fake_upstash, caplog, monkeypatch) -> None:
    caplog.set_level(logging.DEBUG)

    def roto(tipo, resultado):
        raise RuntimeError("a bug in the metrics")

    monkeypatch.setattr(metricas, "incrementos_de_corrida", roto)
    resultado = ResultadoEvaluacion(estado="evaluada")
    assert await metricas.contar_corrida(redis, metricas.TIPO_PRONOSTICO, resultado, AHORA) is None
    assert fake_upstash.commands == []
    assert [r.getMessage() for r in avisos(caplog)] == [f"{AVISO} exc_type=RuntimeError"]


async def test_a_cancellation_is_not_swallowed(redis, fake_upstash, monkeypatch) -> None:
    async def cancelado(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(redis, "hincrby", cancelado)
    with pytest.raises(asyncio.CancelledError):
        await metricas.contar_alta(redis, AHORA)


# ---------------------------------------------------------------------------
# [S6] Reading for the panel: one day, or a range of days, tolerant of days without data
# ---------------------------------------------------------------------------


async def test_reading_a_day_returns_its_counters_as_integers(redis, fake_upstash) -> None:
    resultado = ResultadoEvaluacionSmn(estado="evaluada", smn=ResumenSmn(smn_avisos=1), envio=ResumenEnvio(avisadas=1, enviados=2))
    await metricas.contar_corrida(redis, metricas.TIPO_SMN, resultado, AHORA_SMN)
    await metricas.contar_alta(redis, AHORA)
    fake_upstash.commands.clear()

    assert await metricas.leer_dia(redis, DIA) == {
        "smn:corridas:evaluada": 1,
        "smn:smn_avisos": 1,
        "smn:avisadas": 1,
        "smn:enviados": 2,
        "suscripciones:altas": 1,
    }
    assert fake_upstash.commands == [["HGETALL", CLAVE_DIA]]  # one command per day read


async def test_reading_a_day_without_data_is_an_empty_dict(redis, fake_upstash) -> None:
    assert await metricas.leer_dia(redis, date(2026, 1, 1)) == {}


async def test_reading_a_range_returns_every_day_in_order_including_the_empty_ones(redis, fake_upstash) -> None:
    await metricas.contar_alta(redis, datetime(2026, 10, 12, 12, 0, tzinfo=AR))
    await metricas.contar_baja(redis, datetime(2026, 10, 14, 12, 0, tzinfo=AR))
    await metricas.contar_baja(redis, datetime(2026, 10, 14, 18, 0, tzinfo=AR))
    fake_upstash.commands.clear()

    rango = await metricas.leer_rango(redis, date(2026, 10, 12), date(2026, 10, 15))
    assert rango == {
        "2026-10-12": {"suscripciones:altas": 1},
        "2026-10-13": {},
        "2026-10-14": {"suscripciones:bajas": 2},
        "2026-10-15": {},
    }
    assert list(rango) == ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15"]
    assert sorted(c[1] for c in fake_upstash.commands) == sorted(f"alertas:metricas:2026-10-{d}" for d in (12, 13, 14, 15))
    assert await metricas.leer_rango(redis, DIA, DIA) == {"2026-10-14": {"suscripciones:bajas": 2}}


async def test_reading_a_range_refuses_an_inverted_or_too_long_range_before_touching_upstash(redis, fake_upstash) -> None:
    with pytest.raises(ValueError):
        await metricas.leer_rango(redis, date(2026, 10, 15), date(2026, 10, 14))
    with pytest.raises(ValueError):
        await metricas.leer_rango(redis, date(2026, 9, 1), date(2026, 9, 1) + timedelta(days=metricas.RETENCION_DIAS))
    assert fake_upstash.commands == []
    assert len(await metricas.leer_rango(redis, date(2026, 9, 1), date(2026, 9, 1) + timedelta(days=39))) == 40


async def test_reading_with_upstash_down_raises_unavailable(fake_upstash) -> None:
    with pytest.raises(UpstashUnavailableError):
        await metricas.leer_dia(RedisConFalla("HGETALL"), DIA)


async def test_a_value_that_is_not_a_number_is_skipped_with_a_warning(redis, fake_upstash, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    fake_upstash.hashes[CLAVE_DIA] = {"suscripciones:altas": "3", "suscripciones:bajas": "muchas"}
    assert await metricas.leer_dia(redis, DIA) == {"suscripciones:altas": 3}
    assert any("suscripciones:bajas" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


# ---------------------------------------------------------------------------
# [S7] Only numbers: no id, endpoint, zone or key ever reaches a metrics key, field or value
# ---------------------------------------------------------------------------


async def test_no_id_endpoint_or_key_reaches_the_metrics(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, own_caches, reloj_de_openmeteo,
) -> None:
    ids = await registrar(alertas_redis, "cordoba", 2)
    response = await llamar_evaluar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA

    comandos = de_metricas(fake_upstash)
    assert comandos  # the run was counted
    nombre_de_clave = re.compile(r"alertas:metricas:\d{4}-\d{2}-\d{2}")
    nombre_de_campo = re.compile(r"(pronostico|smn|suscripciones):[a-z_:]+")
    for comando in comandos:
        assert nombre_de_clave.fullmatch(comando[1]), comando
        if comando[0] == "HINCRBY":
            assert nombre_de_campo.fullmatch(comando[2]) and comando[3].isdigit(), comando
    texto = " ".join(" ".join(c) for c in comandos)
    assert "cordoba" not in texto and "SECRETO" not in texto
    assert not any(sub_id in texto for sub_id in ids)


# ---------------------------------------------------------------------------
# Through the router: the runs, with their exact cost in commands
# ---------------------------------------------------------------------------


async def test_a_dry_forecast_run_through_the_router_is_counted_on_the_argentine_day_after_the_run(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, install, own_caches, reloj_de_openmeteo, reloj_del_router,
) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200 and response.json()["estado"] == "evaluada"
    assert "pronostico" not in response.text  # the response keeps its shape: no metrics field
    assert fake_upstash.hashes == {CLAVE_DIA: {"pronostico:corridas:evaluada": "1"}}
    # The count comes LAST (after the run), and costs exactly one increment plus the expiry.
    assert fake_upstash.commands[-2:] == [["HINCRBY", CLAVE_DIA, "pronostico:corridas:evaluada", "1"], EXPIRE_DIA]
    assert fake_upstash.commands[0] == ["GET", CLAVE_APAGADO]


async def test_a_forecast_run_with_a_zone_without_data_and_one_that_failed_counts_both_through_the_router(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, install, own_caches, reloj_de_openmeteo, reloj_del_router,
) -> None:
    install(respond=respuestas_por_zona({"cordoba": None, "rosario": RuntimeError("bug"), "mendoza": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza")
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200 and response.json()["estado"] == "evaluada"
    assert (response.json()["sin_datos"], response.json()["errores"], response.json()["diferidas"]) == (1, 1, 0)
    assert fake_upstash.hashes == {
        CLAVE_DIA: {"pronostico:corridas:evaluada": "1", "pronostico:sin_datos": "1", "pronostico:errores": "1"}
    }  # `diferidas` is zero: not written


async def test_an_smn_run_through_the_router_counts_its_state_the_smn_and_the_sending_counters(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, own_caches, reloj_de_openmeteo,
) -> None:
    await registrar(alertas_redis, "cordoba", 2)
    fake_upstash.commands.clear()
    response = await llamar_evaluar(async_client, CUERPO_SMN)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert fake_upstash.hashes[CLAVE_DIA] == {
        "smn:corridas:evaluada": "1",
        "smn:smn_avisos": "1",
        "smn:smn_avisadas": "1",
        "smn:avisadas": "1",
        "smn:enviados": "2",
    }
    assert [c[0] for c in fake_upstash.commands[-6:]] == ["HINCRBY"] * 5 + ["EXPIRE"]


async def test_an_smn_run_without_alerts_through_the_router_costs_five_commands_in_all(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, own_caches, reloj_de_openmeteo,
) -> None:
    feed.obtener = avisos_por_zona({})
    suscribir(fake_upstash, "cordoba", cantidad=3)
    fake_upstash.commands.clear()
    response = await llamar_evaluar(async_client, CUERPO_SMN)

    assert response.status_code == 200 and response.json()["estado"] == "evaluada"
    # The 3 commands of FRA-359 (switch, lock, index) plus the ONE count and the expiry of S3.
    assert [c[0] for c in fake_upstash.commands] == ["GET", "SET", "SMEMBERS", "HINCRBY", "EXPIRE"]
    assert fake_upstash.hashes[CLAVE_DIA] == {"smn:corridas:evaluada": "1"}


async def test_an_smn_run_with_the_alert_already_sent_costs_five_counting_commands(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, own_caches, reloj_de_openmeteo,
) -> None:
    await registrar(alertas_redis, "cordoba", 2)
    await llamar_evaluar(async_client, CUERPO_SMN)
    fake_upstash.commands.clear()
    fake_upstash.strings.pop("alertas:lock:evaluar-smn")  # the lock is never released: a second run is a later one
    await llamar_evaluar(async_client, CUERPO_SMN)

    assert [c[2] for c in de_metricas(fake_upstash) if c[0] == "HINCRBY"] == [
        "smn:corridas:evaluada", "smn:smn_avisos", "smn:smn_ya_avisadas", "smn:ya_avisadas",
    ]
    assert len(de_metricas(fake_upstash)) == 5  # four increments plus the expiry


async def test_the_router_counts_on_the_day_the_run_started_even_if_it_ends_after_midnight(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, monkeypatch,
) -> None:
    lecturas = iter([datetime(2026, 10, 15, 2, 59, 59, tzinfo=UTC)])  # 23:59:59 of the 14th in Argentina
    monkeypatch.setattr(
        router_alertas, "_ahora_utc", lambda: next(lecturas, datetime(2026, 10, 15, 3, 0, 5, tzinfo=UTC))
    )

    async def corrida(redis_, ahora, **kw):
        kw["reloj"]()  # the run reads the clock again: it is already the 15th
        return ResultadoEvaluacionSmn(estado="evaluada", smn=ResumenSmn())

    monkeypatch.setattr(evaluacion, "evaluar_smn", corrida)
    await llamar_evaluar(async_client, CUERPO_SMN)

    assert {c[1] for c in de_metricas(fake_upstash)} == {CLAVE_DIA}


async def test_apagado_is_not_a_run_and_is_not_counted(async_client: AsyncClient, alertas_redis, fake_upstash) -> None:
    response = await llamar_evaluar(async_client)  # both flags off
    assert response.json() == {"estado": "apagado"} and fake_upstash.commands == []


async def test_en_curso_and_fuera_de_ventana_are_counted_as_runs_with_their_state(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, install, own_caches, reloj_de_openmeteo, monkeypatch,
) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: datetime(2026, 10, 14, 22, 30, tzinfo=AR).astimezone(UTC))
    assert (await llamar_evaluar(async_client)).json() == {"estado": "fuera_de_ventana"}
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA.astimezone(UTC))
    fake_upstash.strings["alertas:lock:evaluar"] = "otra-corrida"
    assert (await llamar_evaluar(async_client)).json() == {"estado": "en_curso"}

    assert fake_upstash.hashes == {
        CLAVE_DIA: {"pronostico:corridas:fuera_de_ventana": "1", "pronostico:corridas:en_curso": "1"}
    }


async def test_upstash_failing_to_count_changes_nothing_of_the_run_the_sends_or_the_log_line(
    async_client: AsyncClient, fake_upstash, envio_activo, push, feed, own_caches, reloj_de_openmeteo, caplog,
) -> None:
    """The fake fails ONLY on the metrics commands: the run, its sends, its answer and its line are exactly as before."""
    caplog.set_level(logging.DEBUG)
    redis_roto = RedisConFalla("HINCRBY")
    configure_redis(redis_roto)
    ids = await registrar(redis_roto, "cordoba", 2)
    response = await llamar_evaluar(async_client, CUERPO_SMN)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert [(r.levelno, r.getMessage()) for r in lineas_de_resumen_smn(caplog)] == [(logging.INFO, LINEA_SMN_ENVIADA)]
    assert fake_upstash.hashes == {} and de_metricas(fake_upstash) == []
    assert [r.getMessage() for r in avisos(caplog)] == [f"{AVISO} exc_type=UpstashUnavailableError"]


@pytest.mark.parametrize("falla", ["timeout", "connect", "error400", "nonint"])
async def test_a_transport_failure_only_on_the_metrics_keys_changes_nothing_of_the_smn_run(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, own_caches, reloj_de_openmeteo,
    caplog, falla: str,
) -> None:
    """Whatever the way Upstash fails on the metrics keys (and ONLY on them), the run, its sends, its answer and its line
    are exactly as without the counters."""
    caplog.set_level(logging.DEBUG)
    await registrar(alertas_redis, "cordoba", 2)
    original = fake_upstash._run

    def run(name, args):
        if args and str(args[0]).startswith(metricas.PREFIJO):
            if falla == "timeout":
                raise httpx.ReadTimeout("lento")
            if falla == "connect":
                raise httpx.ConnectError("caido")
            if falla == "error400":
                raise httpx.HTTPStatusError(
                    "400", request=httpx.Request("POST", "https://fake-upstash.io/"),
                    response=httpx.Response(400, json={"error": "WRONGTYPE"}),
                )
            return "no-es-entero"
        return original(name, args)

    fake_upstash._run = run
    response = await llamar_evaluar(async_client, CUERPO_SMN)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert len(push.llamadas) == 2 and fake_upstash.hashes == {}
    assert [(r.levelno, r.getMessage()) for r in lineas_de_resumen_smn(caplog)] == [(logging.INFO, LINEA_SMN_ENVIADA)]


async def test_a_forecast_run_that_sends_through_the_router_with_upstash_failing_to_count_answers_as_before(
    async_client: AsyncClient, fake_upstash, envio_activo, push, install, own_caches, reloj_de_openmeteo, reloj_del_router,
    caplog,
) -> None:
    caplog.set_level(logging.DEBUG)
    from tests.alertas_helpers import TORMENTA

    install(TORMENTA)
    redis_roto = RedisConFalla("HINCRBY")
    configure_redis(redis_roto)
    ids = await registrar(redis_roto, "cordoba", 2)
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200
    assert response.json()["estado"] == "evaluada" and response.json()["enviados"] == 2
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert len(lineas_de_resumen(caplog)) == 1 and de_metricas(fake_upstash) == []
    assert len(avisos(caplog)) == 1


# ---------------------------------------------------------------------------
# Through the router: altas and bajas
# ---------------------------------------------------------------------------


async def test_a_new_subscription_counts_an_alta_and_a_renewal_or_a_change_of_zone_does_not(
    async_client: AsyncClient, alertas_redis, fake_upstash, reloj_del_router,
) -> None:
    primera = await async_client.post(RUTA_ALTA, json=_cuerpo_alta())
    assert primera.status_code == 201 and primera.json() == {"id": id_de_endpoint(ENDPOINT), "zona": "cordoba"}
    assert fake_upstash.hashes == {CLAVE_DIA: {"suscripciones:altas": "1"}}
    assert fake_upstash.commands[-2:] == [["HINCRBY", CLAVE_DIA, "suscripciones:altas", "1"], EXPIRE_DIA]

    fake_upstash.commands.clear()
    renovada = await async_client.post(RUTA_ALTA, json=_cuerpo_alta())
    cambiada = await async_client.post(RUTA_ALTA, json=_cuerpo_alta(zona="rosario"))
    assert renovada.status_code == cambiada.status_code == 201 and cambiada.json()["zona"] == "rosario"
    assert de_metricas(fake_upstash) == []  # a renewal costs nothing
    assert fake_upstash.hashes == {CLAVE_DIA: {"suscripciones:altas": "1"}}


async def test_a_baja_counts_once_and_an_unknown_id_answers_204_without_counting(
    async_client: AsyncClient, alertas_redis, fake_upstash, reloj_del_router,
) -> None:
    sub_id = (await async_client.post(RUTA_ALTA, json=_cuerpo_alta())).json()["id"]
    fake_upstash.commands.clear()

    assert (await async_client.post(RUTA_BAJA, json={"id": sub_id})).status_code == 204
    assert fake_upstash.hashes[CLAVE_DIA] == {"suscripciones:altas": "1", "suscripciones:bajas": "1"}
    assert fake_upstash.commands[-2:] == [["HINCRBY", CLAVE_DIA, "suscripciones:bajas", "1"], EXPIRE_DIA]

    fake_upstash.commands.clear()
    assert (await async_client.post(RUTA_BAJA, json={"id": sub_id})).status_code == 204  # idempotent, as always
    assert (await async_client.post(RUTA_BAJA, json={"id": "A" * 22})).status_code == 204
    assert de_metricas(fake_upstash) == []
    assert fake_upstash.hashes[CLAVE_DIA]["suscripciones:bajas"] == "1"


async def test_the_subscription_endpoints_answer_as_before_when_counting_fails(
    async_client: AsyncClient, fake_upstash, reloj_del_router, caplog,
) -> None:
    caplog.set_level(logging.DEBUG)
    configure_redis(RedisConFalla("HINCRBY"))
    alta = await async_client.post(RUTA_ALTA, json=_cuerpo_alta())
    assert alta.status_code == 201 and alta.json() == {"id": id_de_endpoint(ENDPOINT), "zona": "cordoba"}
    assert fake_upstash.sets["alertas:ids"] == {alta.json()["id"]}  # the subscription was saved
    baja = await async_client.post(RUTA_BAJA, json={"id": alta.json()["id"]})
    assert baja.status_code == 204 and fake_upstash.sets["alertas:ids"] == set()  # and deleted
    assert fake_upstash.hashes == {} and len(avisos(caplog)) == 2


async def test_a_rejected_alta_or_baja_counts_nothing(async_client: AsyncClient, alertas_redis, fake_upstash) -> None:
    assert (await async_client.post(RUTA_ALTA, json=_cuerpo_alta(endpoint="https://evil.com/x"))).status_code == 422
    assert (await async_client.post(RUTA_BAJA, json={"id": "corto"})).status_code == 422
    assert fake_upstash.commands == []


# ---------------------------------------------------------------------------
# The new service functions keep the old ones' behavior (S8)
# ---------------------------------------------------------------------------


async def test_alta_detallada_says_whether_the_subscription_is_new_and_alta_still_answers_the_id(redis, fake_upstash) -> None:
    suscripcion = svc.Suscripcion(ENDPOINT, P256DH, AUTH, "cordoba")
    primera = await svc.alta_detallada(redis, suscripcion)
    assert primera == svc.ResultadoAlta(sub_id=id_de_endpoint(ENDPOINT), nueva=True)
    segunda = await svc.alta_detallada(redis, svc.Suscripcion(ENDPOINT, P256DH, AUTH, "rosario"))
    assert segunda == svc.ResultadoAlta(sub_id=primera.sub_id, nueva=False)
    assert fake_upstash.sets["alertas:zona:rosario"] == {primera.sub_id} and primera.sub_id not in fake_upstash.sets["alertas:zona:cordoba"]
    assert await svc.alta(redis, suscripcion) == primera.sub_id  # the public `alta` is unchanged
    assert not any(c[0] == "HINCRBY" for c in fake_upstash.commands)  # the service itself never counts


async def test_baja_detallada_says_whether_something_was_deleted_and_baja_stays_idempotent(redis, fake_upstash) -> None:
    sub_id = await svc.alta(redis, svc.Suscripcion(ENDPOINT, P256DH, AUTH, "cordoba"))
    assert await svc.baja_detallada(redis, sub_id) is True
    assert await svc.baja_detallada(redis, sub_id) is False
    assert fake_upstash.sets["alertas:ids"] == set() and fake_upstash.sets["alertas:zona:cordoba"] == set()
    assert await svc.baja(redis, sub_id) is None
    with pytest.raises(svc.SuscripcionInvalida):
        await svc.baja_detallada(redis, "corto")
