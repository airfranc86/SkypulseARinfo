"""The client key of the alert job (FRA-355, PR5b): `con_clave_de_cliente`, `job:alertas` and the Open-Meteo budget.

The scheduled evaluation runs under the fixed key `ALERTAS_JOB_CLIENT_KEY`, not under no key at all: with no key the
Open-Meteo budget lets every call through (neither the per-client cap nor the GLOBAL one applies). These tests pin the
helper, the key the zone queries really run under, and the budget end to end (dedicated share, global cap, 429 pause).
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from app.core import client_context
from app.core.client_context import ALERTAS_JOB_CLIENT_KEY, current_client_key, reset_client_key, set_client_key
from app.core.config import settings
from app.core.rate_limit_pause import openmeteo_pause
from app.core.upstash import UpstashRedis
from app.services.alertas import evaluacion
from app.services.alertas.evaluacion import ResultadoEvaluacion
from app.services.alertas.zonas import ZONAS, zona_por_slug
from app.services.openmeteo_budget import budget_refusals
from app.services.openmeteo_source import set_source
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    AHORA,
    CALMA,
    CLAVE_LOCK,
    FuenteQueSeCuelga,
    RedisEnMemoria,
    comandos,
    lineas_de_resumen,
    open_meteo_real,
    redis,
    reloj_de_openmeteo,
    suscribir,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo, monkeypatch):  # noqa: F811
    """Fresh caches and a frozen `fetched_at` clock (the data is as fresh as AHORA) for every test of this file."""
    return own_caches


# ---------------------------------------------------------------------------
# PR5b: la clave de cliente del trabajo (`con_clave_de_cliente`)
# ---------------------------------------------------------------------------


def test_the_job_key_helper_sets_the_key_and_restores_the_previous_one() -> None:
    token = set_client_key("203.0.113.9")
    try:
        with client_context.con_clave_de_cliente("job:alertas"):
            assert current_client_key() == "job:alertas"
        assert current_client_key() == "203.0.113.9"
    finally:
        reset_client_key(token)
    with client_context.con_clave_de_cliente("job:otra"):
        assert current_client_key() == "job:otra"
    assert current_client_key() is None


def test_the_job_key_helper_restores_the_key_after_an_error() -> None:
    token = set_client_key("203.0.113.9")
    try:
        with pytest.raises(RuntimeError):
            with client_context.con_clave_de_cliente("job:alertas"):
                raise RuntimeError("falla del evaluador")
        assert current_client_key() == "203.0.113.9"
    finally:
        reset_client_key(token)


def test_the_job_key_helpers_nest() -> None:
    with client_context.con_clave_de_cliente("job:alertas"):
        with client_context.con_clave_de_cliente("job:interna"):
            assert current_client_key() == "job:interna"
        assert current_client_key() == "job:alertas"
        with client_context.sin_clave_de_cliente():
            assert current_client_key() is None
        assert current_client_key() == "job:alertas"


@pytest.mark.parametrize("clave", [None, "", 123, b"job"], ids=["none", "vacia", "entero", "bytes"])
def test_the_job_key_helper_refuses_a_key_that_would_switch_the_budget_off(clave) -> None:
    # `None` means "not a client request": the Open-Meteo budget does not cap it. A job must never get there by accident.
    with pytest.raises(ValueError):
        with client_context.con_clave_de_cliente(clave):
            pass
    assert current_client_key() is None


def test_the_job_key_constant_is_the_documented_one() -> None:
    assert ALERTAS_JOB_CLIENT_KEY == "job:alertas"


# ---------------------------------------------------------------------------
# [6] The fixed job client key and the Open-Meteo budget
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clave_previa", [None, "203.0.113.9"], ids=["sin-clave", "clave-de-una-ip"])
async def test_the_zone_queries_run_under_the_job_key_and_the_callers_key_comes_back(
    redis, fake_upstash, install, clave_previa
) -> None:
    vistas: list[str | None] = []

    def respond(params):
        vistas.append(current_client_key())
        return CALMA

    install(respond=respond)
    suscribir(fake_upstash, "cordoba", "rosario")
    token = set_client_key(clave_previa)
    try:
        await evaluacion.evaluar(redis, AHORA)
        assert vistas == ["job:alertas", "job:alertas"]
        assert current_client_key() == clave_previa  # restored
    finally:
        reset_client_key(token)


async def test_the_key_is_restored_even_when_the_run_fails(redis, fake_upstash) -> None:
    class _Rota(UpstashRedis):
        async def scard(self, key: str) -> int:
            raise RuntimeError("bug")

    suscribir(fake_upstash, "cordoba")
    token = set_client_key("203.0.113.9")
    try:
        with pytest.raises(RuntimeError):
            await evaluacion.evaluar(_Rota(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN), AHORA)
        assert current_client_key() == "203.0.113.9"
    finally:
        reset_client_key(token)


async def test_the_global_open_meteo_cap_still_applies_to_the_job(
    open_meteo_real, openmeteo_budget_clock, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_minute", 3)
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 12)
    cinco = ("cordoba", "rosario", "mendoza", "salta", "tucuman")
    resultado = await evaluacion.evaluar(RedisEnMemoria(*cinco), AHORA)
    assert open_meteo_real.call_count == 3  # the 4th and 5th were refused before reaching the network
    assert resultado.evaluadas == 5 and resultado.sin_tormenta == 3 and resultado.sin_datos == 2
    assert budget_refusals()["global"] == 2


async def test_the_job_gets_a_share_big_enough_for_the_default_number_of_zones(
    open_meteo_real, openmeteo_budget_clock
) -> None:
    todas = tuple(z.slug for z in ZONAS)
    resultado = await evaluacion.evaluar(RedisEnMemoria(*todas), AHORA)
    assert resultado.evaluadas == 50 and resultado.sin_datos == 0  # 50 calls fit in the dedicated share (50)
    assert open_meteo_real.call_count == 50
    assert budget_refusals() == {"client": 0, "global": 0}


async def test_with_a_low_global_cap_only_the_global_bucket_refuses_never_the_dedicated_share(
    open_meteo_real, openmeteo_budget_clock, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_minute", 40)  # OPENMETEO_CALLS_PER_MINUTE=40 with 50 zones
    todas = tuple(z.slug for z in ZONAS)
    resultado = await evaluacion.evaluar(RedisEnMemoria(*todas), AHORA)
    assert open_meteo_real.call_count == 40
    assert resultado.evaluadas == 50 and resultado.sin_tormenta == 40 and resultado.sin_datos == 10
    assert budget_refusals() == {"client": 0, "global": 10}  # none of the 10 was refused by the DEDICATED share


async def test_with_a_tiny_per_client_cap_the_job_share_still_covers_every_zone(
    open_meteo_real, openmeteo_budget_clock, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "openmeteo_calls_per_client_per_minute", 1)
    monkeypatch.setattr(settings, "openmeteo_calls_per_minute", 200)
    resultado = await evaluacion.evaluar(RedisEnMemoria(*(z.slug for z in ZONAS)), AHORA)
    assert resultado.sin_datos == 0 and budget_refusals() == {"client": 0, "global": 0}


async def test_with_the_429_pause_open_no_zone_goes_out_to_the_network(
    open_meteo_real, openmeteo_budget_clock
) -> None:
    openmeteo_pause.trip(None)
    resultado = await evaluacion.evaluar(RedisEnMemoria("cordoba", "rosario"), AHORA)
    assert open_meteo_real.call_count == 0
    assert resultado.sin_datos == 2 and resultado.sin_tormenta == 0 and resultado.con_tormenta == 0


# ---------------------------------------------------------------------------
# [9] The run deadline
# ---------------------------------------------------------------------------


async def test_the_deadline_ends_the_run_and_the_zones_not_reached_are_diferidas_not_sin_datos(
    redis, fake_upstash, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 0.2)
    fuente = FuenteQueSeCuelga({"mendoza": CALMA}, cuelgan={"tucuman"})
    set_source(fuente)
    suscribir(fake_upstash, "mendoza", "tucuman", "salta")  # catalog order: mendoza, tucuman (hangs), salta
    resultado = await asyncio.wait_for(evaluacion.evaluar(redis, AHORA), timeout=10)
    assert resultado == ResultadoEvaluacion(
        estado="evaluada_incompleta", zonas_con_suscriptores=3, evaluadas=1, sin_tormenta=1, diferidas=2
    )
    assert resultado.sin_datos == 0 and resultado.errores == 0
    assert [(c["latitude"]) for c in fuente.calls] == [zona_por_slug("mendoza").lat, zona_por_slug("tucuman").lat]
    assert [(z.slug, z.veredicto) for z in resultado.zonas] == [
        ("mendoza", "sin_tormenta"), ("tucuman", "diferida"), ("salta", "diferida")
    ]


async def test_the_deadline_is_its_own_setting_and_not_the_lock_expiry(redis, fake_upstash, monkeypatch) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 0.2)
    monkeypatch.setattr(settings, "alertas_lock_ttl_segundos", 3600)
    set_source(FuenteQueSeCuelga({}, cuelgan={"cordoba"}))
    suscribir(fake_upstash, "cordoba")
    resultado = await asyncio.wait_for(evaluacion.evaluar(redis, AHORA), timeout=10)  # a hung source would wait for 1 h
    assert resultado.estado == "evaluada_incompleta" and resultado.diferidas == 1


async def test_after_the_deadline_the_lock_is_still_left_to_expire_and_the_client_key_comes_back(
    redis, fake_upstash, monkeypatch
) -> None:
    from app.core.client_context import current_client_key

    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 0.2)
    set_source(FuenteQueSeCuelga({}, cuelgan={"cordoba"}))
    suscribir(fake_upstash, "cordoba")
    await asyncio.wait_for(evaluacion.evaluar(redis, AHORA), timeout=10)
    assert CLAVE_LOCK in fake_upstash.strings and "DEL" not in comandos(fake_upstash)
    assert current_client_key() is None


async def test_the_deadline_diferidas_add_up_to_the_ones_over_the_cap(redis, fake_upstash, monkeypatch) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 0.2)
    monkeypatch.setattr(settings, "alertas_max_zonas_por_corrida", 3)
    set_source(FuenteQueSeCuelga({"cordoba": CALMA}, cuelgan={"rosario"}))
    suscribir(fake_upstash, "cordoba", "rosario", "mendoza", "salta", "tucuman")  # 5 zones, cap 3
    resultado = await asyncio.wait_for(evaluacion.evaluar(redis, AHORA), timeout=10)
    # cordoba done; rosario hangs (deferred), mendoza not reached (deferred), salta and tucuman over the cap
    assert (resultado.evaluadas, resultado.diferidas, resultado.zonas_con_suscriptores) == (1, 4, 5)
    assert resultado.estado == "evaluada_incompleta"


async def test_a_run_that_finishes_inside_the_deadline_is_a_plain_evaluada(redis, fake_upstash, install) -> None:
    install(CALMA)
    suscribir(fake_upstash, "cordoba")
    assert (await evaluacion.evaluar(redis, AHORA)).estado == "evaluada"


async def test_a_deadline_logs_a_warning_with_the_counters(
    redis, fake_upstash, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 0.2)
    set_source(FuenteQueSeCuelga({}, cuelgan={"cordoba"}))
    suscribir(fake_upstash, "cordoba")
    await asyncio.wait_for(evaluacion.evaluar(redis, AHORA), timeout=10)
    lineas = lineas_de_resumen(caplog)
    assert [r.levelno for r in lineas] == [logging.WARNING]
    assert "estado=evaluada_incompleta" in lineas[0].getMessage() and "diferidas=1" in lineas[0].getMessage()
