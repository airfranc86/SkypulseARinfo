"""Sentry alerts about the push-alert runs (FRA-360, T11, part 2): `services/alertas/avisos_sentry.py`.

Three kinds of event, each at most once every 6 hours: a failed run (`alertas_corrida`), failed sends above 20 %
(`alertas_envios`) and a rejected-but-well-formed signature (`alertas_firma`). The rules are pure; the emission is a side
effect that never changes a response, a run, a send or the counters, and it costs 0 commands when everything is healthy.
The limit is a process memory (monotonic clock) plus `SET alertas:sentry:{tipo} 1 NX EX 21600`; if Upstash cannot store the
mark the alert goes out anyway. Sentry is a spy (`sentry_espia`: the `(message, kwargs)` of every `capture_message`);
Upstash is the fake of conftest.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core.upstash import UpstashRedis, UpstashUnavailableError, configure_redis
from app.routers import alertas as router_alertas
from app.services.alertas import avisos_sentry, avisos_smn, envio, evaluacion, firma_qstash, metricas
from app.services.alertas.avisos_sentry import Aviso
from app.services.alertas.despacho import ResumenEnvio, ResumenSmn
from app.services.alertas.evaluacion import ResultadoEvaluacion, ResultadoEvaluacionSmn
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name; estado_de_alertas_limpio is autouse)
    AHORA,
    AR,
    CALMA,
    CLAVE_LOCK_SMN,
    CUERPO,
    CUERPO_SMN,
    NO_AUTORIZADO,
    RedisConFalla,
    RedisSinSet,
    conteo_del_dia,
    en_seco,
    endpoint_de,
    envio_activo,
    esperas,
    estado_de_alertas_limpio,
    lineas_de_resumen_smn,
    llamar_evaluar,
    marca_de_sentry,
    redis,
    registrar,
    reloj_de_openmeteo,
    respuestas_por_zona,
    sentry_espia,
    suscribir,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.qstash_helpers import CLAVE_AJENA, firmar
from tests.test_alertas_avisos_smn import AMARILLO, avisos_por_zona, push  # noqa: F401  (`push` is a fixture)

pytestmark = pytest.mark.integration

UTC = timezone.utc
AHORA_SMN = datetime(2026, 10, 14, 13, 0, tzinfo=AR)  # the yellow alert of Córdoba is in force
CLAVE_CORRIDA = "alertas:sentry:corrida"
CLAVE_ENVIOS = "alertas:sentry:envios"
CLAVE_FIRMA = "alertas:sentry:firma"
SEIS_HORAS = 21_600
LOG_MARCA = "alertas: sentry mark could not be stored"
LOG_EMISION = "alertas: sentry alert could not be emitted"
# What the SMN run answers when it sends to the two subscribers of Córdoba and the push service fails for both.
RESPUESTA_SMN_ENVIOS_FALLIDOS = {
    "estado": "evaluada", "smn_sin_datos": 0, "smn_avisos": 1, "smn_avisadas": 0, "smn_ya_avisadas": 0,
    "smn_omitidas": 0, "smn_errores": 0, "avisadas": 0, "ya_avisadas": 0, "enviados": 0, "vencidos": 0,
    "fallidos": 2, "diferidos": 0, "reintentadas": 0,
}
LINEA_SMN_ENVIOS_FALLIDOS = (
    "alertas: smn evaluation estado=evaluada smn_sin_datos=0 smn_avisos=1 smn_avisadas=0 smn_ya_avisadas=0 "
    "smn_omitidas=0 smn_errores=0 avisadas=0 ya_avisadas=0 enviados=0 vencidos=0 fallidos=2 diferidos=0 reintentadas=0"
)
KWARGS_ENVIOS_FALLIDOS = {
    "level": "error",
    "tags": {"alert_kind": "alertas_envios", "corrida": "smn", "estado": "evaluada"},
    "extras": {"enviados": 0, "fallidos": 2, "vencidos": 0, "diferidos": 0, "intentos": 2, "porcentaje": 100},
    "fingerprint": ["alertas-envios"],
}


@pytest.fixture(autouse=True)
def _entorno(estado_de_alertas_limpio, own_caches, reloj_de_openmeteo, esperas):  # noqa: F811
    """A clean alerts state FIRST (both flags off, the 6-hour memory empty), fresh caches and no real waiting."""
    return own_caches


@pytest.fixture
def reloj_de_avisos(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The monotonic clock of the 6-hour limit, driven by the test (it starts well after zero)."""
    reloj = SimpleNamespace(segundos=1_000.0)
    reloj.avanzar = lambda segundos: setattr(reloj, "segundos", reloj.segundos + segundos)  # type: ignore[attr-defined]
    monkeypatch.setattr(avisos_sentry, "_monotonico", lambda: reloj.segundos)
    return reloj


@pytest.fixture
def reloj_del_router(monkeypatch: pytest.MonkeyPatch) -> None:
    """The router's clock pinned at AHORA (10:30 in Argentina, the 10 h review), handed over in UTC like the real one."""
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA.astimezone(UTC))


@pytest.fixture
def reloj_smn(monkeypatch: pytest.MonkeyPatch) -> None:
    """The router's clock pinned at 13:00 in Argentina (the yellow alert of Córdoba is in force)."""
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA_SMN.astimezone(UTC))


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The SMN feed (the yellow alert of Córdoba by default) injected through the real plumbing."""
    estado = SimpleNamespace(obtener=avisos_por_zona({"cordoba": [AMARILLO]}))
    original = avisos_smn.evaluar_avisos_smn

    async def con_feed(redis_, ahora, **kwargs):
        return await original(redis_, ahora, obtener_avisos=estado.obtener, **kwargs)

    monkeypatch.setattr(avisos_smn, "evaluar_avisos_smn", con_feed)
    return estado


def pronostico(estado: str, **campos: object) -> ResultadoEvaluacion:
    return ResultadoEvaluacion(estado=estado, **campos)  # type: ignore[arg-type]


def smn(estado: str, resumen: ResumenSmn = ResumenSmn(), envio_: ResumenEnvio | None = None) -> ResultadoEvaluacionSmn:
    return ResultadoEvaluacionSmn(estado=estado, smn=resumen, envio=envio_)


def set_de(clave: str) -> list[str]:
    return marca_de_sentry(clave.removeprefix(f"{avisos_sentry.PREFIJO}:"))


def de_sentry(fake_upstash) -> list[list[str]]:
    """Every command that touched a Sentry-limit key."""
    return [c for c in fake_upstash.commands if len(c) > 1 and c[1].startswith(avisos_sentry.PREFIJO)]


def avisos_del_log(caplog: pytest.LogCaptureFixture, texto: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == avisos_sentry.logger.name and r.getMessage().startswith(texto)]


def kwargs_de(nivel: str, tags: dict[str, str], extras: dict[str, int], fingerprint: list[str]) -> dict:
    return {"level": nivel, "tags": tags, "extras": extras, "fingerprint": fingerprint}


# ---------------------------------------------------------------------------
# [S3, S4] The rule of the failed run: which states are failures and which are not
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("resultado", "motivo", "nivel"),
    [
        (pronostico("upstash_no_disponible"), "upstash_no_disponible", "error"),
        (pronostico("sin_vapid"), "sin_vapid", "error"),
        (pronostico("evaluada_incompleta"), "evaluada_incompleta", "warning"),
        (pronostico("evaluada", evaluadas=3, sin_datos=3), "sin_datos_total", "warning"),
        (pronostico("evaluada", evaluadas=1, sin_datos=1), "sin_datos_total", "warning"),
        # The deadline wins over "every zone without data": one reason per event, in the order of the rule.
        (pronostico("evaluada_incompleta", evaluadas=3, sin_datos=3), "evaluada_incompleta", "warning"),
    ],
)
def test_a_forecast_run_that_failed_is_an_alert_with_its_reason_and_level(resultado, motivo, nivel) -> None:
    aviso = avisos_sentry.aviso_de_corrida(metricas.TIPO_PRONOSTICO, resultado)
    assert aviso is not None
    assert (aviso.tipo, aviso.nivel, aviso.mensaje) == ("corrida", nivel, f"alertas: corrida fallida ({motivo})")
    assert aviso.tags == {
        "alert_kind": "alertas_corrida", "corrida": "pronostico", "estado": resultado.estado, "motivo": motivo,
    }
    assert aviso.fingerprint == ("alertas-corrida", motivo)


@pytest.mark.parametrize(
    "resultado",
    [
        pronostico("evaluada", evaluadas=3, sin_datos=2),  # a partial `sin_datos` is the usual Open-Meteo 429
        pronostico("evaluada", evaluadas=0, sin_datos=0),
        pronostico("evaluada", evaluadas=4, sin_tormenta=4),
        pronostico("evaluada", evaluadas=2, con_tormenta=1, errores=1),  # `errores` reach the log, not an alert
        pronostico("evaluada"),
        pronostico("en_curso"),  # the lock protects the run: not a failure
        pronostico("fuera_de_ventana"),
        pronostico("apagado_a_mitad", evaluadas=3, sin_datos=3),  # the operator stopped it
        pronostico("listo"),  # a state outside the closed list
        pronostico(""),
    ],
)
def test_a_forecast_run_that_did_its_job_or_was_stopped_on_purpose_is_not_an_alert(resultado) -> None:
    assert avisos_sentry.aviso_de_corrida(metricas.TIPO_PRONOSTICO, resultado) is None


def test_the_alert_of_a_failed_forecast_run_carries_the_zone_counters_as_whole_numbers() -> None:
    resultado = pronostico("evaluada_incompleta", evaluadas=3, sin_datos=1, errores=1, diferidas=2, con_tormenta=1)
    assert avisos_sentry.aviso_de_corrida(metricas.TIPO_PRONOSTICO, resultado) == Aviso(
        tipo="corrida",
        nivel="warning",
        mensaje="alertas: corrida fallida (evaluada_incompleta)",
        tags={
            "alert_kind": "alertas_corrida", "corrida": "pronostico", "estado": "evaluada_incompleta",
            "motivo": "evaluada_incompleta",
        },
        extras={"evaluadas": 3, "sin_datos": 1, "errores": 1, "diferidas": 2},
        fingerprint=("alertas-corrida", "evaluada_incompleta"),
    )


def test_an_smn_run_that_could_not_verify_the_feed_is_a_warning_with_the_smn_counters() -> None:
    resultado = smn("evaluada", ResumenSmn(smn_sin_datos=1, smn_errores=0))
    assert avisos_sentry.aviso_de_corrida(metricas.TIPO_SMN, resultado) == Aviso(
        tipo="corrida",
        nivel="warning",
        mensaje="alertas: corrida fallida (smn_sin_datos)",
        tags={"alert_kind": "alertas_corrida", "corrida": "smn", "estado": "evaluada", "motivo": "smn_sin_datos"},
        extras={"smn_sin_datos": 1, "smn_avisos": 0, "smn_errores": 0},
        fingerprint=("alertas-corrida", "smn_sin_datos"),
    )


def test_an_smn_run_that_checked_the_feed_is_not_an_alert_whatever_it_found() -> None:
    assert avisos_sentry.aviso_de_corrida(metricas.TIPO_SMN, smn("evaluada", ResumenSmn(smn_sin_datos=0))) is None
    assert avisos_sentry.aviso_de_corrida(metricas.TIPO_SMN, smn("evaluada", ResumenSmn(smn_avisos=3, smn_errores=2))) is None
    for estado in ("en_curso", "apagado_a_mitad", "listo"):
        assert avisos_sentry.aviso_de_corrida(metricas.TIPO_SMN, smn(estado, ResumenSmn(smn_sin_datos=1))) is None


def test_an_smn_run_that_cannot_reach_upstash_is_an_error_like_the_forecasts() -> None:
    aviso = avisos_sentry.aviso_de_corrida(metricas.TIPO_SMN, smn("upstash_no_disponible"))
    assert aviso is not None and (aviso.nivel, aviso.tags["motivo"], aviso.tags["corrida"]) == ("error", "upstash_no_disponible", "smn")
    assert aviso.extras == {"smn_sin_datos": 0, "smn_avisos": 0, "smn_errores": 0}


def test_every_extra_of_every_alert_is_a_whole_number_and_never_a_bool() -> None:
    avisos = [
        avisos_sentry.aviso_de_corrida(metricas.TIPO_PRONOSTICO, pronostico("evaluada_incompleta", evaluadas=2)),
        avisos_sentry.aviso_de_corrida(metricas.TIPO_SMN, smn("evaluada", ResumenSmn(smn_sin_datos=1))),
        avisos_sentry.aviso_de_envios(metricas.TIPO_PRONOSTICO, pronostico("evaluada", envio=ResumenEnvio(enviados=7, fallidos=3))),
    ]
    assert all(aviso is not None and aviso.extras for aviso in avisos)
    assert all(type(valor) is int for aviso in avisos for valor in aviso.extras.values())  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# [S5] The rule of the failed sends: more than 20 % of the attempts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("enviados", "fallidos", "dispara"),
    [
        (7, 3, True),  # 30 % of 10
        (8, 2, False),  # exactly 20 %: not above
        (3, 1, False),  # 25 % but only 4 attempts and some got through
        (4, 1, False),  # 20 % of 5
        (3, 2, True),  # 40 % of 5
        (0, 2, True),  # every attempt failed (2 or more)
        (0, 1, False),  # a single attempt that failed is not a pattern
        (1, 1, False),
        (0, 0, False),
        (1, 0, False),
        (50, 0, False),
    ],
)
def test_the_sends_alert_fires_above_20_percent_of_5_or_more_attempts_or_when_all_of_2_or_more_failed(
    enviados: int, fallidos: int, dispara: bool
) -> None:
    resultado = pronostico("evaluada", envio=ResumenEnvio(enviados=enviados, fallidos=fallidos))
    assert (avisos_sentry.aviso_de_envios(metricas.TIPO_PRONOSTICO, resultado) is not None) is dispara


def test_the_sends_alert_carries_the_counters_the_attempts_and_the_integer_percentage() -> None:
    resultado = pronostico("evaluada", envio=ResumenEnvio(avisadas=2, enviados=7, fallidos=3))
    assert avisos_sentry.aviso_de_envios(metricas.TIPO_PRONOSTICO, resultado) == Aviso(
        tipo="envios",
        nivel="error",
        mensaje="alertas: fallos de envío por encima del 20 %",
        tags={"alert_kind": "alertas_envios", "corrida": "pronostico", "estado": "evaluada"},
        extras={"enviados": 7, "fallidos": 3, "vencidos": 0, "diferidos": 0, "intentos": 10, "porcentaje": 30},
        fingerprint=("alertas-envios",),
    )
    todos = pronostico("evaluada", envio=ResumenEnvio(fallidos=2))
    assert avisos_sentry.aviso_de_envios(metricas.TIPO_PRONOSTICO, todos).extras["porcentaje"] == 100  # type: ignore[union-attr]
    un_tercio = smn("evaluada", envio_=ResumenEnvio(enviados=2, fallidos=1, vencidos=4, diferidos=9))
    assert avisos_sentry.aviso_de_envios(metricas.TIPO_SMN, un_tercio) is None  # 1 of 3, under 5 attempts
    seis = smn("evaluada", envio_=ResumenEnvio(enviados=4, fallidos=2, vencidos=4, diferidos=9))
    aviso = avisos_sentry.aviso_de_envios(metricas.TIPO_SMN, seis)
    assert aviso is not None and aviso.extras["porcentaje"] == 33 and aviso.tags["corrida"] == "smn"


def test_vencidos_and_diferidos_are_not_failed_attempts() -> None:
    assert avisos_sentry.aviso_de_envios(
        metricas.TIPO_PRONOSTICO, pronostico("evaluada", envio=ResumenEnvio(enviados=5, vencidos=50, diferidos=30))
    ) is None


def test_a_run_without_sends_or_stopped_by_the_operator_has_no_sends_alert() -> None:
    assert avisos_sentry.aviso_de_envios(metricas.TIPO_PRONOSTICO, pronostico("evaluada", evaluadas=3)) is None
    parada = pronostico("apagado_a_mitad", envio=ResumenEnvio(fallidos=2))
    assert avisos_sentry.aviso_de_envios(metricas.TIPO_PRONOSTICO, parada) is None


def test_a_state_outside_the_closed_list_is_tagged_desconocido_never_with_its_own_text() -> None:
    aviso = avisos_sentry.aviso_de_envios(metricas.TIPO_PRONOSTICO, pronostico("texto-raro", envio=ResumenEnvio(fallidos=2)))
    assert aviso is not None and aviso.tags["estado"] == "desconocido"


# ---------------------------------------------------------------------------
# [S6] The rule of the signature: what warns and what stays quiet
# ---------------------------------------------------------------------------

TODOS_LOS_MOTIVOS = {getattr(firma_qstash, n) for n in dir(firma_qstash) if n.startswith("MOTIVO_")}


def test_the_two_sets_of_signature_reasons_cover_exactly_the_12_reasons_of_firma_qstash() -> None:
    assert len(TODOS_LOS_MOTIVOS) == 12
    assert avisos_sentry.MOTIVOS_QUE_AVISAN | avisos_sentry.MOTIVOS_SILENCIOSOS == TODOS_LOS_MOTIVOS
    assert avisos_sentry.MOTIVOS_QUE_AVISAN & avisos_sentry.MOTIVOS_SILENCIOSOS == set()  # a reason is one or the other
    assert avisos_sentry.MOTIVOS_QUE_AVISAN == {"clave", "sub", "body", "iss", "exp_nbf", "algoritmo", "config", "interno"}
    assert avisos_sentry.MOTIVOS_SILENCIOSOS == {"sin_cabecera", "formato", "firma_larga", "cuerpo"}


@pytest.mark.parametrize("motivo", sorted(avisos_sentry.MOTIVOS_QUE_AVISAN))
def test_a_well_formed_signature_that_does_not_match_is_a_warning_with_the_fixed_reason(motivo: str) -> None:
    assert avisos_sentry.aviso_de_firma(motivo) == Aviso(
        tipo="firma",
        nivel="warning",
        mensaje=f"alertas: /evaluar rechazó una firma de QStash ({motivo})",
        tags={"alert_kind": "alertas_firma", "motivo": motivo},
        extras={},
        fingerprint=("alertas-firma", motivo),
    )


@pytest.mark.parametrize("motivo", [*sorted(avisos_sentry.MOTIVOS_SILENCIOSOS), "otro", ""])
def test_the_noise_of_internet_scanners_and_an_unknown_reason_stay_quiet(motivo: str) -> None:
    assert avisos_sentry.aviso_de_firma(motivo) is None


# ---------------------------------------------------------------------------
# [S7] The 6-hour limit: process memory, then `SET ... NX EX 21600`
# ---------------------------------------------------------------------------


@pytest.fixture
def corrida_caida() -> tuple[str, ResultadoEvaluacion]:
    return metricas.TIPO_PRONOSTICO, pronostico("upstash_no_disponible")


KWARGS_CORRIDA_CAIDA = kwargs_de(
    "error",
    {"alert_kind": "alertas_corrida", "corrida": "pronostico", "estado": "upstash_no_disponible", "motivo": "upstash_no_disponible"},
    {"evaluadas": 0, "sin_datos": 0, "errores": 0, "diferidas": 0},
    ["alertas-corrida", "upstash_no_disponible"],
)


async def test_the_first_alert_takes_the_mark_with_one_command_and_emits_one_event_with_exact_arguments(
    redis, fake_upstash, sentry_espia, reloj_de_avisos, corrida_caida
) -> None:
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)

    assert fake_upstash.commands == [set_de(CLAVE_CORRIDA)]
    assert fake_upstash.ttls[CLAVE_CORRIDA] == SEIS_HORAS
    assert sentry_espia == [("alertas: corrida fallida (upstash_no_disponible)", KWARGS_CORRIDA_CAIDA)]


async def test_a_second_alert_right_after_costs_no_command_and_emits_nothing_the_memory_stops_it(
    redis, fake_upstash, sentry_espia, reloj_de_avisos, corrida_caida
) -> None:
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)
    reloj_de_avisos.avanzar(60)
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)

    assert fake_upstash.commands == [set_de(CLAVE_CORRIDA)]  # still the first one
    assert len(sentry_espia) == 1


async def test_after_6_hours_the_mark_is_asked_again_and_a_mark_that_still_exists_means_no_event(
    redis, fake_upstash, sentry_espia, reloj_de_avisos, corrida_caida
) -> None:
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)
    reloj_de_avisos.avanzar(SEIS_HORAS - 1)  # 21,599 s: the memory still holds
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)
    assert fake_upstash.commands == [set_de(CLAVE_CORRIDA)]

    reloj_de_avisos.avanzar(1)  # 21,600 s: the memory is over; the key (a restart, another process) still exists
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)
    assert fake_upstash.commands == [set_de(CLAVE_CORRIDA)] * 2
    assert len(sentry_espia) == 1  # the SET did not create anything: somebody alerted within the 6 hours

    reloj_de_avisos.avanzar(SEIS_HORAS + 1)  # the memory was renewed by that answer: it needs its own 6 hours
    del fake_upstash.strings[CLAVE_CORRIDA]  # and the key expired
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)
    assert fake_upstash.commands == [set_de(CLAVE_CORRIDA)] * 3
    assert len(sentry_espia) == 2
    assert sentry_espia[1] == sentry_espia[0]


async def test_a_new_process_with_the_mark_alive_stays_quiet_but_remembers(
    redis, fake_upstash, sentry_espia, reloj_de_avisos, corrida_caida
) -> None:
    fake_upstash.strings[CLAVE_CORRIDA] = "1"  # another instance alerted a moment ago
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)
    await avisos_sentry.avisar_corrida(redis, *corrida_caida)

    assert sentry_espia == []
    assert fake_upstash.commands == [set_de(CLAVE_CORRIDA)]  # one command, then the memory


async def test_each_kind_has_its_own_mark_and_one_run_can_raise_two_alerts_in_order(
    redis, fake_upstash, sentry_espia, reloj_de_avisos
) -> None:
    await avisos_sentry.avisar_corrida(redis, metricas.TIPO_PRONOSTICO, pronostico("evaluada", envio=ResumenEnvio(fallidos=2)))
    await avisos_sentry.avisar_corrida(redis, metricas.TIPO_PRONOSTICO, pronostico("upstash_no_disponible"))
    await avisos_sentry.avisar_firma_invalida(redis, "clave")

    assert fake_upstash.commands == [set_de(CLAVE_ENVIOS), set_de(CLAVE_CORRIDA), set_de(CLAVE_FIRMA)]
    assert [m for m, _ in sentry_espia] == [
        "alertas: fallos de envío por encima del 20 %",
        "alertas: corrida fallida (upstash_no_disponible)",
        "alertas: /evaluar rechazó una firma de QStash (clave)",
    ]
    # A run that is a failure AND whose sends failed: the failed run first, then the sends, each with its own mark.
    fake_upstash.commands.clear()
    reloj_de_avisos.avanzar(SEIS_HORAS)
    for clave in (CLAVE_CORRIDA, CLAVE_ENVIOS, CLAVE_FIRMA):
        del fake_upstash.strings[clave]
    sentry_espia.clear()
    await avisos_sentry.avisar_corrida(
        redis, metricas.TIPO_PRONOSTICO, pronostico("evaluada_incompleta", envio=ResumenEnvio(enviados=1, fallidos=4))
    )
    assert fake_upstash.commands == [set_de(CLAVE_CORRIDA), set_de(CLAVE_ENVIOS)]
    assert [k["tags"]["alert_kind"] for _, k in sentry_espia] == ["alertas_corrida", "alertas_envios"]


async def test_a_healthy_run_costs_zero_commands_and_zero_events(redis, fake_upstash, sentry_espia, reloj_de_avisos) -> None:
    await avisos_sentry.avisar_corrida(redis, metricas.TIPO_PRONOSTICO, pronostico("evaluada", evaluadas=3, sin_tormenta=3))
    await avisos_sentry.avisar_corrida(redis, metricas.TIPO_SMN, smn("evaluada", ResumenSmn(smn_avisos=1), ResumenEnvio(enviados=5)))
    await avisos_sentry.avisar_firma_invalida(redis, "sin_cabecera")
    assert fake_upstash.commands == [] and sentry_espia == []


async def test_if_upstash_cannot_store_the_mark_the_alert_goes_out_anyway_with_one_warning_and_the_memory_stops_the_spam(
    fake_upstash, sentry_espia, reloj_de_avisos, corrida_caida, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    redis_roto = RedisConFalla("SET")
    await avisos_sentry.avisar_corrida(redis_roto, *corrida_caida)

    assert sentry_espia == [("alertas: corrida fallida (upstash_no_disponible)", KWARGS_CORRIDA_CAIDA)]
    avisos = avisos_del_log(caplog, LOG_MARCA)
    assert [(r.levelno, r.getMessage()) for r in avisos] == [
        (logging.WARNING, f"{LOG_MARCA} exc_type=UpstashUnavailableError")
    ]
    assert "caido" not in caplog.text  # the message of the error, which could carry data, is not logged

    reloj_de_avisos.avanzar(3_600)
    await avisos_sentry.avisar_corrida(redis_roto, *corrida_caida)
    assert len(sentry_espia) == 1 and len(avisos_del_log(caplog, LOG_MARCA)) == 1  # no second event, no second command
    assert fake_upstash.commands == []


async def test_without_a_configured_upstash_the_alert_goes_out_once_with_no_command(
    fake_upstash, sentry_espia, reloj_de_avisos, corrida_caida
) -> None:
    await avisos_sentry.avisar_corrida(None, *corrida_caida)
    await avisos_sentry.avisar_corrida(None, *corrida_caida)
    assert len(sentry_espia) == 1 and fake_upstash.commands == []


# ---------------------------------------------------------------------------
# [S8] Emitting never breaks anything
# ---------------------------------------------------------------------------


async def test_a_sentry_that_raises_leaves_one_warning_with_only_the_class_and_the_caller_goes_on(
    redis, fake_upstash, monkeypatch, reloj_de_avisos, corrida_caida, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def roto(mensaje: str, **kwargs: object) -> None:
        raise RuntimeError("secreto-del-sdk")

    monkeypatch.setattr(avisos_sentry, "capture_message", roto)
    assert await avisos_sentry.avisar_corrida(redis, *corrida_caida) is None
    assert await avisos_sentry.avisar_firma_invalida(redis, "clave") is None

    assert [(r.levelno, r.getMessage()) for r in avisos_del_log(caplog, LOG_EMISION)] == [
        (logging.WARNING, f"{LOG_EMISION} exc_type=RuntimeError")
    ] * 2
    assert "secreto-del-sdk" not in caplog.text


async def test_a_bug_in_a_rule_leaves_one_warning_per_rule_and_never_reaches_the_caller(
    redis, fake_upstash, sentry_espia, reloj_de_avisos, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    sin_campos = SimpleNamespace(estado="evaluada")  # not a result: the rules cannot read it
    assert await avisos_sentry.avisar_corrida(redis, metricas.TIPO_PRONOSTICO, sin_campos) is None  # type: ignore[arg-type]

    assert [r.getMessage() for r in avisos_del_log(caplog, LOG_EMISION)] == [f"{LOG_EMISION} exc_type=AttributeError"] * 2
    assert sentry_espia == [] and fake_upstash.commands == []


async def test_a_cancellation_is_not_swallowed_and_does_not_poison_the_memory(
    redis, fake_upstash, sentry_espia, reloj_de_avisos, corrida_caida
) -> None:
    class Cancelado(UpstashRedis):
        async def set_nx(self, key: str, value: str, ex: int) -> bool:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await avisos_sentry.avisar_corrida(Cancelado(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN), *corrida_caida)
    assert sentry_espia == []

    await avisos_sentry.avisar_corrida(redis, *corrida_caida)  # nothing was decided by the cancelled attempt
    assert len(sentry_espia) == 1


def test_the_reset_for_tests_empties_the_memory(sentry_espia, reloj_de_avisos) -> None:
    avisos_sentry._ultimas["corrida"] = 5.0
    avisos_sentry.reset_para_tests()
    assert avisos_sentry._ultimas == {}


async def test_the_three_alerts_reach_a_real_sentry_event_with_message_level_tags_extras_and_fingerprint(
    redis, fake_upstash, reloj_de_avisos
) -> None:
    """With the real SDK (no spy) and a transport that keeps every envelope: the arguments of `capture_message` are the
    ones the SDK 2.x understands (`level`, `tags`, `extras`, `fingerprint`) and the filters of `main.py` let them through."""
    import sentry_sdk
    from sentry_sdk.scope import Scope
    from sentry_sdk.transport import Transport

    from app import main

    enviados: list[dict] = []

    class Captura(Transport):
        def capture_envelope(self, envelope):  # noqa: ANN001
            enviados.extend(it.payload.json for it in envelope.items if it.payload.json is not None)

    sentry_sdk.init(
        dsn="https://k@o0.ingest.sentry.io/1", transport=Captura, send_default_pii=False,
        before_send=main._scrub_event, before_send_transaction=main._scrub_transaction,
    )
    try:
        await avisos_sentry.avisar_corrida(redis, metricas.TIPO_PRONOSTICO, pronostico("sin_vapid"))
        await avisos_sentry.avisar_corrida(redis, metricas.TIPO_SMN, smn("evaluada", envio_=ResumenEnvio(enviados=3, fallidos=2)))
        await avisos_sentry.avisar_firma_invalida(redis, "iss")
        sentry_sdk.flush()
    finally:  # leave the process as it was: no client on any scope (other tests assert that Sentry is inactive)
        Scope.get_global_scope().set_client(None)
        Scope.get_isolation_scope().set_client(None)
        Scope.get_current_scope().set_client(None)

    for evento in enviados:  # the SDK's own default integration adds the process arguments; they are not ours
        evento.get("extra", {}).pop("sys.argv", None)
    por_tipo = {e["tags"]["alert_kind"]: e for e in enviados}
    assert set(por_tipo) == {"alertas_corrida", "alertas_envios", "alertas_firma"}
    corrida, envios, firma = por_tipo["alertas_corrida"], por_tipo["alertas_envios"], por_tipo["alertas_firma"]
    assert (corrida["message"], corrida["level"], corrida["fingerprint"]) == (
        "alertas: corrida fallida (sin_vapid)", "error", ["alertas-corrida", "sin_vapid"]
    )
    assert corrida["tags"] == {"alert_kind": "alertas_corrida", "corrida": "pronostico", "estado": "sin_vapid", "motivo": "sin_vapid"}
    assert corrida["extra"] == {"evaluadas": 0, "sin_datos": 0, "errores": 0, "diferidas": 0}
    assert (envios["message"], envios["level"], envios["fingerprint"]) == (
        "alertas: fallos de envío por encima del 20 %", "error", ["alertas-envios"]
    )
    assert envios["extra"] == {"enviados": 3, "fallidos": 2, "vencidos": 0, "diferidos": 0, "intentos": 5, "porcentaje": 40}
    assert (firma["message"], firma["level"], firma["fingerprint"]) == (
        "alertas: /evaluar rechazó una firma de QStash (iss)", "warning", ["alertas-firma", "iss"]
    )
    assert firma["tags"] == {"alert_kind": "alertas_firma", "motivo": "iss"} and not firma.get("extra")


# ---------------------------------------------------------------------------
# [S3, S5, S8, S9] Through the router: the response never changes, the cost is exact
# ---------------------------------------------------------------------------


async def test_with_upstash_unable_to_give_the_lock_the_response_is_the_same_and_the_failed_run_is_alerted(
    async_client: AsyncClient, fake_upstash, en_seco, install, reloj_del_router, sentry_espia,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    configure_redis(RedisSinSet(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200 and response.json() == {"estado": "upstash_no_disponible"}
    assert sentry_espia == [("alertas: corrida fallida (upstash_no_disponible)", KWARGS_CORRIDA_CAIDA)]
    # This Upstash cannot do SET NX at all: the mark could not be stored, the alert went out anyway.
    assert [r.getMessage() for r in avisos_del_log(caplog, LOG_MARCA)] == [f"{LOG_MARCA} exc_type=UpstashUnavailableError"]
    assert de_sentry(fake_upstash) == []


async def test_a_run_that_fails_listing_the_zones_alerts_after_the_counters_with_one_extra_command(
    async_client: AsyncClient, fake_upstash, en_seco, install, reloj_del_router, sentry_espia
) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    configure_redis(RedisConFalla("SMEMBERS"))
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200 and response.json() == {"estado": "upstash_no_disponible"}
    assert fake_upstash.commands[-3:] == [
        *conteo_del_dia("2026-10-14", ("pronostico:corridas:upstash_no_disponible", 1)),
        set_de(CLAVE_CORRIDA),  # the alert comes AFTER the counting
    ]
    assert [(m, k["level"], k["tags"]["motivo"]) for m, k in sentry_espia] == [
        ("alertas: corrida fallida (upstash_no_disponible)", "error", "upstash_no_disponible")
    ]


async def test_asked_to_send_without_a_vapid_key_the_response_is_the_same_and_the_run_is_an_error_alert(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, reloj_del_router, sentry_espia
) -> None:
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200 and response.json() == {"estado": "sin_vapid"}
    assert [(k["level"], k["tags"]["estado"], k["tags"]["motivo"]) for _, k in sentry_espia] == [
        ("error", "sin_vapid", "sin_vapid")
    ]
    assert de_sentry(fake_upstash) == [set_de(CLAVE_CORRIDA)]


async def test_a_forecast_run_where_every_zone_has_no_data_is_a_warning(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, install, reloj_del_router, sentry_espia
) -> None:
    install(respond=respuestas_por_zona({"cordoba": None, "rosario": None}))
    suscribir(fake_upstash, "cordoba", "rosario")
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200 and (response.json()["evaluadas"], response.json()["sin_datos"]) == (2, 2)
    assert [(k["level"], k["tags"]["motivo"], k["extras"]) for _, k in sentry_espia] == [
        ("warning", "sin_datos_total", {"evaluadas": 2, "sin_datos": 2, "errores": 0, "diferidas": 0})
    ]


async def test_a_forecast_run_with_a_partial_gap_in_the_data_is_the_usual_429_and_no_alert(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, install, reloj_del_router, sentry_espia
) -> None:
    install(respond=respuestas_por_zona({"cordoba": None, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    response = await llamar_evaluar(async_client)

    assert (response.json()["evaluadas"], response.json()["sin_datos"]) == (2, 1)
    assert sentry_espia == [] and de_sentry(fake_upstash) == []


async def test_an_smn_run_whose_sends_all_fail_keeps_its_response_and_log_and_alerts_after_the_counters(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, reloj_smn, sentry_espia,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ids = await registrar(alertas_redis, "cordoba", 2)
    for sub_id in ids:
        push.resultados[sub_id] = [envio.Resultado.ERROR]
    fake_upstash.commands.clear()
    response = await llamar_evaluar(async_client, CUERPO_SMN)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIOS_FALLIDOS
    assert [r.getMessage() for r in lineas_de_resumen_smn(caplog)] == [LINEA_SMN_ENVIOS_FALLIDOS]
    assert sentry_espia == [("alertas: fallos de envío por encima del 20 %", KWARGS_ENVIOS_FALLIDOS)]
    # The mark is the LAST command: after the counters of the run.
    assert fake_upstash.commands[-1] == set_de(CLAVE_ENVIOS)
    assert fake_upstash.commands[-2][0] == "EXPIRE" and fake_upstash.commands[-2][1].startswith(metricas.PREFIJO)
    assert de_sentry(fake_upstash) == [set_de(CLAVE_ENVIOS)]


async def test_a_healthy_forecast_run_and_a_healthy_smn_run_through_the_router_cost_no_sentry_command(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, install, reloj_del_router, sentry_espia
) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json()["estado"] == "evaluada"
    assert sentry_espia == [] and de_sentry(fake_upstash) == []


async def test_a_healthy_smn_run_with_the_alert_sent_costs_no_sentry_command(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, reloj_smn, sentry_espia
) -> None:
    await registrar(alertas_redis, "cordoba", 2)
    response = await llamar_evaluar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json()["enviados"] == 2
    feed.obtener = avisos_por_zona({})
    fake_upstash.strings.pop(CLAVE_LOCK_SMN)
    assert (await llamar_evaluar(async_client, CUERPO_SMN)).status_code == 200
    assert sentry_espia == [] and de_sentry(fake_upstash) == []


async def test_an_smn_run_that_cannot_verify_the_feed_is_a_warning_alert(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, reloj_smn, sentry_espia
) -> None:
    feed.obtener = avisos_por_zona({}, available=False)
    suscribir(fake_upstash, "cordoba")
    response = await llamar_evaluar(async_client, CUERPO_SMN)

    assert response.status_code == 200 and response.json()["smn_sin_datos"] == 1
    assert sentry_espia == [(
        "alertas: corrida fallida (smn_sin_datos)",
        kwargs_de(
            "warning",
            {"alert_kind": "alertas_corrida", "corrida": "smn", "estado": "evaluada", "motivo": "smn_sin_datos"},
            {"smn_sin_datos": 1, "smn_avisos": 0, "smn_errores": 0},
            ["alertas-corrida", "smn_sin_datos"],
        ),
    )]


# ---------------------------------------------------------------------------
# [S6, S7, S8] Through the router: the 401 of a signature that is well formed but wrong
# ---------------------------------------------------------------------------


async def test_a_signature_of_a_foreign_key_is_the_same_401_and_one_warning_with_one_command(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_espia
) -> None:
    firma = firmar(CUERPO, clave=CLAVE_AJENA)
    response = await llamar_evaluar(async_client, CUERPO, firma)

    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert sentry_espia == [(
        "alertas: /evaluar rechazó una firma de QStash (clave)",
        kwargs_de("warning", {"alert_kind": "alertas_firma", "motivo": "clave"}, {}, ["alertas-firma", "clave"]),
    )]
    assert fake_upstash.commands == [set_de(CLAVE_FIRMA)]


@pytest.mark.parametrize(
    ("motivo", "firma"),
    [
        ("clave", lambda: firmar(CUERPO, clave=CLAVE_AJENA)),
        ("sub", lambda: firmar(CUERPO, sub="https://otro.example/api/alertas/evaluar")),
        ("body", lambda: firmar(b'{"otro":"cuerpo"}')),
        ("iss", lambda: firmar(CUERPO, iss="Otro")),
        ("exp_nbf", lambda: firmar(CUERPO, exp_en=-100, nbf_en=-200)),
        ("algoritmo", lambda: firmar(CUERPO, algoritmo="HS384")),
    ],
)
async def test_every_reason_that_comes_after_parsing_a_jwt_warns_with_its_own_code(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_espia, motivo: str, firma
) -> None:
    response = await llamar_evaluar(async_client, CUERPO, firma())
    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert [(k["tags"]["alert_kind"], k["tags"]["motivo"]) for _, k in sentry_espia] == [("alertas_firma", motivo)]


@pytest.mark.parametrize("firma", [None, "", "no-es-un-jwt", "x" * 5000])
async def test_the_noise_of_scanners_is_the_same_401_with_no_event_and_no_command(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_espia, firma: str | None
) -> None:
    response = await llamar_evaluar(async_client, CUERPO, firma)
    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert sentry_espia == [] and fake_upstash.commands == []


async def test_a_body_over_the_limit_is_quiet_noise_too(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_espia
) -> None:
    enorme = b"x" * (router_alertas.MAX_CUERPO_EVALUAR_BYTES + 1)
    response = await llamar_evaluar(async_client, enorme, firmar(CUERPO))
    assert response.status_code == 401 and sentry_espia == [] and fake_upstash.commands == []


async def test_30_wrong_signatures_in_a_row_are_one_event_and_one_command(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_espia
) -> None:
    for _ in range(30):  # the rate limit of the endpoint is 30 a minute
        response = await llamar_evaluar(async_client, CUERPO, firmar(CUERPO, clave=CLAVE_AJENA))
        assert response.status_code == 401 and response.json() == NO_AUTORIZADO

    assert len(sentry_espia) == 1
    assert fake_upstash.commands == [set_de(CLAVE_FIRMA)]


async def test_without_a_configured_upstash_a_wrong_signature_still_warns_once_from_the_memory(
    async_client: AsyncClient, fake_upstash, sentry_espia
) -> None:
    for _ in range(3):
        response = await llamar_evaluar(async_client, CUERPO, firmar(CUERPO, clave=CLAVE_AJENA))
        assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert len(sentry_espia) == 1 and fake_upstash.commands == []


async def test_a_valid_signature_never_raises_the_signature_alert(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_espia
) -> None:
    response = await llamar_evaluar(async_client)  # both flags off: `apagado`, nothing is touched
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert sentry_espia == [] and de_sentry(fake_upstash) == []


# ---------------------------------------------------------------------------
# [S8] A Sentry that fails inside the router changes nothing
# ---------------------------------------------------------------------------


@pytest.fixture
def sentry_roto(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    llamadas: list[str] = []

    def roto(mensaje: str, **kwargs: object) -> None:
        llamadas.append(mensaje)
        raise RuntimeError("secreto-del-sdk")

    monkeypatch.setattr(avisos_sentry, "capture_message", roto)
    return llamadas


async def test_a_sentry_that_raises_does_not_change_the_401(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_roto, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = await llamar_evaluar(async_client, CUERPO, firmar(CUERPO, clave=CLAVE_AJENA))

    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert sentry_roto == ["alertas: /evaluar rechazó una firma de QStash (clave)"]
    assert [r.getMessage() for r in avisos_del_log(caplog, LOG_EMISION)] == [f"{LOG_EMISION} exc_type=RuntimeError"]
    assert "secreto-del-sdk" not in caplog.text
    assert any("motivo=clave" in r.getMessage() for r in caplog.records)  # the log of the rejection is still there


async def test_a_sentry_that_raises_does_not_change_a_run_that_sends_nor_its_pushes_nor_its_log(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, reloj_smn, sentry_roto,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ids = await registrar(alertas_redis, "cordoba", 2)
    for sub_id in ids:
        push.resultados[sub_id] = [envio.Resultado.ERROR]
    response = await llamar_evaluar(async_client, CUERPO_SMN)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIOS_FALLIDOS
    assert sorted({c.sub_id for c in push.llamadas}) == sorted(ids)
    assert [r.getMessage() for r in lineas_de_resumen_smn(caplog)] == [LINEA_SMN_ENVIOS_FALLIDOS]
    assert sentry_roto == ["alertas: fallos de envío por encima del 20 %"]
    assert [r.getMessage() for r in avisos_del_log(caplog, LOG_EMISION)] == [f"{LOG_EMISION} exc_type=RuntimeError"]
    assert fake_upstash.hashes  # the counters of the run were written before


# ---------------------------------------------------------------------------
# [S8] Privacy: only names of states and whole numbers
# ---------------------------------------------------------------------------


async def test_no_event_carries_an_id_endpoint_zone_lock_value_or_signature(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, reloj_smn, sentry_espia
) -> None:
    ids = await registrar(alertas_redis, "cordoba", 2)
    for sub_id in ids:
        push.resultados[sub_id] = [envio.Resultado.ERROR]
    firma_usada = firmar(CUERPO, clave=CLAVE_AJENA)
    assert (await llamar_evaluar(async_client, CUERPO_SMN)).status_code == 200
    assert (await llamar_evaluar(async_client, CUERPO, firma_usada)).status_code == 401
    assert [k["tags"]["alert_kind"] for _, k in sentry_espia] == ["alertas_envios", "alertas_firma"]

    texto = json.dumps(sentry_espia)
    for secreto in (*ids, endpoint_de("cordoba", 0), "fcm.googleapis.com", "SECRETO", "cordoba", firma_usada,
                    fake_upstash.strings[CLAVE_LOCK_SMN], "/api/alertas/evaluar"):
        assert secreto not in texto, secreto

    tags_cerrados = {
        "alert_kind": {"alertas_corrida", "alertas_envios", "alertas_firma"},
        "corrida": {"pronostico", "smn"},
        "estado": set(metricas.ESTADOS_CONOCIDOS),
        "motivo": avisos_sentry.MOTIVOS_QUE_AVISAN
        | {"upstash_no_disponible", "sin_vapid", "evaluada_incompleta", "sin_datos_total", "smn_sin_datos"},
    }
    for _, kwargs in sentry_espia:
        assert set(kwargs) == {"level", "tags", "extras", "fingerprint"}
        assert all(valor in tags_cerrados[nombre] for nombre, valor in kwargs["tags"].items())
        assert all(type(valor) is int for valor in kwargs["extras"].values())
    # And the only Upstash commands the alerts add are the constant marks.
    assert de_sentry(fake_upstash) == [set_de(CLAVE_ENVIOS), set_de(CLAVE_FIRMA)]


def test_the_time_limit_and_the_keys_of_the_marks_do_not_collide_with_the_existing_keys() -> None:
    assert avisos_sentry.LIMITE_SEGUNDOS == SEIS_HORAS
    existentes = ("alertas:ids", "alertas:zonas", "alertas:sub:", "alertas:zona:", "alertas:lock:", "alertas:apagado",
                  "alertas:enviado:", "alertas:smn:enviado:", "alertas:prueba:", "alertas:metricas:")
    for tipo in (avisos_sentry.AVISO_CORRIDA, avisos_sentry.AVISO_ENVIOS, avisos_sentry.AVISO_FIRMA):
        clave = f"{avisos_sentry.PREFIJO}:{tipo}"
        assert clave in (CLAVE_CORRIDA, CLAVE_ENVIOS, CLAVE_FIRMA)
        assert not any(clave.startswith(prefijo) for prefijo in existentes)
