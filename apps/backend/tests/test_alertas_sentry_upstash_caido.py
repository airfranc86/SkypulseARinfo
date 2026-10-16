"""FRA-360, part 2 follow-up: a run that answers `apagado` because Upstash is DOWN must alert Sentry.

Before this, the router answered `{"estado": "apagado"}` (fail closed) when the kill key could not be read and nothing
told anybody: a full Upstash outage was silent. Now, with a sending flag ON, an unreadable kill key (or no Upstash at
all) emits the `upstash_no_disponible` alert of its run kind (error, once every 6 hours). A deliberate stop stays silent:
both flags off, or the kill key present. The decision (`_modo_de_la_corrida`) is unchanged (it still delegates to
`interruptor.envio_activo` / `evaluacion.evaluacion_permitida`, which a truth table pins); the router only looks, AFTER an
"apagado", at how the single read of the kill key ended (`interruptor.ultimo_estado_de_la_clave`). Emitting never changes the response. Sentry is the spy `sentry_espia`; Upstash is the fake of conftest.
"""
from __future__ import annotations

import asyncio
import itertools
import json
from contextvars import ContextVar

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError, configure_redis
from app.routers import alertas as router_alertas
from app.services.alertas import avisos_sentry, evaluacion, interruptor
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name; estado_de_alertas_limpio is autouse)
    CLAVE_APAGADO,
    CUERPO,
    CUERPO_SMN,
    en_seco,
    envio_activo,
    estado_de_alertas_limpio,
    llamar_evaluar,
    sentry_espia,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL

pytestmark = pytest.mark.integration

APAGADO = {"estado": "apagado"}


def _evento_de_upstash_caido(tipo: str) -> tuple[str, dict]:
    return (
        "alertas: corrida fallida (upstash_no_disponible)",
        {
            "level": "error",
            "tags": {
                "alert_kind": "alertas_corrida",
                "corrida": tipo,
                "estado": "upstash_no_disponible",
                "motivo": "upstash_no_disponible",
            },
            "extras": {"evaluadas": 0, "sin_datos": 0, "errores": 0, "diferidas": 0}
            if tipo == "pronostico"
            else {"smn_sin_datos": 0, "smn_avisos": 0, "smn_errores": 0},
            "fingerprint": ["alertas-corrida", "upstash_no_disponible"],
        },
    )


# ---------------------------------------------------------------- the decision did not change; the signal is exact


@pytest.mark.parametrize(
    ("en_seco_on", "envio_on", "estado"),
    list(itertools.product((False, True), (False, True), ("ausente", "presente", "ilegible", "sin_upstash"))),
)
async def test_the_mode_of_the_run_is_the_predicates_and_the_unreadable_signal_is_exact(
    monkeypatch, fake_upstash, en_seco_on, envio_on, estado
) -> None:
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", en_seco_on)
    monkeypatch.setattr(settings, "alertas_envio_activo", envio_on)
    redis = None if estado == "sin_upstash" else UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    if estado == "presente":
        fake_upstash.strings[CLAVE_APAGADO] = "1"
    if estado == "ilegible":
        fake_upstash.down = True

    # The old rule, written from its documentation: the dry run wins; otherwise only the sending flag sends.
    if en_seco_on:
        viejo = False if await evaluacion.evaluacion_permitida(redis) else None
    else:
        viejo = True if await interruptor.envio_activo(redis) else None
    fake_upstash.commands.clear()
    interruptor.olvidar_el_ultimo_estado_de_la_clave()
    modo = await router_alertas._modo_de_la_corrida(redis)
    ilegible = modo is None and router_alertas._apagado_por_upstash_ilegible()

    assert modo == viejo
    # "Unreadable" is only reported when a sending flag is on (with both off the answer is a deliberate no, and Upstash
    # is not even touched) and the key could not be read.
    assert ilegible is ((en_seco_on or envio_on) and estado in ("ilegible", "sin_upstash"))
    assert router_alertas._apagado_por_upstash_ilegible() is ilegible
    if not (en_seco_on or envio_on):
        assert fake_upstash.commands == []
    else:
        assert len([c for c in fake_upstash.commands if c[0] == "GET"]) <= 1  # the kill key is read once, never twice


# ---------------------------------------------------------------- through the router


@pytest.mark.parametrize(("cuerpo", "tipo"), [(None, "pronostico"), (CUERPO_SMN, "smn")])
async def test_upstash_down_with_sending_on_alerts_sentry_and_the_answer_does_not_change(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, sentry_espia, cuerpo, tipo
) -> None:
    fake_upstash.down = True
    response = await llamar_evaluar(async_client, cuerpo) if cuerpo else await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == APAGADO
    assert sentry_espia == [_evento_de_upstash_caido(tipo)]


async def test_upstash_down_with_only_the_dry_run_flag_also_alerts(
    async_client: AsyncClient, alertas_redis, fake_upstash, en_seco, sentry_espia
) -> None:
    fake_upstash.down = True
    response = await llamar_evaluar(async_client)
    assert response.status_code == 200 and response.json() == APAGADO
    assert sentry_espia == [_evento_de_upstash_caido("pronostico")]


async def test_without_a_configured_upstash_and_sending_on_it_alerts_from_memory(
    async_client: AsyncClient, envio_activo, sentry_espia
) -> None:
    response = await llamar_evaluar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json() == APAGADO
    assert sentry_espia == [_evento_de_upstash_caido("smn")]


async def test_the_kill_key_present_is_a_deliberate_stop_and_stays_silent(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, sentry_espia
) -> None:
    fake_upstash.strings[CLAVE_APAGADO] = "1"
    fake_upstash.commands.clear()
    response = await llamar_evaluar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json() == APAGADO
    assert fake_upstash.commands == [["GET", CLAVE_APAGADO]]  # one read, no Sentry mark
    assert sentry_espia == []


async def test_both_flags_off_is_a_deliberate_stop_and_stays_silent_even_with_upstash_down(
    async_client: AsyncClient, alertas_redis, fake_upstash, sentry_espia
) -> None:
    fake_upstash.down = True
    response = await llamar_evaluar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json() == APAGADO
    assert sentry_espia == [] and fake_upstash.requests == []  # Upstash is not even touched


async def test_a_second_outage_run_inside_six_hours_alerts_once(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, sentry_espia
) -> None:
    fake_upstash.down = True
    for _ in range(3):
        response = await llamar_evaluar(async_client, CUERPO_SMN)
        assert response.status_code == 200 and response.json() == APAGADO
    assert len(sentry_espia) == 1


async def test_a_sentry_failure_does_not_change_the_apagado_answer(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, monkeypatch, caplog
) -> None:
    def roto(mensaje: str, **kwargs) -> None:
        raise RuntimeError("sentry caido")

    monkeypatch.setattr(avisos_sentry, "capture_message", roto)
    fake_upstash.down = True
    response = await llamar_evaluar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json() == APAGADO
    assert any("sentry alert could not be emitted exc_type=RuntimeError" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- extra cases found by the independent review


@pytest.mark.parametrize("cuerpo", [{}, {"error": "WRONGPASS"}, {"result": 123}], ids=["sin-result", "error", "no-texto"])
async def test_a_strange_answer_to_the_kill_key_read_also_alerts_and_the_answer_does_not_change(
    async_client: AsyncClient, envio_activo, sentry_espia, cuerpo
) -> None:
    with respx.mock(assert_all_called=False) as router:
        router.post(url__startswith=FAKE_UPSTASH_URL).mock(
            side_effect=lambda req: httpx.Response(200, json=cuerpo)
            if json.loads(req.content)[0] == "GET"
            else httpx.Response(200, json={"result": "OK"})
        )
        configure_redis(UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
        response = await llamar_evaluar(async_client, CUERPO_SMN)
    assert response.status_code == 200 and response.json() == APAGADO
    assert len(sentry_espia) == 1


QUIEN: ContextVar[str] = ContextVar("quien", default="?")


async def _como(quien: str, client: AsyncClient, cuerpo: bytes | None = None):
    QUIEN.set(quien)
    return await (llamar_evaluar(client, cuerpo) if cuerpo else llamar_evaluar(client))


async def test_two_simultaneous_requests_do_not_see_each_others_read_of_the_kill_key(
    async_client: AsyncClient, alertas_redis, envio_activo, sentry_espia, monkeypatch
) -> None:
    """A cannot read the kill key (Upstash down for it) while B reads it present: only A alerts, whatever the order."""
    b_listo = asyncio.Event()

    async def read_strict(self, key):
        if QUIEN.get() == "A":
            await b_listo.wait()  # B has already finished its read when A fails
            raise UpstashUnavailableError("caido")
        b_listo.set()
        return "1"

    monkeypatch.setattr(UpstashRedis, "read_strict", read_strict)
    ra, rb = await asyncio.gather(_como("A", async_client, CUERPO_SMN), _como("B", async_client))
    assert ra.json() == rb.json() == APAGADO
    assert [evento[1]["tags"]["corrida"] for evento in sentry_espia] == ["smn"]


async def test_the_outage_costs_one_get_and_one_mark_the_first_time_and_only_the_get_after(
    async_client: AsyncClient, alertas_redis, fake_upstash, envio_activo, sentry_espia
) -> None:
    fake_upstash.down = True
    await llamar_evaluar(async_client, CUERPO_SMN)
    primera = len(fake_upstash.requests)
    await llamar_evaluar(async_client, CUERPO_SMN)
    assert primera == 2 and len(fake_upstash.requests) - primera == 1  # GET + SET, then only the GET
