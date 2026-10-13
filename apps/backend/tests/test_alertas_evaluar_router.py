"""POST /api/alertas/evaluar with the real evaluation (FRA-355, PR5b), through the router.

The modes (both flags off = `apagado` without touching Upstash or Open-Meteo; either flag = evaluate; neither ever sends),
the kill key, the states of a run (`fuera_de_ventana`, `en_curso`, `upstash_no_disponible`, ...), the response whitelist
and what must never leave the process (ids, endpoints, keys, the lock value), plus the switch (`evaluacion_permitida`)
and the settings and `render.yaml` entries that gate it. Upstash and Open-Meteo are fakes: there is no network.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import respx
from httpx import AsyncClient, Response

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.upstash import UpstashRedis, configure_redis
from app.routers import alertas as router_alertas
from app.services.alertas import envio, evaluacion, regla
from app.services.alertas import suscripcion as svc
from app.services.alertas.evaluacion import ResultadoEvaluacion, ZonaEvaluada
from app.services.alertas.zonas import ZONAS
from app.services.openmeteo_source import set_source
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name; estado_de_alertas_limpio is autouse)
    AHORA,
    AR,
    CALMA,
    CLAVE_APAGADO,
    CLAVE_LOCK,
    CONTADORES_HTTP,
    TORMENTA,
    FuenteQueSeCuelga,
    RedisSinSet,
    en_seco,
    estado_de_alertas_limpio,
    llamar_evaluar,
    lineas_de_resumen,
    payload_horario,
    redis,
    reloj_de_openmeteo,
    respuestas_por_zona,
    suscribir,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.qstash_helpers import CLAVE_ACTUAL, CLAVE_SIGUIENTE
from tests.test_alertas_suscripcion import AUTH, P256DH

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo):  # noqa: F811
    """Fresh caches with a recording backend and a frozen `fetched_at` clock (the data is as fresh as AHORA)."""
    return own_caches


# ---------------------------------------------------------------------------
# PR5b: el router con la evaluación de verdad
# ---------------------------------------------------------------------------



@pytest.fixture
def reloj_del_router(monkeypatch):
    """El reloj del router clavado en AHORA (10:30 en Argentina, la revisión de las 10 h), en UTC."""
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA.astimezone(timezone.utc))


@pytest.fixture
def evaluacion_real(reloj_del_router, reloj_de_openmeteo, own_caches):  # noqa: F811
    """Todo lo que la evaluación de verdad necesita para correr sin red y sin depender del reloj de pared."""


RESPUESTA_DOS_ZONAS = {
    "estado": "evaluada",
    "zonas_con_suscriptores": 2,
    "evaluadas": 2,
    "con_tormenta": 1,
    "sin_tormenta": 1,
    "sin_datos": 0,
    "errores": 0,
    "diferidas": 0,
    "desconocidas": 0,
}


async def test_with_both_flags_off_nothing_is_touched_not_even_open_meteo(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real
) -> None:
    fuente = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert fake_upstash.commands == []
    assert fuente.calls == []


@pytest.mark.parametrize(
    ("con_envio", "con_seco"),
    [(False, True), (True, False), (True, True)],
    ids=["solo-en-seco", "solo-envio", "ambos"],
)
async def test_either_flag_turns_the_evaluation_on_and_neither_ever_sends(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, push_http, monkeypatch,
    con_envio: bool, con_seco: bool,
) -> None:
    monkeypatch.setattr(settings, "alertas_envio_activo", con_envio)
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", con_seco)

    async def prohibido(*args, **kwargs):
        raise AssertionError("la evaluación de la PR5b no manda nada")

    monkeypatch.setattr(envio, "enviar", prohibido)
    monkeypatch.setattr(envio, "enviar_prueba", prohibido)
    fuente = install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == RESPUESTA_DOS_ZONAS
    assert fake_upstash.commands[0] == ["GET", CLAVE_APAGADO]
    assert len(fuente.calls) == 2
    assert push_http.requests == []


async def test_the_dry_run_flag_alone_still_obeys_the_kill_key(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco
) -> None:
    fuente = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    fake_upstash.strings[CLAVE_APAGADO] = "1"
    response = await llamar_evaluar(async_client)
    assert response.json() == {"estado": "apagado"}
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]]
    assert fuente.calls == []


async def test_the_dry_run_flag_alone_with_upstash_down_is_apagado(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco
) -> None:
    fuente = install(TORMENTA)
    fake_upstash.down = True
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert fuente.calls == []


async def test_the_dry_run_flag_alone_without_a_configured_upstash_is_apagado(
    async_client: AsyncClient, install, evaluacion_real, en_seco
) -> None:
    fuente = install(TORMENTA)
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert fuente.calls == []


@pytest.mark.parametrize(
    ("respuesta", "estado"),
    [({}, "apagado"), ({"error": "x"}, "apagado"), ({"result": 5}, "apagado"), ({"result": "1"}, "apagado")],
    ids=["vacio", "error", "entero", "texto"],
)
async def test_the_dry_run_fails_closed_on_an_unusable_kill_key_answer(
    async_client: AsyncClient, install, evaluacion_real, en_seco, respuesta: dict, estado: str
) -> None:
    fuente = install(TORMENTA)
    configure_redis(UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(return_value=Response(200, json=respuesta))
        response = await llamar_evaluar(async_client)
    assert response.json() == {"estado": estado}
    assert fuente.calls == []


async def test_outside_the_review_hours_the_answer_says_so_and_nothing_else_happens(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco, monkeypatch
) -> None:
    from datetime import datetime

    fuera = datetime(2026, 10, 14, 22, 30, tzinfo=AHORA.tzinfo).astimezone(timezone.utc)
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: fuera)
    fuente = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "fuera_de_ventana"}
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]]  # not even the lock
    assert fuente.calls == []


async def test_a_run_that_finds_the_lock_taken_answers_en_curso_without_evaluating(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco
) -> None:
    fuente = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    fake_upstash.strings[CLAVE_LOCK] = "otra-corrida"
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "en_curso"}
    assert fuente.calls == []


async def test_a_repeated_delivery_right_after_a_run_is_turned_away_by_the_lock(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco
) -> None:
    fuente = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    primera = await llamar_evaluar(async_client)
    limiter.reset()
    segunda = await llamar_evaluar(async_client)
    assert primera.json()["estado"] == "evaluada" and segunda.json() == {"estado": "en_curso"}
    assert len(fuente.calls) == 1
    assert fake_upstash.ttls[CLAVE_LOCK] == settings.alertas_lock_ttl_segundos


async def test_if_upstash_fails_to_give_the_lock_the_answer_is_still_a_200(
    async_client: AsyncClient, fake_upstash, install, evaluacion_real, en_seco
) -> None:
    fuente = install(TORMENTA)
    suscribir(fake_upstash, "cordoba")
    configure_redis(RedisSinSet(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200  # a 5xx would make QStash retry
    assert response.json() == {"estado": "upstash_no_disponible"}
    assert fuente.calls == []


async def test_the_evaluator_receives_the_routers_clock_with_a_time_zone(
    async_client: AsyncClient, alertas_redis, reloj_del_router, en_seco, monkeypatch
) -> None:
    recibido: dict[str, object] = {}

    async def evaluar_espia(redis, ahora):
        recibido["ahora"] = ahora
        return evaluacion.ResultadoEvaluacion(estado="listo")

    monkeypatch.setattr(evaluacion, "evaluar", evaluar_espia)
    await llamar_evaluar(async_client)
    assert recibido["ahora"] == AHORA and recibido["ahora"].tzinfo is not None


def test_the_routers_real_clock_is_an_aware_utc_now() -> None:
    from datetime import datetime

    antes = datetime.now(timezone.utc)
    ahora = router_alertas._ahora_utc()
    despues = datetime.now(timezone.utc)
    assert ahora.tzinfo is not None and ahora.utcoffset().total_seconds() == 0
    assert antes <= ahora <= despues


async def test_the_response_and_the_logs_carry_no_id_endpoint_key_or_lock_value(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    install(TORMENTA)
    ids, endpoints = [], []
    for i in range(2):
        endpoint = f"https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-{i}"
        endpoints.append(endpoint)
        ids.append(await svc.alta(alertas_redis, svc.Suscripcion(endpoint, P256DH, AUTH, "cordoba")))
    response = await llamar_evaluar(async_client)
    assert response.json()["estado"] == "evaluada"
    visible = response.text + str(dict(response.headers)) + caplog.text
    for secreto in (
        *ids, *endpoints, P256DH, AUTH, fake_upstash.strings[CLAVE_LOCK], "SECRETO", CLAVE_ACTUAL, CLAVE_SIGUIENTE,
    ):
        assert secreto not in visible
    assert set(response.json()) == set(RESPUESTA_DOS_ZONAS)


async def test_the_per_zone_detail_never_reaches_the_http_response_nor_the_logs(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": payload_horario()}))
    suscribir(fake_upstash, "cordoba", "rosario")
    fake_upstash.sets["alertas:zonas"].add("salta")  # a listed zone with no subscribers
    response = await llamar_evaluar(async_client)
    assert response.json() == RESPUESTA_DOS_ZONAS  # exactly the whitelist, nothing else
    visible = response.text + str(dict(response.headers)) + caplog.text
    for dato in ("cordoba", "rosario", "salta", "2026-10-14", "15:00", "hoy", "manana", "sin_suscriptores"):
        assert dato not in visible


async def test_a_run_that_hits_its_deadline_still_answers_a_200_with_the_incomplete_state_and_counters(
    async_client: AsyncClient, alertas_redis, fake_upstash, evaluacion_real, en_seco, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 0.2)
    set_source(FuenteQueSeCuelga({"mendoza": payload_horario()}, cuelgan={"tucuman"}))
    suscribir(fake_upstash, "mendoza", "tucuman", "salta")
    response = await asyncio.wait_for(llamar_evaluar(async_client), timeout=10)
    assert response.status_code == 200
    assert response.json() == {
        **RESPUESTA_DOS_ZONAS,
        "estado": "evaluada_incompleta",
        "zonas_con_suscriptores": 3,
        "evaluadas": 1,
        "con_tormenta": 0,
        "sin_tormenta": 1,
        "diferidas": 2,
    }


async def test_a_bug_in_one_zone_is_counted_as_an_error_and_the_answer_is_still_a_200(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, evaluacion_real, en_seco
) -> None:
    install(respond=respuestas_por_zona({"cordoba": RuntimeError("bug"), "rosario": TORMENTA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200
    assert response.json() == {**RESPUESTA_DOS_ZONAS, "errores": 1, "sin_tormenta": 0}


async def test_the_rate_limit_still_covers_the_evaluation_path(
    async_client: AsyncClient, alertas_redis, install, evaluacion_real, en_seco
) -> None:
    install(CALMA)
    estados = [(await llamar_evaluar(async_client)).status_code for _ in range(31)]
    assert estados[:30] == [200] * 30 and estados[30] == 429


# ---------------------------------------------------------------------------
# The switch used by the router (flags + kill key)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("envio_activo", "en_seco"), [(True, False), (False, True), (True, True)])
async def test_the_evaluation_is_allowed_with_either_flag_and_no_kill_key(
    redis, fake_upstash, monkeypatch, envio_activo: bool, en_seco: bool
) -> None:
    monkeypatch.setattr(settings, "alertas_envio_activo", envio_activo)
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", en_seco)
    assert await evaluacion.evaluacion_permitida(redis) is True
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]]


async def test_with_both_flags_off_it_is_not_allowed_and_upstash_is_not_touched(
    redis, fake_upstash, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alertas_envio_activo", False)
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", False)
    assert await evaluacion.evaluacion_permitida(redis) is False
    assert fake_upstash.commands == []


@pytest.mark.parametrize("valor", ["1", "", "0", "false"])
async def test_the_kill_key_denies_whatever_its_value(redis, fake_upstash, monkeypatch, valor: str) -> None:
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", True)
    fake_upstash.strings[CLAVE_APAGADO] = valor
    assert await evaluacion.evaluacion_permitida(redis) is False


async def test_without_upstash_or_with_it_down_it_is_not_allowed(redis, fake_upstash, monkeypatch) -> None:
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", True)
    assert await evaluacion.evaluacion_permitida(None) is False
    fake_upstash.down = True
    assert await evaluacion.evaluacion_permitida(redis) is False


# ---------------------------------------------------------------------------
# Settings and deployment
# ---------------------------------------------------------------------------


def _ajustes_sin_entorno(monkeypatch, **variables: str):
    """A fresh `Settings` read from a clean environment plus `variables` (names in lower case)."""
    for variable in (
        "ALERTAS_EVALUAR_EN_SECO",
        "ALERTAS_MAX_ZONAS_POR_CORRIDA",
        "ALERTAS_LOCK_TTL_SEGUNDOS",
        "ALERTAS_PLAZO_CORRIDA_SEGUNDOS",
    ):
        monkeypatch.delenv(variable, raising=False)
    for nombre, valor in variables.items():
        monkeypatch.setenv(nombre.upper(), valor)
    return type(settings)(_env_file=None)


def test_the_new_settings_default_to_off_the_whole_catalog_and_a_lock_that_outlasts_the_signature(monkeypatch) -> None:
    fresco = _ajustes_sin_entorno(monkeypatch)
    assert fresco.alertas_evaluar_en_seco is False
    assert fresco.alertas_max_zonas_por_corrida == 50 == len(ZONAS)
    assert fresco.alertas_lock_ttl_segundos == 600  # a QStash signature lives ~5 minutes: the lock must outlast it
    assert fresco.alertas_plazo_corrida_segundos == 480
    assert fresco.alertas_plazo_corrida_segundos < fresco.alertas_lock_ttl_segundos


def test_the_new_settings_read_their_environment_variables(monkeypatch) -> None:
    leido = _ajustes_sin_entorno(
        monkeypatch,
        alertas_evaluar_en_seco="true",
        alertas_max_zonas_por_corrida="7",
        alertas_lock_ttl_segundos="700",
        alertas_plazo_corrida_segundos="90",
    )
    assert leido.alertas_evaluar_en_seco is True
    assert leido.alertas_max_zonas_por_corrida == 7
    assert leido.alertas_lock_ttl_segundos == 700
    assert leido.alertas_plazo_corrida_segundos == 90


@pytest.mark.parametrize(
    ("variable", "valor"),
    [
        ("ALERTAS_MAX_ZONAS_POR_CORRIDA", "0"),
        ("ALERTAS_MAX_ZONAS_POR_CORRIDA", "-1"),
        ("ALERTAS_MAX_ZONAS_POR_CORRIDA", "51"),  # more than the catalog has
        ("ALERTAS_LOCK_TTL_SEGUNDOS", "0"),
        ("ALERTAS_LOCK_TTL_SEGUNDOS", "329"),  # shorter than the signature plus a margin
        ("ALERTAS_LOCK_TTL_SEGUNDOS", "3601"),
        ("ALERTAS_PLAZO_CORRIDA_SEGUNDOS", "59"),
        ("ALERTAS_PLAZO_CORRIDA_SEGUNDOS", "0"),
    ],
)
def test_the_size_settings_reject_values_that_would_break_the_run(monkeypatch, variable: str, valor: str) -> None:
    with pytest.raises(Exception, match="(?i)validation"):
        _ajustes_sin_entorno(monkeypatch, **{variable.lower(): valor})


@pytest.mark.parametrize(
    ("lock", "plazo", "valido"),
    [("600", "599", True), ("600", "600", False), ("600", "601", False), ("330", "329", True), ("330", "480", False)],
)
def test_the_deadline_must_be_below_the_lock_expiry(monkeypatch, lock: str, plazo: str, valido: bool) -> None:
    variables = {"alertas_lock_ttl_segundos": lock, "alertas_plazo_corrida_segundos": plazo}
    if valido:
        assert _ajustes_sin_entorno(monkeypatch, **variables).alertas_plazo_corrida_segundos == int(plazo)
    else:
        with pytest.raises(Exception, match="(?i)plazo"):
            _ajustes_sin_entorno(monkeypatch, **variables)


def test_the_lock_expiry_must_outlast_the_qstash_signature_on_its_own(monkeypatch) -> None:
    """With a short deadline the order check passes, so only the lower bound of the lock expiry can refuse 329."""
    corto = {"alertas_lock_ttl_segundos": "329", "alertas_plazo_corrida_segundos": "60"}
    with pytest.raises(Exception, match="(?i)validation"):
        _ajustes_sin_entorno(monkeypatch, **corto)
    justo = _ajustes_sin_entorno(monkeypatch, alertas_lock_ttl_segundos="330", alertas_plazo_corrida_segundos="60")
    assert justo.alertas_lock_ttl_segundos == 330


def test_render_declares_the_dry_run_flag_turned_off() -> None:
    texto = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")
    assert re.search(r'- key: ALERTAS_EVALUAR_EN_SECO\s*\n\s*value: "false"', texto)
    assert re.search(r'- key: ALERTAS_ENVIO_ACTIVO\s*\n\s*value: "false"', texto)  # unchanged: sending stays off


def test_the_catalog_order_that_breaks_ties_between_zones_starts_with_the_biggest_cities() -> None:
    assert [z.slug for z in ZONAS][:3] == ["buenos-aires", "cordoba", "rosario"]


# ---------------------------------------------------------------------------
# [7] The result, the response and the log
# ---------------------------------------------------------------------------


def test_the_result_is_frozen_and_its_counters_default_to_zero() -> None:
    resultado = ResultadoEvaluacion(estado="evaluada")
    assert [getattr(resultado, nombre) for nombre in CONTADORES_HTTP] == [0] * len(CONTADORES_HTTP)
    assert resultado.zonas == ()
    with pytest.raises(FrozenInstanceError):
        resultado.estado = "otro"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        resultado.con_tormenta = 1  # type: ignore[misc]


def test_the_http_whitelist_is_explicit_and_every_field_of_the_result_is_accounted_for() -> None:
    """A new field of `ResultadoEvaluacion` must be added to `CONTADORES` (HTTP) or declared here as internal: it can
    never reach the response by accident."""
    assert evaluacion.CONTADORES == CONTADORES_HTTP
    campos = {campo.name for campo in dataclasses.fields(ResultadoEvaluacion)}
    assert campos == {"estado", "zonas", *CONTADORES_HTTP}


def test_the_zone_detail_is_invisible_in_the_repr_and_ignored_by_equality() -> None:
    zona = ZonaEvaluada(slug="cordoba", veredicto="sin_tormenta", suscriptores=2)
    con_detalle = ResultadoEvaluacion(estado="evaluada", evaluadas=1, sin_tormenta=1, zonas=(zona,))
    sin_detalle = ResultadoEvaluacion(estado="evaluada", evaluadas=1, sin_tormenta=1)
    assert con_detalle == sin_detalle
    assert "cordoba" not in repr(con_detalle)
    assert set(con_detalle.como_respuesta()) == {"estado", *CONTADORES_HTTP}


def test_a_zone_detail_is_frozen() -> None:
    zona = ZonaEvaluada(slug="cordoba", veredicto="sin_tormenta", suscriptores=2)
    with pytest.raises(FrozenInstanceError):
        zona.veredicto = "con_tormenta"  # type: ignore[misc]
    assert (zona.revision, zona.aviso, zona.fecha_objetivo, zona.ventana) == (None, None, None, None)


async def test_the_response_carries_the_state_and_the_integer_counters_only(redis, fake_upstash, install) -> None:
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario", cantidad=2)
    respuesta = (await evaluacion.evaluar(redis, AHORA)).como_respuesta()
    assert set(respuesta) == {"estado", *CONTADORES_HTTP}
    assert respuesta["estado"] == "evaluada"
    assert all(type(respuesta[nombre]) is int for nombre in CONTADORES_HTTP)
    assert respuesta["zonas_con_suscriptores"] == 2 and respuesta["con_tormenta"] == 1  # zones, not subscribers


@pytest.mark.parametrize("estado", ["en_curso", "fuera_de_ventana", "upstash_no_disponible", "otro"])
def test_a_run_that_never_looked_at_the_zones_answers_only_its_state(estado: str) -> None:
    assert ResultadoEvaluacion(estado=estado).como_respuesta() == {"estado": estado}


def test_an_incomplete_run_reports_its_counters_too() -> None:
    respuesta = ResultadoEvaluacion(estado="evaluada_incompleta", zonas_con_suscriptores=3, diferidas=2).como_respuesta()
    assert set(respuesta) == {"estado", *CONTADORES_HTTP} and respuesta["diferidas"] == 2


def test_a_run_stopped_by_the_kill_key_still_reports_what_it_counted() -> None:
    respuesta = ResultadoEvaluacion(estado="apagado_a_mitad", zonas_con_suscriptores=3, evaluadas=1).como_respuesta()
    assert respuesta["estado"] == "apagado_a_mitad" and respuesta["evaluadas"] == 1


async def test_no_id_endpoint_key_or_lock_value_leaves_the_evaluator(
    redis, fake_upstash, install, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    ids, endpoints = [], []
    for i, zona in enumerate(("cordoba", "cordoba", "rosario")):
        endpoint = f"https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-{i}"
        endpoints.append(endpoint)
        ids.append(await svc.alta(redis, svc.Suscripcion(endpoint, P256DH, AUTH, zona)))
    resultado = await evaluacion.evaluar(redis, AHORA)
    visible = json.dumps(resultado.como_respuesta()) + repr(resultado) + caplog.text
    valor_del_lock = fake_upstash.strings[CLAVE_LOCK]
    for secreto in (*ids, *endpoints, P256DH, AUTH, valor_del_lock, "SECRETO", "fcm.googleapis.com"):
        assert secreto not in visible


async def test_one_info_line_with_the_counters_per_run_when_all_went_well(
    redis, fake_upstash, install, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    await evaluacion.evaluar(redis, AHORA)
    lineas = lineas_de_resumen(caplog)
    assert [r.levelno for r in lineas] == [logging.INFO]
    mensaje = lineas[0].getMessage()
    for fragmento in (
        "estado=evaluada",
        "zonas_con_suscriptores=2",
        "evaluadas=2",
        "con_tormenta=1",
        "sin_tormenta=1",
        "sin_datos=0",
        "errores=0",
        "diferidas=0",
        "desconocidas=0",
    ):
        assert fragmento in mensaje
    assert "cordoba" not in mensaje and "ID-SECRETO" not in mensaje


@pytest.mark.parametrize(
    ("respuestas", "fragmento"),
    [
        ({"cordoba": None, "rosario": CALMA}, "sin_datos=1"),
        ({"cordoba": RuntimeError("bug"), "rosario": CALMA}, "errores=1"),
    ],
    ids=["sin-datos", "errores"],
)
async def test_the_summary_is_a_warning_when_a_zone_had_no_data_or_failed(
    redis, fake_upstash, install, caplog: pytest.LogCaptureFixture, respuestas, fragmento: str
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona(respuestas))
    suscribir(fake_upstash, "cordoba", "rosario")
    await evaluacion.evaluar(redis, AHORA)
    lineas = lineas_de_resumen(caplog)
    assert [r.levelno for r in lineas] == [logging.WARNING]
    assert fragmento in lineas[0].getMessage()


@pytest.mark.parametrize("hora", [3, 22])
async def test_a_run_that_does_not_evaluate_also_logs_its_state_once(
    redis, fake_upstash, install, caplog: pytest.LogCaptureFixture, hora: int
) -> None:
    caplog.set_level(logging.DEBUG)
    install(CALMA)
    await evaluacion.evaluar(redis, datetime(2026, 10, 14, hora, 0, tzinfo=AR))
    lineas = [r.getMessage() for r in caplog.records if r.name == evaluacion.logger.name and r.levelno == logging.INFO]
    assert len(lineas) == 1 and "estado=fuera_de_ventana" in lineas[0]


# ---------------------------------------------------------------------------
# [7b] The per-zone detail for the caller (never for the response or the logs)
# ---------------------------------------------------------------------------


async def test_the_result_lists_every_known_zone_with_its_verdict_and_its_subscriber_count(
    redis, fake_upstash, install, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "alertas_max_zonas_por_corrida", 3)
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA, "mendoza": None}))
    suscribir(fake_upstash, "mendoza", cantidad=3)
    suscribir(fake_upstash, "cordoba", cantidad=2)
    suscribir(fake_upstash, "rosario", "tucuman")  # one subscriber each
    fake_upstash.sets["alertas:zonas"].update({"salta", "ciudad-que-no-existe"})  # salta: listed but empty
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert [(z.slug, z.veredicto, z.suscriptores) for z in resultado.zonas] == [
        ("mendoza", "sin_datos", 3),
        ("cordoba", "con_tormenta", 2),
        ("rosario", "sin_tormenta", 1),
        ("tucuman", "diferida", 1),  # over the cap
        ("salta", "sin_suscriptores", 0),  # so that the caller can prune `alertas:zonas`
    ]  # the unknown slug is not a zone: it is only counted
    assert resultado.desconocidas == 1


async def test_a_storm_zone_carries_the_rule_result_the_kind_of_notice_and_the_target_date(
    redis, fake_upstash, install
) -> None:
    install(respond=respuestas_por_zona({"cordoba": payload_horario(codigos={15: 96}, cape={16: 3100.0})}))
    suscribir(fake_upstash, "cordoba", "rosario")
    resultado = await evaluacion.evaluar(redis, AHORA)
    cordoba = next(z for z in resultado.zonas if z.slug == "cordoba")
    assert cordoba.veredicto == "con_tormenta"
    assert cordoba.revision is not None and cordoba.revision.hay_tormenta
    assert [(h.hora, h.motivo) for h in cordoba.revision.horas] == [("15:00", "codigo"), ("16:00", "cape")]
    assert cordoba.aviso == "hoy"
    assert cordoba.fecha_objetivo == date(2026, 10, 14)
    assert cordoba.ventana == regla.ventana(AHORA)
    rosario = next(z for z in resultado.zonas if z.slug == "rosario")  # not a storm: nothing about a notice
    assert (rosario.veredicto, rosario.revision, rosario.aviso, rosario.fecha_objetivo, rosario.ventana) == (
        "sin_datos", None, None, None, None
    )


async def test_the_21_h_review_is_a_notice_for_tomorrow_with_tomorrows_date(
    redis, fake_upstash, install, reloj_de_openmeteo
) -> None:
    ahora = datetime(2026, 10, 14, 21, 5, tzinfo=AR)
    reloj_de_openmeteo.instante = ahora
    install(payload_horario(codigos={24 + 15: 95}))
    suscribir(fake_upstash, "cordoba")
    zona = (await evaluacion.evaluar(redis, ahora)).zonas[0]
    assert (zona.veredicto, zona.aviso, zona.fecha_objetivo) == ("con_tormenta", "manana", date(2026, 10, 15))


async def test_the_zone_detail_never_reaches_the_response_nor_the_logs(
    redis, fake_upstash, install, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario", cantidad=2)
    resultado = await evaluacion.evaluar(redis, AHORA)
    assert resultado.zonas  # the detail exists ...
    visible = json.dumps(resultado.como_respuesta()) + repr(resultado) + caplog.text
    for dato in ("cordoba", "rosario", "2026-10-14", "15:00", "hoy", "manana", "sin_suscriptores", "ID-SECRETO"):
        assert dato not in visible  # ... and none of it is serialized or logged
    assert set(resultado.como_respuesta()) == {"estado", *CONTADORES_HTTP}
