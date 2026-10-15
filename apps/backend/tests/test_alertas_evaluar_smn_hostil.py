"""FRA-359 T4, hostile and cross-run cases of the "SMN only" mode of POST /api/alertas/evaluar.

They do not duplicate `tests/test_alertas_evaluar_smn.py`: they attack the parser of
the mode with hostile bodies, the order of the checks (signature before mode) with INVALID signatures, the body size
boundary, the two runs at the same time, the lock TTL as a setting, the Upstash cost through HTTP and the night rule.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.core.client_context import ALERTAS_JOB_CLIENT_KEY, current_client_key
from app.core.config import settings
from app.routers import alertas as router_alertas
from app.services.alertas import avisos_smn
from app.services.alertas.zonas import ZONAS
from tests.alertas_helpers import (  # noqa: F401
    AHORA,
    AR,
    CALMA,
    CLAVE_APAGADO,
    CLAVE_LOCK,
    CLAVE_LOCK_SMN,
    CUERPO,
    CUERPO_SMN,
    NO_AUTORIZADO,
    TORMENTA,
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
    respuestas_por_zona,
    suscribir,
)
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.qstash_helpers import CLAVE_AJENA, firmar
from tests.test_alertas_avisos_smn import AMARILLO, TORMENTA_SIN_FECHAS, alerta, avisos_por_zona, push  # noqa: F401
from tests.test_alertas_evaluar_smn import (  # noqa: F401
    AHORA_SMN,
    MODO_DESCONOCIDO,
    RESPUESTA_PRONOSTICO_DOS_ZONAS,
    RESPUESTA_SMN_ENVIADA,
    _entorno,
    feed,
    locks,
    open_meteo_prohibido,
    reloj_pronostico,
    reloj_smn,
)

pytestmark = pytest.mark.integration

ROJO = alerta(nivel="rojo", severidad="Extreme")  # the one level the night rule of T5 lets through


async def llamar(client: AsyncClient, cuerpo: bytes, firma: str | None = "auto"):
    return await llamar_evaluar(client, cuerpo, firma)


# ---------------------------------------------------------------------------
# Hostile bodies with a VALID signature (only the key holder can produce them)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        b'{"modo":true}',
        b'{"modo":false}',
        b'{"modo":0}',
        b'{"modo":"smn\\u0000"}',
        b'{"modo":"smn\\n"}',
        b'{"modo":" smn"}',
        b'{"modo":"pronostico "}',
        b'{"modo":"smn","modo":"SMN"}',  # duplicate keys: the last one wins and it is unknown
        b'{"modo":"Smn"}',
        '{"modo":"pronóstico"}'.encode("utf-8"),
    ],
    ids=["true", "false", "cero", "nul", "salto", "espacio-antes", "espacio-despues", "dup-ultimo-malo", "capital", "tilde"],
)
async def test_hostile_mode_values_are_422_and_touch_nothing(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    cuerpo: bytes,
) -> None:
    await registrar(alertas_redis, "cordoba", 1)
    fake_upstash.commands.clear()
    response = await llamar(async_client, cuerpo)
    assert response.status_code == 422 and response.json() == MODO_DESCONOCIDO
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == [] and locks(fake_upstash) == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        b'{"modo":"pronostico","modo":"smn"}',  # duplicate keys: the LAST one wins (json.loads)
        b"\xef\xbb\xbf" + CUERPO_SMN,  # UTF-8 BOM: json.loads(bytes) accepts it
        b'  \n {"modo" : "smn" , "origen":"qstash"} \n ',  # whitespace around and inside
        b'{"modo":"s\\u006dn"}',  # a JSON escape that spells "smn"
    ],
    ids=["dup-ultimo-smn", "bom", "blancos", "escape"],
)
async def test_bodies_that_decode_to_modo_smn_run_the_smn_mode(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    cuerpo: bytes,
) -> None:
    ids = await registrar(alertas_redis, "cordoba", 2)
    response = await llamar(async_client, cuerpo)
    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids) and len(feed.llamadas) == 1
    assert locks(fake_upstash) == [CLAVE_LOCK_SMN] and open_meteo_prohibido.calls == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        b'{"modo":"smn","modo":"pronostico"}',  # duplicate keys: the LAST one wins
        b'{"MODO":"smn"}',  # the key is case-sensitive: no `modo` -> forecast
        b'{"Modo":"smn"}',
        b'{"modo":"smn"',  # truncated JSON -> "not JSON" -> forecast (documented in the runbook as an open point)
        b'{"modo":"smn"} extra',  # trailing garbage -> not JSON -> forecast
        b"modo=smn",  # a form body -> not JSON -> forecast
    ],
    ids=["dup-ultimo-pronostico", "clave-mayusculas", "clave-capital", "truncado", "basura-final", "form"],
)
async def test_bodies_that_do_not_decode_to_modo_smn_run_the_forecast_silently(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, en_seco, feed, monkeypatch, cuerpo: bytes,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Documents (does not endorse) the fallback: a body MEANT as SMN but not decodable as `{"modo":"smn"}` runs the
    forecast, with its Open-Meteo calls, and answers 200. The runbook lists it as an open decision."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA.astimezone(timezone.utc))
    fuente = install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    suscribir(fake_upstash, "cordoba", "rosario")
    response = await llamar(async_client, cuerpo)
    assert response.status_code == 200 and response.json() == RESPUESTA_PRONOSTICO_DOS_ZONAS
    assert len(fuente.calls) == 2 and feed.llamadas == [] and locks(fake_upstash) == [CLAVE_LOCK]
    assert len(lineas_de_resumen(caplog)) == 1 and lineas_de_resumen_smn(caplog) == []


async def test_a_signed_deeply_nested_json_body_is_the_forecast_run_never_a_500(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, feed, reloj_pronostico,  # noqa: F811
) -> None:
    """The router promises "nunca 500". `json.loads` raises RecursionError (not ValueError) on ~65 k nested arrays,
    which fit under MAX_CUERPO_EVALUAR_BYTES. As in the baseline, such a signed body is the forecast run (here, with
    the flags off, the usual `apagado`)."""
    fuente = install(CALMA)
    suscribir(fake_upstash, "cordoba")
    cuerpo = b"[" * (router_alertas.MAX_CUERPO_EVALUAR_BYTES - 1)
    response = await llamar(async_client, cuerpo)
    assert response.status_code == 200 and response.json() == {"estado": "apagado"}
    assert fake_upstash.commands == [] and fuente.calls == [] and feed.llamadas == []


def test_modo_pedido_on_a_deeply_nested_body_is_the_forecast_mode() -> None:
    assert router_alertas.modo_pedido(b"[" * 65535) == router_alertas.MODO_PRONOSTICO


# ---------------------------------------------------------------------------
# Signature before mode: an INVALID signature (not only an absent one) hides the 422
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "firma",
    [
        firmar(b'{"modo":"otro"}', clave=CLAVE_AJENA),  # right body, foreign key
        firmar(CUERPO_SMN),  # valid signature, but for another body
        firmar(b'{"modo":"otro"}', exp_en=-60),  # expired
        firmar(b'{"modo":"otro"}', sub="https://otro.example/api/alertas/evaluar"),  # another URL
        firmar(b'{"modo":"otro"}', quitar=("body",)),  # no body claim
    ],
    ids=["clave-ajena", "otro-cuerpo", "vencida", "otra-url", "sin-body"],
)
async def test_an_unknown_mode_with_an_invalid_signature_is_the_401_never_the_422(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    firma: str, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    fake_upstash.commands.clear()
    response = await llamar(async_client, b'{"modo":"otro"}', firma=firma)
    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert fake_upstash.commands == [] and push.llamadas == [] and feed.llamadas == []
    assert not any("modo desconocido" in r.getMessage() for r in caplog.records)  # the mode was never looked at


# ---------------------------------------------------------------------------
# The body size boundary is unchanged: 64 KiB with `modo` inside still runs; one byte more is the 401 of always
# ---------------------------------------------------------------------------


def _cuerpo_de(largo: int) -> bytes:
    cabeza = b'{"modo":"smn","pad":"'
    cola = b'"}'
    return cabeza + b"x" * (largo - len(cabeza) - len(cola)) + cola


async def test_a_64_kib_signed_body_with_modo_smn_runs_the_smn_mode(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
) -> None:
    cuerpo = _cuerpo_de(router_alertas.MAX_CUERPO_EVALUAR_BYTES)
    assert len(cuerpo) == 64 * 1024
    await registrar(alertas_redis, "cordoba", 2)
    response = await llamar(async_client, cuerpo)
    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA


async def test_a_body_one_byte_over_the_cap_is_the_401_before_the_mode(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
) -> None:
    cuerpo = _cuerpo_de(router_alertas.MAX_CUERPO_EVALUAR_BYTES + 1)
    await registrar(alertas_redis, "cordoba", 2)
    fake_upstash.commands.clear()
    response = await llamar(async_client, cuerpo)
    assert response.status_code == 401 and response.json() == NO_AUTORIZADO
    assert fake_upstash.commands == [] and feed.llamadas == []


# ---------------------------------------------------------------------------
# Two runs at once: a forecast delivery and an SMN delivery, both evaluated, each with its own lock
# ---------------------------------------------------------------------------


async def test_a_forecast_delivery_and_an_smn_delivery_at_the_same_time_both_run(
    async_client: AsyncClient, alertas_redis, fake_upstash, install, envio_activo, push, feed, monkeypatch,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: AHORA.astimezone(timezone.utc))  # 10:30 AR: in window
    fuente = install(respond=respuestas_por_zona({"cordoba": TORMENTA, "rosario": CALMA}))
    ids = await registrar(alertas_redis, "cordoba", 2)
    await registrar(alertas_redis, "rosario", 1)
    feed.obtener = avisos_por_zona({"cordoba": [TORMENTA_SIN_FECHAS]})
    push.cesiones = 5

    pronostico, smn = await asyncio.gather(llamar(async_client, CUERPO), llamar(async_client, CUERPO_SMN))

    assert pronostico.status_code == 200 and pronostico.json()["estado"] == "evaluada"
    assert smn.status_code == 200 and smn.json()["estado"] == "evaluada"
    assert smn.json()["smn_avisadas"] == 1 and pronostico.json()["con_tormenta"] == 1
    assert locks(fake_upstash) == [CLAVE_LOCK, CLAVE_LOCK_SMN]
    assert len(fuente.calls) == 2 and len(feed.llamadas) == 1
    # Each subscriber of cordoba got one forecast push and one SMN push (different tags: they do not collapse).
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids * 2)
    assert len({c.payload["tag"] for c in push.llamadas}) == 2
    assert len(lineas_de_resumen(caplog)) == 1 and len(lineas_de_resumen_smn(caplog)) == 1


# ---------------------------------------------------------------------------
# The lock TTL comes from the setting, not a constant; the run deadline is the configured one (no 22:00 cut)
# ---------------------------------------------------------------------------


async def test_the_smn_lock_ttl_follows_the_setting(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, feed, open_meteo_prohibido, reloj_smn, monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "alertas_lock_ttl_segundos", 900)
    await llamar(async_client, CUERPO_SMN)
    assert fake_upstash.ttls[CLAVE_LOCK_SMN] == 900
    [comando] = [c for c in fake_upstash.commands if c[0] == "SET"]
    assert comando[3:] == ["NX", "EX", "900"]


async def test_the_smn_run_does_not_pass_a_deadline_so_the_configured_one_applies_and_runs_under_the_job_key(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
    monkeypatch,
) -> None:
    vistas: dict[str, object] = {}
    original = feed.obtener

    async def espia(lat: float, lon: float):
        vistas["clave"] = current_client_key()
        return await original(lat, lon)

    feed.obtener = espia
    await registrar(alertas_redis, "cordoba", 1)
    await llamar(async_client, CUERPO_SMN)
    [(_, kwargs)] = feed.llamadas
    assert set(kwargs) == {"vapid", "reloj"}  # no `plazo`, no `omitir`: the configured deadline and T3's night plug
    assert vistas["clave"] == ALERTAS_JOB_CLIENT_KEY


# ---------------------------------------------------------------------------
# Upstash cost through HTTP: 3 commands for an empty run, 11 with 50 zones and one alert
# ---------------------------------------------------------------------------


async def test_an_smn_run_with_50_zones_and_no_alert_costs_3_commands_through_http(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
) -> None:
    for zona in ZONAS:
        suscribir(fake_upstash, zona.slug, cantidad=3)
    feed.obtener = avisos_por_zona({})
    fake_upstash.commands.clear()
    response = await llamar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json()["estado"] == "evaluada"
    assert [c[0] for c in fake_upstash.commands] == ["GET", "SET", "SMEMBERS"]
    assert push.llamadas == []


async def test_an_smn_run_with_50_zones_and_one_alert_costs_11_commands_through_http(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, push, feed, open_meteo_prohibido, reloj_smn,
) -> None:
    for zona in ZONAS:
        if zona.slug != "cordoba":
            suscribir(fake_upstash, zona.slug, cantidad=3)
    await registrar(alertas_redis, "cordoba", 2)
    fake_upstash.commands.clear()
    response = await llamar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert [c[0] for c in fake_upstash.commands] == [
        "GET", "SET", "SMEMBERS", "SMEMBERS", "SMEMBERS", "GET", "GET", "GET", "GET", "SADD", "EXPIRE",
    ]


# ---------------------------------------------------------------------------
# S7 (T5): at 3 h in Argentina a yellow alert does NOT go out; a red one does (the table: test_alertas_noche_smn.py)
# ---------------------------------------------------------------------------


def test_the_night_rule_omits_a_yellow_alert_from_22_to_5_and_never_a_red_one() -> None:
    for hora in (22, 23, 0, 3, 4):
        assert avisos_smn.se_omite_de_noche(AMARILLO, datetime(2026, 10, 14, hora, 0, tzinfo=AR)) is True
        assert avisos_smn.se_omite_de_noche(ROJO, datetime(2026, 10, 14, hora, 0, tzinfo=AR)) is False
    for hora in (5, 13, 21):
        assert avisos_smn.se_omite_de_noche(AMARILLO, datetime(2026, 10, 14, hora, 0, tzinfo=AR)) is False


# ---------------------------------------------------------------------------
# The new log line vs the old substring filter of the forecast line
# ---------------------------------------------------------------------------


async def test_the_smn_line_would_match_a_substring_filter_on_evaluation_estado(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, feed, open_meteo_prohibido, reloj_smn,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Informative: anyone grepping Render logs for `evaluation estado=` (without the `alertas: ` prefix) sees both
    lines; grepping `alertas: evaluation estado=` sees only the forecast's."""
    caplog.set_level(logging.DEBUG)
    await llamar(async_client, CUERPO_SMN)
    [linea] = lineas_de_resumen_smn(caplog)
    assert "evaluation estado=" in linea.getMessage()
    assert not linea.getMessage().startswith("alertas: evaluation estado=")
