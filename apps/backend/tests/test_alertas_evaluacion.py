"""Scheduled alert evaluation, dry run (FRA-355, PR5b): `services/alertas/evaluacion.py`.

`evaluar(redis, ahora)` takes the run lock, reads the zones that have subscribers, asks ECMWF for each one (under the
fixed job client key, so the GLOBAL Open-Meteo budget still applies), applies the storm rule and COUNTS. It never
sends anything, never deletes anything, never reads a subscription and never reads the wall clock: `ahora` comes from
the caller. Everything here runs against `FakeUpstash` and `FakeOpenMeteoSource`; there is no network.

Contract pinned by these tests (the numbers in brackets are the points of the PR5b design):
  [1] modes: the router decides (see test_alertas_evaluar_router.py); the evaluator itself never sends
  [2] lock `alertas:lock:evaluar` with SET NX EX, never released with DEL; Upstash down at the lock = no evaluation
  [3] window from `regla.ventana(ahora)`, `ahora` must carry a time zone
  [4] zones from `alertas:zonas` ∩ catalog, only those with subscribers, most subscribers first (ties: catalog
      order), capped, extras `diferidas`
  [5] one ECMWF request per zone; no usable data (None, refused, stale) is `sin_datos`, never "no storm". A storm
      in fresh data is reported even if some hour has a hole; "no storm" needs EVERY hour of the window with BOTH
      `weather_code` and `cape`, otherwise `sin_datos`
  [6] job client key `job:alertas` (see test_alertas_con_clave.py)
  [7] result: integer counters for the response and the log, the per-zone detail (`zonas`) only for the caller
  [8] the kill key is read again before EVERY zone
  [9] run deadline: the zones not reached are `diferidas`, the state is `evaluada_incompleta`
"""
from __future__ import annotations

import ast
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from app.core.cache import FetchRefused
from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas import envio, evaluacion, interruptor, pronostico, regla
from app.services.alertas import suscripcion as svc
from app.services.alertas.evaluacion import ResultadoEvaluacion
from app.services.alertas.zonas import ZONAS, zona_por_slug
from app.services.openmeteo_source import CacheLevel
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    AHORA,
    AR,
    CALMA,
    CLAVE_APAGADO,
    CLAVE_LOCK,
    TORMENTA,
    LecturaQueSeRompe,
    RedisConFalla,
    RedisQueMideConcurrencia,
    comandos,
    payload_horario,
    redis,
    reloj_de_openmeteo,
    respuestas_por_zona,
    suscribir,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.test_alertas_suscripcion import AUTH, P256DH

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo, monkeypatch):  # noqa: F811
    """Fresh caches with a recording backend and a frozen `fetched_at` clock for every test of this file."""
    return own_caches


# ---------------------------------------------------------------------------
# [3] The window and the injected clock
# ---------------------------------------------------------------------------


async def test_a_naive_now_is_rejected_before_touching_anything(redis, fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "cordoba")
    with pytest.raises(ValueError):
        await evaluacion.evaluar(redis, AHORA.replace(tzinfo=None))
    assert fake_upstash.commands == []
    assert fake.calls == []


@pytest.mark.parametrize("hora", [0, 3, 6, 8, 9, 11, 12, 14, 15, 17, 18, 20, 22, 23])
async def test_outside_the_review_hours_and_in_the_silence_nothing_is_evaluated(
    redis, fake_upstash, install, hora: int
) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, datetime(2026, 10, 14, hora, 15, tzinfo=AR))
    assert resultado == ResultadoEvaluacion(estado="fuera_de_ventana")
    assert fake_upstash.commands == []  # no lock, no zones: the clock decides before Upstash is touched
    assert fake.calls == []


@pytest.mark.parametrize("hora", [7, 10, 13, 16, 19, 21])
async def test_on_a_review_hour_the_run_goes_ahead(redis, fake_upstash, install, hora: int) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, datetime(2026, 10, 14, hora, 0, tzinfo=AR))
    assert resultado.estado == "evaluada"
    assert resultado.evaluadas == 1


@pytest.mark.parametrize(
    ("hora_de_la_corrida", "hora_de_la_tormenta", "esperado"),
    [
        (10, 15, "con_tormenta"),  # today's 10 h review looks from 10:00 to midnight of today
        (10, 8, "sin_tormenta"),  # before the start of the window
        (10, 24 + 15, "sin_tormenta"),  # tomorrow is not covered by a today review
        (19, 22, "con_tormenta"),
        (21, 24 + 15, "con_tormenta"),  # the 21 h review covers tomorrow
        (21, 15, "sin_tormenta"),  # ... and not what is left of today
    ],
)
async def test_the_window_comes_from_the_rule(
    redis, fake_upstash, install, reloj_de_openmeteo, hora_de_la_corrida: int, hora_de_la_tormenta: int, esperado: str
) -> None:
    ahora = datetime(2026, 10, 14, hora_de_la_corrida, 10, tzinfo=AR)
    reloj_de_openmeteo.instante = ahora  # the data is as fresh as the run
    install(payload_horario(codigos={hora_de_la_tormenta: 95}))
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, ahora)
    assert getattr(resultado, esperado) == 1


async def test_a_now_in_another_time_zone_is_read_in_argentina_time(redis, fake_upstash, install) -> None:
    install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    # 13:30 UTC is 10:30 in Argentina: the 10 h review.
    resultado = await evaluacion.evaluar(redis, datetime(2026, 10, 14, 13, 30, tzinfo=timezone.utc))
    assert resultado.estado == "evaluada" and resultado.con_tormenta == 1


# ---------------------------------------------------------------------------
# [2] The run lock
# ---------------------------------------------------------------------------


async def test_the_lock_is_taken_with_nx_and_an_expiry_and_an_opaque_value(redis, fake_upstash, install) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    await evaluacion.evaluar(redis, AHORA)
    primero = fake_upstash.commands[0]
    assert primero[:2] == ["SET", CLAVE_LOCK]
    assert primero[3:] == ["NX", "EX", "600"]
    valor = primero[2]
    assert len(valor) >= 16 and valor not in ("1", "true", "OK")
    assert fake_upstash.strings[CLAVE_LOCK] == valor
    assert fake_upstash.ttls[CLAVE_LOCK] == 600
    assert fake_upstash.requests[0].url == httpx.URL(f"{FAKE_UPSTASH_URL}/")  # the value goes in the body


async def test_the_lock_expiry_is_the_configured_one(redis, fake_upstash, install, monkeypatch) -> None:
    monkeypatch.setattr(settings, "alertas_lock_ttl_segundos", 400)
    install(CALMA)
    await evaluacion.evaluar(redis, AHORA)
    assert fake_upstash.commands[0][3:] == ["NX", "EX", "400"]


async def test_two_runs_do_not_use_the_same_lock_value(redis, fake_upstash, install) -> None:
    install(CALMA)
    await evaluacion.evaluar(redis, AHORA)
    primero = fake_upstash.strings.pop(CLAVE_LOCK)
    await evaluacion.evaluar(redis, AHORA)
    assert fake_upstash.strings[CLAVE_LOCK] != primero


async def test_a_run_that_finds_the_lock_taken_does_nothing(redis, fake_upstash, install) -> None:
    fake = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    fake_upstash.strings[CLAVE_LOCK] = "otra-corrida"
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado == ResultadoEvaluacion(estado="en_curso")
    assert comandos(fake_upstash) == ["SET"]  # it asked for the lock and stopped
    assert fake_upstash.strings[CLAVE_LOCK] == "otra-corrida"  # the other owner's lock is untouched
    assert fake.calls == []


async def test_the_lock_is_left_to_expire_and_never_deleted(redis, fake_upstash, install) -> None:
    install(TORMENTA)
    suscribir(fake_upstash, "cordoba", "rosario")
    await evaluacion.evaluar(redis, AHORA)
    assert "DEL" not in comandos(fake_upstash)
    assert CLAVE_LOCK in fake_upstash.strings  # still there: it expires by itself
    # ... so a second run right after is turned away.
    assert (await evaluacion.evaluar(redis, AHORA)).estado == "en_curso"


async def test_a_lock_that_cannot_be_taken_because_upstash_fails_stops_the_run(fake_upstash, install) -> None:
    fake = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    # Only the lock command fails: the zones could be read, so a run that went on anyway would evaluate them.
    resultado = await evaluacion.evaluar(RedisConFalla("SET"), AHORA)
    assert resultado == ResultadoEvaluacion(estado="upstash_no_disponible")
    assert fake.calls == []
    assert ["SMEMBERS"] not in [comando[:1] for comando in fake_upstash.commands]  # it never got to the zones


# ---------------------------------------------------------------------------
# [4] Which zones are evaluated
# ---------------------------------------------------------------------------


async def test_with_no_subscribed_zones_there_is_nothing_to_do(redis, fake_upstash, install) -> None:
    fake = install(TORMENTA)
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado == ResultadoEvaluacion(estado="evaluada")
    assert fake.calls == []


async def test_only_zones_with_at_least_one_subscriber_are_asked_about(redis, fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "cordoba", "rosario")
    fake_upstash.sets["alertas:zonas"].add("mendoza")  # listed, but its subscriber set is empty (all left)
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.zonas_con_suscriptores == 2 and resultado.evaluadas == 2
    assert len(fake.calls) == 2
    pedidas = {(c.params["latitude"], c.params["longitude"]) for c in fake.calls}
    assert pedidas == {(zona_por_slug(s).lat, zona_por_slug(s).lon) for s in ("cordoba", "rosario")}


async def test_an_unknown_slug_is_ignored_counted_and_never_touched(redis, fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "cordoba")
    fake_upstash.sets["alertas:zonas"].update({"ciudad-que-no-existe", "../../otra:clave", "ALERTAS:IDS"})
    antes = {clave: set(valores) for clave, valores in fake_upstash.sets.items()}
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.desconocidas == 3 and resultado.evaluadas == 1 and resultado.zonas_con_suscriptores == 1
    assert len(fake.calls) == 1
    assert fake_upstash.sets == antes  # nothing is pruned
    assert not {"SREM", "SADD", "DEL"} & set(comandos(fake_upstash))
    for comando in fake_upstash.commands:  # an unknown slug never becomes part of a key
        assert not any("ciudad-que-no-existe" in arg or "otra:clave" in arg for arg in comando)


async def test_zones_with_the_same_subscribers_go_in_catalog_order_and_the_extras_are_deferred(
    redis, fake_upstash, install, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alertas_max_zonas_por_corrida", 2)
    fake = install(CALMA)
    # In the catalog: mendoza, tucuman, salta. In alphabetical order: mendoza, salta, tucuman.
    suscribir(fake_upstash, "salta", "tucuman", "mendoza")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado == ResultadoEvaluacion(
        estado="evaluada", zonas_con_suscriptores=3, evaluadas=2, sin_tormenta=2, diferidas=1
    )
    pedidas = [(c.params["latitude"], c.params["longitude"]) for c in fake.calls]
    assert pedidas == [(zona_por_slug(s).lat, zona_por_slug(s).lon) for s in ("mendoza", "tucuman")]


async def test_the_order_does_not_depend_on_the_order_of_the_set(redis, fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "salta", "buenos-aires", "tucuman", "cordoba", "mendoza")
    await evaluacion.evaluar(redis, AHORA)
    orden = [s.slug for s in ZONAS if s.slug in {"salta", "buenos-aires", "tucuman", "cordoba", "mendoza"}]
    assert [(c.params["latitude"]) for c in fake.calls] == [zona_por_slug(s).lat for s in orden]


async def test_a_run_with_exactly_the_cap_defers_nothing(redis, fake_upstash, install, monkeypatch) -> None:
    monkeypatch.setattr(settings, "alertas_max_zonas_por_corrida", 3)
    install(CALMA)
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.evaluadas == 3 and resultado.diferidas == 0


async def test_zones_with_more_subscribers_go_first_and_ties_follow_the_catalog(redis, fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "mendoza")  # catalog index 3, 1 subscriber
    suscribir(fake_upstash, "salta", cantidad=3)  # index 7, 3 subscribers
    suscribir(fake_upstash, "cordoba", cantidad=2)  # index 1, 2 subscribers
    suscribir(fake_upstash, "tucuman", cantidad=3)  # index 4, 3 subscribers (ties with salta: the catalog decides)
    await evaluacion.evaluar(redis, AHORA)
    pedidas = [c.params["latitude"] for c in fake.calls]
    assert pedidas == [zona_por_slug(s).lat for s in ("tucuman", "salta", "cordoba", "mendoza")]


async def test_when_the_cap_bites_the_zones_with_fewer_subscribers_are_the_deferred_ones(
    redis, fake_upstash, install, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alertas_max_zonas_por_corrida", 2)
    fake = install(CALMA)
    suscribir(fake_upstash, "buenos-aires")  # first in the catalog but with a single subscriber
    suscribir(fake_upstash, "salta", cantidad=4)
    suscribir(fake_upstash, "mendoza", cantidad=2)
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.evaluadas == 2 and resultado.diferidas == 1
    assert [c.params["latitude"] for c in fake.calls] == [zona_por_slug(s).lat for s in ("salta", "mendoza")]
    assert [(z.slug, z.veredicto, z.suscriptores) for z in resultado.zonas] == [
        ("salta", "sin_tormenta", 4),
        ("mendoza", "sin_tormenta", 2),
        ("buenos-aires", "diferida", 1),
    ]


async def test_with_a_cap_of_25_the_other_25_catalog_zones_are_deferred(redis, fake_upstash, install, monkeypatch) -> None:
    monkeypatch.setattr(settings, "alertas_max_zonas_por_corrida", 25)
    fake = install(CALMA)
    suscribir(fake_upstash, *(z.slug for z in ZONAS))
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.zonas_con_suscriptores == len(ZONAS) == 50
    assert resultado.evaluadas == 25 and resultado.diferidas == 25
    assert len(fake.calls) == 25


async def test_by_default_every_catalog_zone_is_evaluated(redis, fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, *(z.slug for z in ZONAS))
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.zonas_con_suscriptores == 50 and resultado.evaluadas == 50 and resultado.diferidas == 0
    assert len(fake.calls) == 50


async def test_the_zones_are_read_from_the_documented_keys_by_the_real_signup(redis, fake_upstash, install) -> None:
    """The keys the evaluator reads are the ones `suscripcion.alta` writes (they are two copies of the same name)."""
    fake = install(CALMA)
    for i, zona in enumerate(("cordoba", "cordoba", "rosario")):
        await svc.alta(redis, svc.Suscripcion(f"https://fcm.googleapis.com/fcm/send/real-{i}", P256DH, AUTH, zona))
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.zonas_con_suscriptores == 2 and resultado.evaluadas == 2
    assert len(fake.calls) == 2


async def test_it_only_reads_counts_never_the_ids_nor_the_subscriptions(redis, fake_upstash, install) -> None:
    install(TORMENTA)
    suscribir(fake_upstash, "cordoba", "rosario", cantidad=3)
    await evaluacion.evaluar(redis, AHORA)
    assert set(comandos(fake_upstash)) <= {"SET", "SMEMBERS", "SCARD", "GET"}
    for comando in fake_upstash.commands:
        if comando[0] == "SMEMBERS":
            assert comando[1] == "alertas:zonas"
        if comando[0] == "GET":
            assert comando[1] == CLAVE_APAGADO
        assert not any(arg.startswith("alertas:sub:") for arg in comando)


@pytest.mark.parametrize("comando", ["SMEMBERS", "SCARD"])
async def test_if_upstash_fails_while_listing_the_zones_nothing_is_evaluated(
    fake_upstash, install, comando: str
) -> None:
    fake = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(RedisConFalla(comando), AHORA)
    assert resultado == ResultadoEvaluacion(estado="upstash_no_disponible")
    assert fake.calls == []


# ---------------------------------------------------------------------------
# [5] What each zone says
# ---------------------------------------------------------------------------


async def test_a_storm_code_in_the_window_is_a_storm(redis, fake_upstash, install) -> None:
    install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    assert await evaluacion.evaluar(redis, AHORA) == ResultadoEvaluacion(
        estado="evaluada", zonas_con_suscriptores=1, evaluadas=1, con_tormenta=1
    )


async def test_a_high_cape_in_the_window_is_a_storm(redis, fake_upstash, install) -> None:
    install(payload_horario(cape={16: 2500.0}))
    suscribir(fake_upstash, "cordoba")
    assert (await evaluacion.evaluar(redis, AHORA)).con_tormenta == 1


async def test_a_calm_zone_is_no_storm(redis, fake_upstash, install) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    assert await evaluacion.evaluar(redis, AHORA) == ResultadoEvaluacion(
        estado="evaluada", zonas_con_suscriptores=1, evaluadas=1, sin_tormenta=1
    )


async def test_every_zone_gets_its_own_verdict(redis, fake_upstash, install) -> None:
    install(
        respond=respuestas_por_zona(
            {"cordoba": TORMENTA, "rosario": CALMA, "mendoza": None, "salta": FetchRefused("tope")}
        )
    )
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza", "salta")
    assert await evaluacion.evaluar(redis, AHORA) == ResultadoEvaluacion(
        estado="evaluada",
        zonas_con_suscriptores=4,
        evaluadas=4,
        con_tormenta=1,
        sin_tormenta=1,
        sin_datos=2,
    )


@pytest.mark.parametrize(
    "respuesta",
    [
        None,
        FetchRefused("tope"),
        {},
        {"hourly": {}},
        payload_horario(horas=23),
        payload_horario(codigos={15: None}, cape={15: None}),
        payload_horario(cape={15: None}),
        payload_horario(codigos={15: None}),
        payload_horario(cape_base=None),
        payload_horario(codigo_base=None),
    ],
    ids=[
        "fallo", "rechazado-por-el-tope", "payload-vacio", "sin-horas", "serie-corta", "hueco",
        "hueco-solo-cape", "hueco-solo-codigo", "sin-cape-en-ninguna-hora", "sin-codigo-en-ninguna-hora",
    ],
)
async def test_no_data_is_sin_datos_and_never_sin_tormenta(redis, fake_upstash, install, respuesta) -> None:
    install(respuesta)
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado == ResultadoEvaluacion(estado="evaluada", zonas_con_suscriptores=1, evaluadas=1, sin_datos=1)


async def test_stale_data_is_sin_datos_whatever_it_says(redis, fake_upstash, install, reloj_de_openmeteo) -> None:
    reloj_de_openmeteo.instante = AHORA - timedelta(minutes=91)
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.sin_datos == 2 and resultado.con_tormenta == 0 and resultado.sin_tormenta == 0


async def test_data_of_exactly_90_minutes_still_counts(redis, fake_upstash, install, reloj_de_openmeteo) -> None:
    reloj_de_openmeteo.instante = AHORA - timedelta(minutes=90)
    install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    assert (await evaluacion.evaluar(redis, AHORA)).con_tormenta == 1


async def test_an_unexpected_error_in_one_zone_is_an_error_not_sin_datos_and_the_others_go_on(
    redis, fake_upstash, install, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": RuntimeError("bug de prueba"), "rosario": TORMENTA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.errores == 1 and resultado.sin_datos == 0 and resultado.con_tormenta == 1 and resultado.evaluadas == 2
    assert any(r.levelno >= logging.ERROR and r.name == evaluacion.logger.name for r in caplog.records)
    assert [z.veredicto for z in resultado.zonas] == ["error", "con_tormenta"]


async def test_a_bug_in_the_rule_is_an_error_of_that_zone_and_not_an_exception_with_the_lock_taken(
    redis, fake_upstash, install, monkeypatch
) -> None:
    def regla_rota(hourly, ahora):
        raise RuntimeError("bug en la regla")

    monkeypatch.setattr(regla, "evaluar_revision", regla_rota)
    install(CALMA)
    suscribir(fake_upstash, "cordoba", "rosario")
    resultado = await evaluacion.evaluar(redis, AHORA)  # does not raise
    assert resultado == ResultadoEvaluacion(
        estado="evaluada", zonas_con_suscriptores=2, evaluadas=2, errores=2
    )
    assert CLAVE_LOCK in fake_upstash.strings


async def test_errors_and_sin_datos_are_counted_apart(redis, fake_upstash, install) -> None:
    install(respond=respuestas_por_zona({"cordoba": RuntimeError("bug"), "rosario": None, "mendoza": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert (resultado.errores, resultado.sin_datos, resultado.sin_tormenta, resultado.evaluadas) == (1, 1, 1, 3)


async def test_the_answers_are_not_persisted(redis, fake_upstash, install, _entorno) -> None:
    install(TORMENTA)
    suscribir(fake_upstash, "cordoba", "rosario")
    await evaluacion.evaluar(redis, AHORA)
    await _entorno.caches[CacheLevel.FORECAST].flush_persistence()  # a save is scheduled in the background
    assert _entorno.backend.saved == [] and _entorno.backend.loaded == []


# --- The coverage rule: positive evidence is never discarded, and "no storm" needs the whole window with BOTH values


async def test_a_storm_is_reported_even_if_another_hour_has_a_hole(redis, fake_upstash, install) -> None:
    install(payload_horario(codigos={15: 95, 20: None}, cape={20: None}))  # hour 20 has neither value
    suscribir(fake_upstash, "cordoba")
    assert await evaluacion.evaluar(redis, AHORA) == ResultadoEvaluacion(
        estado="evaluada", zonas_con_suscriptores=1, evaluadas=1, con_tormenta=1
    )


async def test_a_storm_is_reported_from_a_series_that_stops_before_the_end_of_the_window(
    redis, fake_upstash, install
) -> None:
    install(payload_horario(horas=23, codigos={15: 95}))
    suscribir(fake_upstash, "cordoba")
    assert (await evaluacion.evaluar(redis, AHORA)).con_tormenta == 1


async def test_a_storm_by_code_is_reported_even_if_cape_is_missing_everywhere(redis, fake_upstash, install) -> None:
    install(payload_horario(cape_base=None, codigos={15: 96}))
    suscribir(fake_upstash, "cordoba")
    assert (await evaluacion.evaluar(redis, AHORA)).con_tormenta == 1


async def test_a_storm_by_cape_is_reported_even_if_codes_are_missing_everywhere(redis, fake_upstash, install) -> None:
    install(payload_horario(codigo_base=None, cape={16: 3000.0}))
    suscribir(fake_upstash, "cordoba")
    assert (await evaluacion.evaluar(redis, AHORA)).con_tormenta == 1


async def test_only_weather_codes_everywhere_cannot_conclude_no_storm(redis, fake_upstash, install) -> None:
    install(payload_horario(cape_base=None))
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.sin_datos == 1 and resultado.sin_tormenta == 0


async def test_only_cape_everywhere_cannot_conclude_no_storm(redis, fake_upstash, install) -> None:
    install(payload_horario(codigo_base=None))
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.sin_datos == 1 and resultado.sin_tormenta == 0


async def test_both_values_in_every_hour_conclude_no_storm_or_a_storm_as_the_rule_says(
    redis, fake_upstash, install
) -> None:
    install(respond=respuestas_por_zona({"cordoba": CALMA, "rosario": TORMENTA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert (resultado.sin_tormenta, resultado.con_tormenta, resultado.sin_datos) == (1, 1, 0)


async def test_a_hole_in_the_other_variable_of_one_hour_blocks_no_storm(redis, fake_upstash, install) -> None:
    install(payload_horario(cape={15: None}))  # the code of hour 15 is there but its CAPE is not
    suscribir(fake_upstash, "cordoba")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.sin_datos == 1 and resultado.sin_tormenta == 0


# ---------------------------------------------------------------------------
# [8] The kill key, read again before every zone
# ---------------------------------------------------------------------------


async def test_the_kill_key_is_read_before_each_zone(redis, fake_upstash, install) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza")
    await evaluacion.evaluar(redis, AHORA)
    assert comandos(fake_upstash).count("GET") == 3
    ordenados = comandos(fake_upstash)
    assert ordenados.index("GET") > ordenados.index("SCARD")  # the zones were already known
    assert fake_upstash.commands.count(["GET", CLAVE_APAGADO]) == 3


async def test_a_kill_key_that_appears_mid_run_stops_before_the_next_zone(redis, fake_upstash, install) -> None:
    def respond(params):
        fake_upstash.strings[CLAVE_APAGADO] = "1"  # the owner sets it from the Upstash console during the run
        return CALMA

    fuente = install(respond=respond)
    suscribir(fake_upstash, "mendoza", "tucuman", "salta")
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado == ResultadoEvaluacion(
        estado="apagado_a_mitad", zonas_con_suscriptores=3, evaluadas=1, sin_tormenta=1, diferidas=2
    )
    assert len(fuente.calls) == 1  # the second zone was never asked about


async def test_a_kill_key_already_there_stops_before_the_first_zone(redis, fake_upstash, install) -> None:
    fake = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    fake_upstash.strings[CLAVE_APAGADO] = "cualquier valor"
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado == ResultadoEvaluacion(estado="apagado_a_mitad", zonas_con_suscriptores=1, diferidas=1)
    assert fake.calls == []


async def test_an_unreadable_kill_key_mid_run_counts_as_off(fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "mendoza", "tucuman", "salta")
    resultado = await evaluacion.evaluar(LecturaQueSeRompe(buenas=1), AHORA)
    assert resultado == ResultadoEvaluacion(
        estado="apagado_a_mitad", zonas_con_suscriptores=3, evaluadas=1, sin_tormenta=1, diferidas=2
    )
    assert len(fake.calls) == 1


async def test_an_unusable_kill_key_answer_counts_as_off(fake_upstash, install) -> None:
    fake = install(CALMA)
    suscribir(fake_upstash, "cordoba")

    class _RespuestaRota(UpstashRedis):
        async def read_strict(self, key: str) -> str | None:
            raise UpstashUnavailableError("resultado_no_es_texto")

    resultado = await evaluacion.evaluar(_RespuestaRota(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN), AHORA)
    assert resultado.estado == "apagado_a_mitad" and fake.calls == []


# ---------------------------------------------------------------------------
# Small robustness: bounded fan-out, one shared reader of the kill key
# ---------------------------------------------------------------------------


async def test_the_scard_fan_out_over_the_zones_is_bounded_but_still_parallel(fake_upstash, install) -> None:
    install(CALMA)
    suscribir(fake_upstash, *(z.slug for z in ZONAS))
    medido = RedisQueMideConcurrencia()
    resultado = await evaluacion.evaluar(medido, AHORA)
    assert resultado.zonas_con_suscriptores == 50
    assert 2 <= medido.max_simultaneos <= 10


async def test_the_per_zone_check_and_the_switch_use_the_shared_fail_closed_reader(
    redis, fake_upstash, install, monkeypatch
) -> None:
    visto: list[object] = []

    async def lector_falso(r):
        visto.append(r)
        return True

    monkeypatch.setattr(interruptor, "clave_de_apagado_ausente", lector_falso)
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", True)
    install(CALMA)
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza")
    assert await evaluacion.evaluacion_permitida(redis) is True
    await evaluacion.evaluar(redis, AHORA)
    assert visto == [redis] * 4  # once for the switch and once before each of the 3 zones
    assert "GET" not in comandos(fake_upstash)  # the spy answered: evaluacion reads nothing by itself


def test_evaluacion_has_no_private_copy_of_the_kill_key_reader() -> None:
    assert not hasattr(evaluacion, "_clave_de_apagado_ausente")
    fuente = Path(evaluacion.__file__).read_text(encoding="utf-8")
    assert "read_strict" not in fuente  # the fail-closed reading lives in `interruptor.py` only


# ---------------------------------------------------------------------------
# [1] It never sends and never reads the wall clock
# ---------------------------------------------------------------------------


async def test_a_storm_in_a_subscribed_zone_sends_nothing(redis, fake_upstash, install, push_http, monkeypatch) -> None:
    async def prohibido(*args, **kwargs):
        raise AssertionError("la evaluación en seco no manda nada")

    monkeypatch.setattr(envio, "enviar", prohibido)
    monkeypatch.setattr(envio, "enviar_prueba", prohibido)
    install(TORMENTA)
    await svc.alta(redis, svc.Suscripcion("https://fcm.googleapis.com/fcm/send/real-0", P256DH, AUTH, "cordoba"))
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.con_tormenta == 1
    assert push_http.requests == []


def _modulos_importados(modulo) -> set[str]:
    arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            base = nodo.module or ""
            nombres.add(base)
            nombres.update(f"{base}.{alias.name}" for alias in nodo.names)
    return nombres


@pytest.mark.parametrize("modulo", [evaluacion, pronostico], ids=["evaluacion", "pronostico"])
def test_the_evaluation_modules_do_not_even_import_the_sender(modulo) -> None:
    importados = _modulos_importados(modulo)
    assert not any(n == "app.services.alertas.envio" or n.endswith(".envio") for n in importados), importados
    assert not any(n.split(".")[0] in {"pywebpush", "requests", "py_vapid"} for n in importados), importados
    assert not hasattr(modulo, "envio")


@pytest.mark.parametrize("modulo", [evaluacion, pronostico], ids=["evaluacion", "pronostico"])
def test_the_evaluation_modules_never_read_the_wall_clock(modulo) -> None:
    arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
    relojes = {"now", "utcnow", "today", "time", "monotonic", "perf_counter", "time_ns"}
    llamadas = [
        nodo.func.attr
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute) and nodo.func.attr in relojes
    ]
    assert llamadas == []
