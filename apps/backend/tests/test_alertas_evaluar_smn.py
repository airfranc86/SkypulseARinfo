"""POST /api/alertas/evaluar in the "SMN only" mode (FRA-359, T4, S2): `{"modo": "smn"}` in the body QStash signs.

The mode travels in the body because the QStash signature covers the body (its SHA-256 is a signed claim): a body
signed for another body, or not signed, is the same 401 as always and nothing runs. The mode is a closed list: an
unknown value is a 422 before Upstash is touched, never a silent forecast run. Without `modo` (or with
`{"modo": "pronostico"}`) the run is the forecast run exactly as before.

The SMN run (`evaluacion.evaluar_smn`) never calls Open-Meteo (a source that fails loudly proves it), reads no review
window and has no 22:00 cut (it runs 24 h: the night rule is T5), takes ITS OWN lock `alertas:lock:evaluar-smn` (never
`alertas:lock:evaluar`, so neither run keeps the other out) and answers the SMN counters plus, when it sends, the sending
counters, with a log line of its own (`alertas: smn evaluation ...`). Upstash, Open-Meteo and the SMN feed are fakes.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.upstash import UpstashRedis, configure_redis
from app.routers import alertas as router_alertas
from app.schemas.smn_alertas import SmnAlertasResponse
from app.services.alertas import avisos_smn, despacho, evaluacion, pronostico, regla
from app.services.alertas.evaluacion import ResultadoEvaluacionSmn
from app.services.smn_alertas import clave_dedupe
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name; estado_de_alertas_limpio is autouse)
    AHORA,
    AR,
    CALMA,
    CLAVE_APAGADO,
    CLAVE_LOCK,
    CLAVE_LOCK_SMN,
    CONTADORES_ENVIO_HTTP,
    CONTADORES_HTTP,
    CONTADORES_SMN_HTTP,
    CUERPO,
    CUERPO_SMN,
    NO_AUTORIZADO,
    TORMENTA,
    RedisConFalla,
    RedisSinSet,
    en_seco,
    envio_activo,
    esperas,
    estado_de_alertas_limpio,
    lineas_de_resumen,
    lineas_de_resumen_smn,
    llamar_evaluar,
    redis,
    registrar,
    reloj_de_openmeteo,
    reloj_del_bucle,
    respuestas_por_zona,
    suscribir,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.qstash_helpers import CLAVE_ACTUAL, CLAVE_AJENA, CLAVE_SIGUIENTE, firmar
from tests.test_alertas_avisos_smn import (  # noqa: F401  (`push` is a fixture)
    AMARILLO,
    ENVIADOS_AMARILLO,
    TORMENTA_SIN_FECHAS,
    alerta,
    avisos_por_zona,
    conjuntos_smn,
    push,
)

pytestmark = pytest.mark.integration

AHORA_SMN = datetime(2026, 10, 14, 13, 0, tzinfo=AR)  # 13 h in Argentina: the yellow alert of L2 is in force
MODO_DESCONOCIDO = {"detail": "modo_desconocido"}
CERO_SMN = {nombre: 0 for nombre in CONTADORES_SMN_HTTP}
CERO_ENVIO = {nombre: 0 for nombre in CONTADORES_ENVIO_HTTP}
RESPUESTA_SMN_EN_SECO = {"estado": "evaluada", **CERO_SMN, "smn_avisos": 1}
RESPUESTA_SMN_ENVIADA = {**RESPUESTA_SMN_EN_SECO, "smn_avisadas": 1, **CERO_ENVIO, "avisadas": 1, "enviados": 2}
LINEA_SMN_ENVIADA = (
    "alertas: smn evaluation estado=evaluada smn_sin_datos=0 smn_avisos=1 smn_avisadas=1 smn_ya_avisadas=0 "
    "smn_omitidas=0 smn_errores=0 avisadas=1 ya_avisadas=0 enviados=2 vencidos=0 fallidos=0 diferidos=0 reintentadas=0"
)
LINEA_SMN_EN_SECO = (
    "alertas: smn evaluation estado=evaluada smn_sin_datos=0 smn_avisos=1 smn_avisadas=0 smn_ya_avisadas=0 "
    "smn_omitidas=0 smn_errores=0"
)
# What the forecast run answers for the two zones of the 10 h review (cordoba: storm, rosario: calm). Pinned here on
# purpose: the forecast flow must stay exactly as it was.
RESPUESTA_PRONOSTICO_DOS_ZONAS = {
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


@pytest.fixture(autouse=True)
def _entorno(estado_de_alertas_limpio, own_caches, reloj_de_openmeteo, esperas):  # noqa: F811
    """A clean alerts state FIRST (both flags off), fresh caches, a frozen `fetched_at` clock and no real waiting."""
    return own_caches


@pytest.fixture
def reloj_smn(monkeypatch):
    """The router's clock pinned at 13:00 in Argentina (the alert of L2 is in force), in UTC."""
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA_SMN.astimezone(timezone.utc))


@pytest.fixture
def feed(monkeypatch) -> SimpleNamespace:
    """The SMN feed the run reads, injected through the real plumbing: `avisos_smn.evaluar_avisos_smn` is wrapped so it
    receives `feed.obtener` (the yellow alert of Córdoba by default; replace it to answer something else). `feed.llamadas`
    records every call the evaluation made (`ahora` and the keyword arguments)."""
    estado = SimpleNamespace(obtener=avisos_por_zona({"cordoba": [AMARILLO]}), llamadas=[])
    original = avisos_smn.evaluar_avisos_smn

    async def con_feed(redis_, ahora, **kwargs):
        estado.llamadas.append((ahora, kwargs))
        return await original(redis_, ahora, obtener_avisos=estado.obtener, **kwargs)

    monkeypatch.setattr(avisos_smn, "evaluar_avisos_smn", con_feed)
    return estado


@pytest.fixture
def open_meteo_prohibido(install, monkeypatch):  # noqa: F811
    """Open-Meteo, the forecast of a zone and the review window fail loudly if anything asks for them: the SMN mode
    must not even look at the forecast flow. `fuente.calls` must stay empty."""
    fuente = install(respond=lambda params: AssertionError("Open-Meteo must not be called in the SMN mode"))

    async def pronostico_prohibido(*args, **kwargs):
        raise AssertionError("pronostico_de_zona must not be called in the SMN mode")

    def ventana_prohibida(ahora):
        raise AssertionError("the review window must not be read in the SMN mode")

    def silencio_prohibido(ahora):
        raise AssertionError("the 22:00 cut must not be applied to the SMN mode")

    monkeypatch.setattr(pronostico, "pronostico_de_zona", pronostico_prohibido)
    monkeypatch.setattr(regla, "ventana", ventana_prohibida)
    monkeypatch.setattr(despacho, "segundos_hasta_el_silencio", silencio_prohibido)
    return fuente


async def llamar_smn(client: AsyncClient, cuerpo: bytes = CUERPO_SMN, firma: str | None = "auto"):
    return await llamar_evaluar(client, cuerpo, firma)


def locks(fake_upstash) -> list[str]:
    return sorted(k for k in fake_upstash.strings if k.startswith("alertas:lock:"))


def comandos_set(fake_upstash) -> list[list[str]]:
    return [c for c in fake_upstash.commands if c[0] == "SET"]


# ---------------------------------------------------------------------------
# [S2] The SMN mode: the alert in force reaches the subscribers, without Open-Meteo, with its own lock and its own line
# ---------------------------------------------------------------------------


async def test_the_smn_mode_sends_the_alert_in_force_without_open_meteo_with_its_own_lock_counters_and_log_line(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ids = await registrar(alertas_redis, "cordoba", 2)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client)

    assert response.status_code == 200
    assert response.json() == RESPUESTA_SMN_ENVIADA
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert open_meteo_prohibido.calls == []
    assert [(a, k["vapid"] is not None, k["reloj"] is not None) for a, k in feed.llamadas] == [
        (AHORA_SMN.astimezone(timezone.utc), True, True)
    ]
    # Its own lock, taken like the forecast's (SET NX EX, same expiry), and the forecast lock untouched.
    assert locks(fake_upstash) == [CLAVE_LOCK_SMN]
    valor = fake_upstash.strings[CLAVE_LOCK_SMN]
    assert comandos_set(fake_upstash) == [
        ["SET", CLAVE_LOCK_SMN, valor, "NX", "EX", str(settings.alertas_lock_ttl_segundos)]
    ]
    assert fake_upstash.ttls[CLAVE_LOCK_SMN] == settings.alertas_lock_ttl_segundos
    assert fake_upstash.commands[0] == ["GET", CLAVE_APAGADO]  # the switch first, as always
    assert fake_upstash.sets[ENVIADOS_AMARILLO] == set(ids) and conjuntos_smn(fake_upstash) == [ENVIADOS_AMARILLO]
    assert not [k for k in fake_upstash.sets if k.startswith("alertas:enviado:")]  # no forecast done-set
    # ONE line of its own, at INFO, and NOT the forecast line.
    lineas = lineas_de_resumen_smn(caplog)
    assert [(r.levelno, r.getMessage()) for r in lineas] == [(logging.INFO, LINEA_SMN_ENVIADA)]
    assert lineas_de_resumen(caplog) == []


async def test_the_dry_run_flag_counts_the_alerts_sends_nothing_and_answers_the_smn_counters_only(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, push, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await registrar(alertas_redis, "cordoba", 2)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_EN_SECO
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert open_meteo_prohibido.calls == []
    assert [k["vapid"] for _, k in feed.llamadas] == [None]  # a dry run of the SMN cross
    valor = fake_upstash.strings[CLAVE_LOCK_SMN]  # the dry run takes the lock too, like the forecast's
    assert fake_upstash.commands == [
        ["GET", CLAVE_APAGADO],
        ["SET", CLAVE_LOCK_SMN, valor, "NX", "EX", str(settings.alertas_lock_ttl_segundos)],
        ["SMEMBERS", "alertas:zonas"],
    ]
    assert [(r.levelno, r.getMessage()) for r in lineas_de_resumen_smn(caplog)] == [(logging.INFO, LINEA_SMN_EN_SECO)]


async def test_the_dry_run_flag_wins_over_the_send_flag_in_the_smn_mode_too(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, en_seco, push, feed, open_meteo_prohibido,
    reloj_smn,
) -> None:
    await registrar(alertas_redis, "cordoba", 2)
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_EN_SECO
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []


async def test_running_the_smn_mode_twice_sends_the_same_alert_once(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    await registrar(alertas_redis, "cordoba", 2)
    primera = await llamar_smn(async_client)
    limiter.reset()
    del fake_upstash.strings[CLAVE_LOCK_SMN]  # the lock expired by itself
    segunda = await llamar_smn(async_client)

    assert primera.json() == RESPUESTA_SMN_ENVIADA
    assert segunda.json() == {**RESPUESTA_SMN_EN_SECO, "smn_ya_avisadas": 1, **CERO_ENVIO, "ya_avisadas": 1}
    assert len(push.llamadas) == 2


async def test_the_smn_mode_runs_at_night_and_outside_the_review_hours(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, monkeypatch
) -> None:
    """The forecast run would be `fuera_de_ventana` at these hours; the SMN run has no window and no 22:00 cut (the
    night rule, from 22 to 5 h only the red alerts, is T5 and lives in `avisos_smn.se_omite_de_noche`)."""
    ids = await registrar(alertas_redis, "cordoba", 2)
    feed.obtener = avisos_por_zona({"cordoba": [TORMENTA_SIN_FECHAS]})  # in force at any hour
    hecho = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", TORMENTA_SIN_FECHAS))
    for hora in (23, 2, 5):
        limiter.reset()
        fake_upstash.strings.pop(CLAVE_LOCK_SMN, None)  # the lock expired
        fake_upstash.sets.pop(hecho, None)  # another alert, as far as the dedupe is concerned
        noche = datetime(2026, 10, 14, hora, 30, tzinfo=AR)
        monkeypatch.setattr(router_alertas, "_ahora_utc", lambda noche=noche: noche.astimezone(timezone.utc))
        response = await llamar_smn(async_client)
        assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA, hora
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids * 3)
    assert open_meteo_prohibido.calls == []


async def test_the_feed_that_cannot_be_verified_is_sin_datos_and_the_line_is_a_warning(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await registrar(alertas_redis, "cordoba", 2)
    feed.obtener = avisos_por_zona({"cordoba": [AMARILLO]}, available=False)
    response = await llamar_smn(async_client)

    assert response.status_code == 200
    assert response.json() == {"estado": "evaluada", **CERO_SMN, "smn_sin_datos": 1, **CERO_ENVIO}
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    lineas = lineas_de_resumen_smn(caplog)
    assert [r.levelno for r in lineas] == [logging.WARNING] and "smn_sin_datos=1" in lineas[0].getMessage()


async def test_the_default_feed_of_the_smn_mode_is_the_real_smn_feed_filtered_by_the_point_of_each_zone(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, open_meteo_prohibido, reloj_smn,
    monkeypatch,
) -> None:
    """Without the `feed` fixture: the run reads `smn_alertas.get_smn_alertas`, fed here from a cached CAP entry whose
    polygon surrounds Córdoba (and not Rosario). Nothing goes to the network."""
    import app.services.smn_alertas as mod

    mod.reset_cache()
    try:
        alrededor_de_cordoba = ((-31.0, -64.5), (-31.0, -63.8), (-31.8, -63.8), (-31.8, -64.5))
        entrada = mod.CapAlert(alerta=AMARILLO, status="Actual", polygons=(alrededor_de_cordoba,))
        monkeypatch.setattr(mod, "_utcnow", lambda: AHORA_SMN)
        monkeypatch.setattr(mod, "_monotonic", lambda: 1000.0)
        monkeypatch.setattr(
            mod, "_state",
            mod._FeedState(entries={"guid-1": entrada}, next_attempt_at=5000.0, last_feed_ok=1000.0, complete=True),
        )
        ids = await registrar(alertas_redis, "cordoba", 1)
        await registrar(alertas_redis, "rosario", 1)
        response = await llamar_smn(async_client)
    finally:
        mod.reset_cache()

    assert response.status_code == 200
    assert response.json() == {**RESPUESTA_SMN_ENVIADA, "enviados": 1}
    assert [c.sub_id for c in push.llamadas] == ids and {c.zona for c in push.llamadas} == {"cordoba"}
    assert open_meteo_prohibido.calls == []


# ---------------------------------------------------------------------------
# The signature covers the mode: nobody without the signing key can switch it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cuerpo_firmado", "cuerpo_enviado"),
    [(CUERPO, CUERPO_SMN), (CUERPO_SMN, CUERPO), (b'{"modo":"pronostico"}', CUERPO_SMN), (b"", CUERPO_SMN)],
    ids=["pronostico-firmado-smn-enviado", "smn-firmado-pronostico-enviado", "modo-cambiado", "vacio-firmado"],
)
async def test_a_signature_for_another_body_cannot_switch_the_mode_and_nothing_runs(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    cuerpo_firmado: bytes, cuerpo_enviado: bytes,
) -> None:
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client, cuerpo=cuerpo_enviado, firma=firmar(cuerpo_firmado))

    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == []
    assert open_meteo_prohibido.calls == [] and locks(fake_upstash) == []


@pytest.mark.parametrize("firma", [None, "", "no-es-un-jwt"], ids=["sin-cabecera", "vacia", "formato"])
async def test_without_a_valid_signature_the_smn_mode_is_the_same_401_as_always(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    firma: str | None,
) -> None:
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client, firma=firma)
    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == []


async def test_a_signature_of_a_foreign_key_cannot_run_the_smn_mode(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client, firma=firmar(CUERPO_SMN, clave=CLAVE_AJENA))
    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == []


async def test_the_next_signing_key_runs_the_smn_mode_too(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    await registrar(alertas_redis, "cordoba", 2)
    response = await llamar_smn(async_client, firma=firmar(CUERPO_SMN, clave=CLAVE_SIGUIENTE))
    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA


# ---------------------------------------------------------------------------
# The mode is a closed list: unknown = 422 before Upstash, never a silent forecast run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        b'{"modo":"SMN"}',
        b'{"modo":"smn "}',
        b'{"modo":"pron\xc3\xb3stico"}',
        b'{"modo":""}',
        b'{"modo":null}',
        b'{"modo":5}',
        b'{"modo":["smn"]}',
        b'{"modo":{"smn":true}}',
        b'{"modo":"ambos"}',
        b'{"origen":"qstash","modo":"otro"}',
    ],
    ids=["mayusculas", "espacio", "tilde", "vacio", "null", "numero", "lista", "objeto", "ambos", "con-origen"],
)
async def test_an_unknown_mode_is_a_422_and_nothing_runs(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    cuerpo: bytes, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client, cuerpo=cuerpo)

    assert response.status_code == 422 and response.json() == MODO_DESCONOCIDO
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == []
    assert open_meteo_prohibido.calls == [] and locks(fake_upstash) == []
    assert lineas_de_resumen(caplog) == [] and lineas_de_resumen_smn(caplog) == []
    assert cuerpo.decode() not in caplog.text  # the body is never logged
    assert any("modo desconocido" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


async def test_an_unknown_mode_is_a_422_even_with_both_flags_off(
    async_client: AsyncClient, alertas_redis, fake_upstash, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    """A misconfigured schedule must be visible from the first delivery, switched off or not."""
    response = await llamar_smn(async_client, cuerpo=b'{"modo":"otro"}')
    assert response.status_code == 422 and response.json() == MODO_DESCONOCIDO
    assert fake_upstash.commands == [] and push.llamadas == []


async def test_an_unknown_mode_without_a_valid_signature_is_the_401_not_the_422(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    """The mode contract is not told to whoever has no signature."""
    response = await llamar_smn(async_client, cuerpo=b'{"modo":"otro"}', firma=None)
    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert fake_upstash.commands == [] and push.llamadas == []


@pytest.mark.parametrize(
    ("cuerpo", "esperado"),
    [
        (b"", "pronostico"),
        (CUERPO, "pronostico"),
        (b'{"modo":"pronostico"}', "pronostico"),
        (b'{"modo":"smn"}', "smn"),
        (b'{"origen":"qstash","modo":"smn"}', "smn"),
        (b" \n", "pronostico"),
        (b"no-es-json", "pronostico"),
        (b"[1, 2]", "pronostico"),
        (b'"smn"', "pronostico"),
        (b"\xff\xfe", "pronostico"),
    ],
    ids=["vacio", "cuerpo-de-siempre", "pronostico", "smn", "smn-con-origen", "blanco", "texto", "lista", "texto-json", "bytes"],
)
def test_the_mode_of_a_body_is_the_forecast_unless_modo_says_smn(cuerpo: bytes, esperado: str) -> None:
    assert router_alertas.modo_pedido(cuerpo) == esperado


@pytest.mark.parametrize("cuerpo", [b'{"modo":"SMN"}', b'{"modo":null}', b'{"modo":["smn"]}', b'{"modo":"x"}'])
def test_a_modo_that_is_not_in_the_list_is_refused_by_the_parser(cuerpo: bytes) -> None:
    with pytest.raises(ValueError):
        router_alertas.modo_pedido(cuerpo)


def test_the_modes_are_exactly_two() -> None:
    assert router_alertas.MODOS == frozenset({"pronostico", "smn"})
    assert router_alertas.MODO_PRONOSTICO == "pronostico" and router_alertas.MODO_SMN == "smn"


# ---------------------------------------------------------------------------
# The forecast run is untouched: without `modo` (or with `pronostico`) everything is as before
# ---------------------------------------------------------------------------


@pytest.fixture
def reloj_pronostico(monkeypatch):
    """The router's clock at 10:30 in Argentina (the 10 h review), in UTC: the forecast tests' moment."""
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA.astimezone(timezone.utc))


@pytest.mark.parametrize(
    "cuerpo",
    [CUERPO, b'{"modo":"pronostico"}', b"", b"no-es-json", b"[1,2]", b'{"origen":"qstash","modo":"pronostico"}'],
    ids=["cuerpo-de-siempre", "pronostico", "vacio", "texto", "lista", "pronostico-con-origen"],
)
async def test_without_modo_smn_the_run_is_the_forecast_run_exactly_as_before(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, en_seco, feed, reloj_pronostico, cuerpo: bytes,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    fuente = install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    response = await llamar_evaluar(async_client, cuerpo)

    assert response.status_code == 200 and response.json() == RESPUESTA_PRONOSTICO_DOS_ZONAS
    assert len(fuente.calls) == 2  # Open-Meteo asked, as always
    assert feed.llamadas == []  # the SMN cross is not part of the forecast run
    assert locks(fake_upstash) == [CLAVE_LOCK]  # the forecast lock, never the SMN one
    assert fake_upstash.commands[0] == ["GET", CLAVE_APAGADO]
    assert [r.levelno for r in lineas_de_resumen(caplog)] == [logging.INFO]
    assert lineas_de_resumen(caplog)[0].getMessage().startswith("alertas: evaluation estado=evaluada ")
    assert lineas_de_resumen_smn(caplog) == []


async def test_an_smn_run_in_flight_does_not_keep_the_forecast_run_out(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, en_seco, feed, reloj_pronostico  # noqa: F811
) -> None:
    fuente = install(CALMA)
    suscribir(fake_upstash, "cordoba")
    fake_upstash.strings[CLAVE_LOCK_SMN] = "corrida-smn-en-vuelo"
    response = await llamar_evaluar(async_client)

    assert response.status_code == 200 and response.json()["estado"] == "evaluada"
    assert len(fuente.calls) == 1 and feed.llamadas == []
    assert locks(fake_upstash) == [CLAVE_LOCK, CLAVE_LOCK_SMN]
    assert fake_upstash.strings[CLAVE_LOCK_SMN] == "corrida-smn-en-vuelo"  # untouched


async def test_the_forecast_lock_taken_still_answers_en_curso_for_the_forecast_run(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, en_seco, feed, reloj_pronostico  # noqa: F811
) -> None:
    fuente = install(CALMA)
    suscribir(fake_upstash, "cordoba")
    fake_upstash.strings[CLAVE_LOCK] = "otra-corrida"
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "en_curso"}
    assert fuente.calls == [] and feed.llamadas == [] and locks(fake_upstash) == [CLAVE_LOCK]


async def test_the_forecast_run_with_the_flags_off_is_still_apagado_without_touching_anything(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, feed, reloj_pronostico  # noqa: F811
) -> None:
    fuente = install(CALMA)
    suscribir(fake_upstash, "cordoba")
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert fake_upstash.commands == [] and fuente.calls == [] and feed.llamadas == []


# ---------------------------------------------------------------------------
# The switch, the kill key and Upstash: the same answers as the forecast run, with a 200 so QStash does not retry
# ---------------------------------------------------------------------------


async def test_with_both_flags_off_the_smn_mode_is_apagado_and_touches_nothing(
    async_client: AsyncClient, alertas_redis, fake_upstash, push, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == [] and locks(fake_upstash) == []
    assert lineas_de_resumen_smn(caplog) == []


async def test_the_kill_key_makes_the_smn_mode_apagado_before_the_lock(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.strings[CLAVE_APAGADO] = "1"
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]] and push.llamadas == [] and feed.llamadas == []
    assert locks(fake_upstash) == []


async def test_with_upstash_down_the_smn_mode_is_apagado(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    fake_upstash.down = True
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert push.llamadas == [] and feed.llamadas == []


async def test_without_a_configured_upstash_the_smn_mode_is_apagado(
    async_client: AsyncClient, envio_activo, feed, open_meteo_prohibido, reloj_smn
) -> None:
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert feed.llamadas == []


async def test_if_upstash_fails_to_give_the_smn_lock_the_answer_is_upstash_no_disponible_and_a_200(
    async_client: AsyncClient, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    configure_redis(RedisSinSet(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "upstash_no_disponible"}
    assert push.llamadas == [] and feed.llamadas == [] and locks(fake_upstash) == []
    lineas = lineas_de_resumen_smn(caplog)
    assert len(lineas) == 1 and lineas[0].getMessage().startswith("alertas: smn evaluation estado=upstash_no_disponible ")


async def test_if_upstash_fails_listing_the_zones_after_the_lock_the_answer_is_upstash_no_disponible(
    async_client: AsyncClient, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 1)
    configure_redis(RedisConFalla("SMEMBERS"))
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "upstash_no_disponible"}
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert locks(fake_upstash) == [CLAVE_LOCK_SMN]  # the lock was taken; it expires by itself
    assert len(lineas_de_resumen_smn(caplog)) == 1


async def test_with_the_send_switch_on_but_no_usable_vapid_key_the_smn_mode_answers_sin_vapid_and_touches_nothing(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    monkeypatch, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(settings, "vapid_private_key", "")
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "sin_vapid"}  # never a 5xx: QStash would retry
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]] and locks(fake_upstash) == []
    assert feed.llamadas == [] and push.llamadas == []
    lineas = lineas_de_resumen_smn(caplog)
    assert [r.levelno for r in lineas] == [logging.WARNING] and "estado=sin_vapid" in lineas[0].getMessage()


# ---------------------------------------------------------------------------
# The lock of the SMN mode: its own, so neither run keeps the other out; two SMN runs never overlap
# ---------------------------------------------------------------------------


async def test_a_forecast_run_in_flight_does_not_keep_the_smn_mode_out(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    ids = await registrar(alertas_redis, "cordoba", 2)
    fake_upstash.strings[CLAVE_LOCK] = "pronostico-en-vuelo"
    response = await llamar_smn(async_client)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert locks(fake_upstash) == [CLAVE_LOCK, CLAVE_LOCK_SMN]
    assert fake_upstash.strings[CLAVE_LOCK] == "pronostico-en-vuelo"  # untouched


async def test_the_smn_lock_taken_answers_en_curso_without_reading_or_sending(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await registrar(alertas_redis, "cordoba", 2)
    fake_upstash.strings[CLAVE_LOCK_SMN] = "otra-corrida-smn"
    fake_upstash.ttls[CLAVE_LOCK_SMN] = 123
    fake_upstash.commands.clear()
    response = await llamar_smn(async_client)

    assert response.status_code == 200 and response.json() == {"estado": "en_curso"}
    assert push.llamadas == [] and feed.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert [c[:2] for c in fake_upstash.commands] == [["GET", CLAVE_APAGADO], ["SET", CLAVE_LOCK_SMN]]
    assert fake_upstash.strings[CLAVE_LOCK_SMN] == "otra-corrida-smn" and fake_upstash.ttls[CLAVE_LOCK_SMN] == 123
    lineas = lineas_de_resumen_smn(caplog)
    assert [r.levelno for r in lineas] == [logging.INFO]
    assert lineas[0].getMessage().startswith("alertas: smn evaluation estado=en_curso ")


async def test_a_repeated_delivery_right_after_an_smn_run_is_turned_away_by_its_lock(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    await registrar(alertas_redis, "cordoba", 2)
    primera = await llamar_smn(async_client)
    limiter.reset()
    segunda = await llamar_smn(async_client)
    assert primera.json() == RESPUESTA_SMN_ENVIADA and segunda.json() == {"estado": "en_curso"}
    assert len(push.llamadas) == 2 and len(feed.llamadas) == 1


async def test_two_smn_deliveries_at_once_send_once(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    ids = await registrar(alertas_redis, "cordoba", 2)
    push.cesiones = 5  # every send yields, so the two requests interleave
    a, b = await asyncio.gather(llamar_smn(async_client), llamar_smn(async_client))

    estados = sorted((a.json()["estado"], b.json()["estado"]))
    assert estados == ["en_curso", "evaluada"]
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)  # once each
    assert len(feed.llamadas) == 1


# ---------------------------------------------------------------------------
# `corte` maps to `estado` like the forecast's: kill key mid-run, deadline
# ---------------------------------------------------------------------------


async def test_the_kill_key_set_during_the_smn_run_answers_apagado_a_mitad_with_the_counters(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn
) -> None:
    await registrar(alertas_redis, "cordoba", 25)

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"

    push.al_llamar = apagar
    response = await llamar_smn(async_client)

    assert response.status_code == 200
    assert response.json() == {
        **RESPUESTA_SMN_ENVIADA, "estado": "apagado_a_mitad", "enviados": 10, "diferidos": 15,
    }
    assert len(push.llamadas) == 10 and len(fake_upstash.sets[ENVIADOS_AMARILLO]) == 10


async def test_a_run_that_hits_its_deadline_answers_evaluada_incompleta_and_a_warning(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    reloj_del_bucle, caplog: pytest.LogCaptureFixture,  # noqa: F811
) -> None:
    caplog.set_level(logging.DEBUG)
    await registrar(alertas_redis, "cordoba", 12)  # two batches: 10 and 2
    push.bucle = reloj_del_bucle
    push.avance = settings.alertas_plazo_corrida_segundos  # the first batch alone eats the whole deadline
    response = await llamar_smn(async_client)

    assert response.status_code == 200
    assert response.json() == {
        **RESPUESTA_SMN_ENVIADA, "estado": "evaluada_incompleta", "enviados": 10, "diferidos": 2,
    }
    assert len(push.llamadas) == 10
    lineas = lineas_de_resumen_smn(caplog)
    assert [r.levelno for r in lineas] == [logging.WARNING] and "estado=evaluada_incompleta" in lineas[0].getMessage()


@pytest.mark.parametrize(
    ("corte", "estado"),
    [
        (None, "evaluada"),
        (despacho.CORTE_PLAZO, "evaluada_incompleta"),
        (despacho.CORTE_APAGADO, "apagado_a_mitad"),
        (despacho.CORTE_ILEGIBLE, "apagado_a_mitad"),
    ],
)
async def test_the_cut_of_the_smn_run_maps_to_the_state_like_the_forecasts(
    redis, fake_upstash, envio_activo, push, monkeypatch, corte: str | None, estado: str
) -> None:
    async def corrida_cortada(redis_, ahora, **kwargs):
        return avisos_smn.ResultadoSmn(despacho.ResumenSmn(smn_avisos=1), despacho.ResumenEnvio(diferidos=3), corte)

    monkeypatch.setattr(avisos_smn, "evaluar_avisos_smn", corrida_cortada)
    resultado = await evaluacion.evaluar_smn(redis, AHORA_SMN, enviar=True)
    assert resultado.estado == estado
    assert resultado.como_respuesta() == {"estado": estado, **CERO_SMN, "smn_avisos": 1, **CERO_ENVIO, "diferidos": 3}


# ---------------------------------------------------------------------------
# The evaluator of the SMN mode on its own
# ---------------------------------------------------------------------------


async def test_a_naive_ahora_is_refused_before_the_lock_is_taken(redis, fake_upstash, push, feed) -> None:
    with pytest.raises(ValueError):
        await evaluacion.evaluar_smn(redis, AHORA_SMN.replace(tzinfo=None), enviar=True)
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == []


async def test_a_dry_run_of_the_evaluator_carries_no_sending_summary(redis, fake_upstash, push, feed) -> None:
    await registrar(redis, "cordoba", 1)
    resultado = await evaluacion.evaluar_smn(redis, AHORA_SMN)
    assert resultado == ResultadoEvaluacionSmn("evaluada", despacho.ResumenSmn(smn_avisos=1))
    assert resultado.envio is None and resultado.como_respuesta() == RESPUESTA_SMN_EN_SECO
    assert push.llamadas == []


async def test_the_evaluator_hands_the_cross_the_clock_it_was_given(redis, fake_upstash, envio_activo, push, feed) -> None:
    reloj = lambda: AHORA_SMN + timedelta(minutes=3)  # noqa: E731
    await evaluacion.evaluar_smn(redis, AHORA_SMN, enviar=True, reloj=reloj)
    assert [(a, k["reloj"]) for a, k in feed.llamadas] == [(AHORA_SMN, reloj)]


async def test_the_router_hands_the_smn_evaluator_its_clock_and_a_wall_clock_and_never_the_forecast_evaluator(
    async_client: AsyncClient, alertas_redis, envio_activo, monkeypatch
) -> None:
    recibido: dict[str, object] = {}

    async def evaluar_smn_espia(redis_, ahora, *, enviar=False, reloj=None):
        recibido["ahora"], recibido["enviar"], recibido["reloj"] = ahora, enviar, reloj
        return ResultadoEvaluacionSmn(estado="listo")

    async def prohibido(*args, **kwargs):
        raise AssertionError("the forecast evaluator must not run in the SMN mode")

    monkeypatch.setattr(evaluacion, "evaluar_smn", evaluar_smn_espia)
    monkeypatch.setattr(evaluacion, "evaluar", prohibido)
    instantes = iter([AHORA_SMN, AHORA_SMN + timedelta(minutes=7)])
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: next(instantes))
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == {"estado": "listo"}
    assert recibido["ahora"] == AHORA_SMN and recibido["ahora"].tzinfo is not None and recibido["enviar"] is True
    assert recibido["reloj"]() == AHORA_SMN + timedelta(minutes=7)


# ---------------------------------------------------------------------------
# The response and the logs: whitelists of integers, nothing sensitive
# ---------------------------------------------------------------------------


def test_the_smn_counters_of_the_response_are_an_explicit_whitelist_of_integers() -> None:
    assert despacho.CONTADORES_SMN == CONTADORES_SMN_HTTP
    assert {campo.name for campo in dataclasses.fields(despacho.ResumenSmn)} == set(CONTADORES_SMN_HTTP)
    assert {campo.name for campo in dataclasses.fields(ResultadoEvaluacionSmn)} == {"estado", "smn", "envio"}
    assert set(CONTADORES_SMN_HTTP).isdisjoint(CONTADORES_HTTP) and set(CONTADORES_SMN_HTTP).isdisjoint(
        CONTADORES_ENVIO_HTTP
    )


@pytest.mark.parametrize("estado", ["en_curso", "upstash_no_disponible", "sin_vapid", "otro"])
def test_an_smn_run_that_never_looked_at_the_zones_answers_only_its_state(estado: str) -> None:
    assert ResultadoEvaluacionSmn(estado=estado).como_respuesta() == {"estado": estado}
    assert ResultadoEvaluacionSmn(estado=estado, envio=despacho.ResumenEnvio()).como_respuesta() == {"estado": estado}


def test_the_smn_result_is_frozen() -> None:
    resultado = ResultadoEvaluacionSmn(estado="evaluada")
    with pytest.raises(dataclasses.FrozenInstanceError):
        resultado.estado = "otro"  # type: ignore[misc]


async def test_the_response_and_the_logs_of_the_smn_mode_carry_no_id_endpoint_text_key_zone_or_lock_value(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    vapid_efimera, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ids = await registrar(alertas_redis, "cordoba", 2)
    response = await llamar_smn(async_client)
    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    visible = response.text + str(dict(response.headers)) + caplog.text
    secretos = (
        *ids, "SECRETO", "fcm.googleapis.com", vapid_efimera.privada, vapid_efimera.publica, "Aviso oficial",
        "SkyPulse ·", "cordoba", "Córdoba", AMARILLO.descripcion, "alertas:smn:enviado", "alertas:lock",
        fake_upstash.strings[CLAVE_LOCK_SMN], CLAVE_ACTUAL, CLAVE_SIGUIENTE,
    )
    for secreto in secretos:
        assert secreto not in visible, secreto
    assert set(response.json()) == {"estado", *CONTADORES_SMN_HTTP, *CONTADORES_ENVIO_HTTP}


async def test_the_rate_limit_still_covers_the_smn_mode(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, feed, open_meteo_prohibido, reloj_smn
) -> None:
    estados = [(await llamar_smn(async_client)).status_code for _ in range(31)]
    assert estados[:30] == [200] * 30 and estados[30] == 429
