"""Real sending of the scheduled alerts (FRA-355, PR5c): `services/alertas/despacho.py` and `evaluar(enviar=True)`.

A run that SENDS (the router decides it with `interruptor.envio_activo`, never with `evaluacion_permitida`) hands every
zone with a storm to `despacho.despachar_zona`:

  recipients read (SMEMBERS) -> dedupe mark `SET NX EX` (BEFORE any send; no mark = no send) -> batches of 10 sends,
  the kill key and the run deadline checked between batches -> OK / VENCIDA (deleted) / ERROR (one retry, never deleted)

Everything runs without a network. Most tests replace `envio.enviar` with `PushFalso` (it records the calls); the last
block runs the REAL `envio.enviar` against the fake HTTP layer of `pywebpush` (`push_http`). Nothing here sends a push.
The second pass, the pruning and the counters of `evaluar` are in `test_alertas_evaluacion.py`; the router, in
`test_alertas_evaluar_router.py`.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone

import pytest

from app.core.config import settings
from app.core.upstash import UpstashRedis, UpstashUnavailableError
from app.services.alertas import despacho, envio, evaluacion, interruptor, regla
from app.services.alertas import suscripcion as svc
from app.services.alertas.envio import Resultado, topic_de
from app.services.alertas.textos import franjas_de, franjas_granizo, texto_aviso_hoy, texto_aviso_manana
from app.services.alertas.zonas import zona_por_slug
from app.services.openmeteo import parse_hourly_forecast
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    AHORA,
    AHORA_21H,
    CALMA,
    CLAVE_APAGADO,
    CLAVE_LOCK,
    CLAVE_ENVIADOS_HOY,
    CLAVE_ENVIADOS_MANANA,
    TORMENTA,
    AR,
    LecturaQueFallaUnaVez,
    LecturaQueSeRompe,
    PushFalso,
    RedisConFalla,
    RedisConLecturaDudosa,
    RelojDeTest,
    comandos,
    correr,
    envio_activo,
    esperas,
    payload_horario,
    push,
    redis,
    registrar,
    reloj_de_openmeteo,
    reloj_del_bucle,
    respuestas_por_zona,
)
from tests.conftest import FAKE_UPSTASH_TOKEN, FAKE_UPSTASH_URL
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.test_alertas_suscripcion import AUTH, P256DH_FUERA_DE_CURVA

pytestmark = pytest.mark.integration

CORDOBA = zona_por_slug("cordoba")
FECHA_HOY = date(2026, 10, 14)
FECHA_MANANA = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def _entorno(own_caches, reloj_de_openmeteo, esperas, envio_activo):  # noqa: F811
    """Fresh caches, a frozen `fetched_at` clock, NO real waiting and the send flag on (as when the router sends)."""
    return own_caches


def olvidar_pronosticos(own_caches) -> None:
    """Forget the cached forecasts (a run hours later would otherwise read the series fetched hours before)."""
    for cache in own_caches.caches.values():
        cache.clear()


def tormenta_en(install, *slugs: str, tormenta: dict = TORMENTA, resto: dict = CALMA):
    """Open-Meteo answers `tormenta` for the given zones and calm everywhere else."""
    return install(respond=respuestas_por_zona({slug: tormenta for slug in slugs}, por_defecto=resto))


def conjuntos(fake_upstash) -> list[str]:
    """The keys of the done-sets (who was already reached) that exist in Upstash."""
    return sorted(k for k in fake_upstash.sets if k.startswith("alertas:enviado:"))


def hechos_de(fake_upstash, clave: str = CLAVE_ENVIADOS_HOY) -> set[str]:
    return set(fake_upstash.sets.get(clave, set()))


class RedisQueFalla(UpstashRedis):
    """Upstash that answers everything except the commands on keys that START with `prefijo` (SET NX or SMEMBERS)."""

    def __init__(self, comando: str, prefijo: str, vaciar: bool = False) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._comando, self._prefijo, self._vaciar = comando, prefijo, vaciar

    async def set_nx(self, key: str, value: str, ex: int) -> bool:
        if self._comando == "SET" and key.startswith(self._prefijo):
            raise UpstashUnavailableError("caido")
        return await super().set_nx(key, value, ex)

    async def smembers(self, key: str) -> frozenset[str]:
        if self._comando == "SMEMBERS" and key.startswith(self._prefijo):
            if self._vaciar:
                return frozenset()
            raise UpstashUnavailableError("caido")
        return await super().smembers(key)


class RedisQueFallaAlAnotar(UpstashRedis):
    """Upstash whose SADD on a done-set fails from the `desde`-th time on (1 = the first batch is not even recorded)."""

    def __init__(self, desde: int) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._desde, self.anotaciones = desde, 0

    async def sadd(self, key: str, *members: str) -> int:
        if key.startswith("alertas:enviado:"):
            self.anotaciones += 1
            if self.anotaciones >= self._desde:
                raise UpstashUnavailableError("caido")
        return await super().sadd(key, *members)


class RedisQueApagaAlLeer(UpstashRedis):
    """Pulls the kill key right when the done-set is read (after the zones were evaluated, before the first batch)."""

    def __init__(self, fake_upstash) -> None:
        super().__init__(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
        self._fake = fake_upstash

    async def smembers(self, key: str) -> frozenset[str]:
        if key.startswith("alertas:enviado:"):
            self._fake.strings[CLAVE_APAGADO] = "1"
        return await super().smembers(key)


# ---------------------------------------------------------------------------
# [1] Mode: a dry run never sends; a sending run needs a VAPID key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("explicito", [False, None], ids=["enviar-false", "sin-argumento"])
async def test_a_dry_run_sends_nothing_marks_nothing_and_touches_no_subscription(
    redis, fake_upstash, install, push, explicito
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 2)
    antes = {k: set(v) for k, v in fake_upstash.sets.items()}
    fake_upstash.commands.clear()
    argumentos = {} if explicito is None else {"enviar": explicito}
    resultado = await evaluacion.evaluar(redis, AHORA, **argumentos)
    assert resultado.estado == "evaluada" and resultado.con_tormenta == 1
    assert resultado.envio is None  # a dry run has no sending counters
    assert push.llamadas == []
    assert conjuntos(fake_upstash) == []
    assert {k: set(v) for k, v in fake_upstash.sets.items()} == antes  # nothing pruned, nothing removed
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in ids)
    leidos = [c for c in fake_upstash.commands if c[0] == "GET" and c[1].startswith("alertas:sub:")]
    assert leidos == []  # not even a subscription was read
    assert [c for c in fake_upstash.commands if c[0] in {"SREM", "DEL", "SADD"}] == []
    assert [c[1] for c in fake_upstash.commands if c[0] == "SET"] == [CLAVE_LOCK]


async def test_a_sending_run_notifies_every_subscriber_of_a_zone_with_a_storm(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 3)
    resultado = await correr(redis)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    for llamada in push.llamadas:
        assert llamada.registro == fake_upstash.strings[f"alertas:sub:{llamada.sub_id}"]  # the stored JSON, untouched
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=3)
    assert resultado.estado == "evaluada" and resultado.con_tormenta == 1


async def test_only_the_zones_with_a_storm_are_notified(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 1)
    ids_rosario = await registrar(redis, "rosario", 2)
    resultado = await correr(redis)
    assert {c.zona for c in push.llamadas} == {"cordoba"}
    assert not any(c.sub_id in ids_rosario for c in push.llamadas)
    assert conjuntos(fake_upstash) == [CLAVE_ENVIADOS_HOY]
    assert resultado.envio.avisadas == 1 and resultado.sin_tormenta == 1


@pytest.mark.parametrize("clave", ["", "no-es-una-clave"], ids=["vacia", "ilegible"])
async def test_without_a_usable_vapid_key_the_run_stops_before_touching_anything(
    redis, fake_upstash, install, monkeypatch, caplog, clave: str
) -> None:
    monkeypatch.setattr(settings, "vapid_private_key", clave)
    fuente = tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 1)
    fake_upstash.commands.clear()
    caplog.set_level(logging.DEBUG)
    resultado = await correr(redis)
    assert resultado.estado == "sin_vapid"
    assert resultado.como_respuesta() == {"estado": "sin_vapid"}
    assert fake_upstash.commands == [] and fuente.calls == []  # no lock, no zones, no Open-Meteo
    assert [r for r in caplog.records if r.levelno >= logging.WARNING]  # the owner must be able to see it
    if clave:
        assert clave not in caplog.text


async def test_outside_the_review_hours_the_state_is_still_fuera_de_ventana_even_without_vapid(
    redis, fake_upstash, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "vapid_private_key", "")
    resultado = await correr(redis, datetime(2026, 10, 14, 3, 0, tzinfo=AHORA.tzinfo))
    assert resultado.estado == "fuera_de_ventana"


# ---------------------------------------------------------------------------
# [3] Dedupe per zone and target date
# ---------------------------------------------------------------------------


async def test_the_ids_reached_are_recorded_in_a_set_with_a_36_hour_expiry_set_once(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 12)  # two batches
    await correr(redis)
    assert hechos_de(fake_upstash) == set(ids)
    sadds = [c for c in fake_upstash.commands if c[:2] == ["SADD", CLAVE_ENVIADOS_HOY]]
    assert [len(c) - 2 for c in sadds] == [10, 2]  # ONE SADD per batch, with all the ids of the batch
    assert ["EXPIRE", CLAVE_ENVIADOS_HOY, str(36 * 3600), "NX"] in fake_upstash.commands  # set if missing: never stretched
    assert fake_upstash.ttls[CLAVE_ENVIADOS_HOY] == 129600 == despacho.ENVIADOS_TTL_SEGUNDOS
    assert not [c for c in fake_upstash.commands if c[0] == "SET" and c[1].startswith("alertas:enviado:")]  # no zone mark


async def test_the_ids_of_a_batch_are_recorded_before_the_next_batch_goes_out(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 25)  # three batches: 10, 10, 5
    await correr(redis)
    assert [c.hechos for c in push.llamadas] == [0] * 10 + [10] * 10 + [20] * 5


async def test_two_consecutive_normal_runs_of_the_same_day_never_send_twice(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 2)
    await correr(redis)
    del fake_upstash.strings[CLAVE_LOCK]  # the lock of the first run expired
    segundo = await correr(redis)
    assert len(push.llamadas) == 2  # not a single new send
    assert segundo.envio == despacho.ResumenEnvio(ya_avisadas=1)


async def test_the_10_h_notice_blocks_the_13_h_run_of_the_same_day(
    redis, fake_upstash, install, push, reloj_de_openmeteo, own_caches
) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 1)
    await correr(redis, AHORA)
    del fake_upstash.strings[CLAVE_LOCK]
    olvidar_pronosticos(own_caches)
    reloj_de_openmeteo.instante = AHORA.replace(hour=13)
    segundo = await correr(redis, AHORA.replace(hour=13))
    assert len(push.llamadas) == 1 and segundo.envio.ya_avisadas == 1 and segundo.envio.enviados == 0


async def test_the_21_h_run_uses_the_tomorrow_key_and_is_not_blocked_by_todays_notice(
    redis, fake_upstash, install, push, reloj_de_openmeteo, own_caches
) -> None:
    ambas = payload_horario(codigos={15: 95, 24 + 15: 95})
    tormenta_en(install, "cordoba", tormenta=ambas)
    await registrar(redis, "cordoba", 1)
    await correr(redis, AHORA)  # 10 h: the notice for TODAY
    del fake_upstash.strings[CLAVE_LOCK]
    olvidar_pronosticos(own_caches)
    reloj_de_openmeteo.instante = AHORA_21H
    noche = await correr(redis, AHORA_21H)  # 21 h: the notice for TOMORROW
    assert conjuntos(fake_upstash) == [CLAVE_ENVIADOS_HOY, CLAVE_ENVIADOS_MANANA]
    assert len(push.llamadas) == 2 and noche.envio.avisadas == 1 and noche.envio.ya_avisadas == 0
    assert push.llamadas[1].fecha == FECHA_MANANA


async def test_everybody_already_reached_means_no_send_and_no_subscription_is_even_read(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 2)
    fake_upstash.sets[CLAVE_ENVIADOS_HOY] = set(ids)
    fake_upstash.commands.clear()
    resultado = await correr(redis)
    assert push.llamadas == [] and resultado.envio == despacho.ResumenEnvio(ya_avisadas=1)
    assert not [c for c in fake_upstash.commands if c[0] == "GET" and c[1].startswith("alertas:sub:")]


async def test_the_done_sets_are_per_zone(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba", "rosario")
    await registrar(redis, "cordoba", 1)
    de_rosario = await registrar(redis, "rosario", 1)
    fake_upstash.sets["alertas:enviado:rosario:hoy:2026-10-14"] = set(de_rosario)
    resultado = await correr(redis)
    assert {c.zona for c in push.llamadas} == {"cordoba"}
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, ya_avisadas=1, enviados=1)


async def test_if_upstash_fails_reading_who_was_reached_that_zone_is_not_notified_and_counts_as_an_error(
    fake_upstash, install, push, caplog
) -> None:
    tormenta_en(install, "cordoba", "rosario")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 2)
    await registrar(base, "rosario", 1)
    caplog.set_level(logging.DEBUG)
    resultado = await correr(RedisQueFalla("SMEMBERS", "alertas:enviado:cordoba"))
    assert {c.zona for c in push.llamadas} == {"rosario"}  # fail-closed for cordoba, the others go on
    assert resultado.errores == 1 and resultado.con_tormenta == 1
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=1)
    assert [r for r in caplog.records if r.levelno == logging.WARNING and "evaluation" in r.getMessage()]


async def test_if_the_recipients_cannot_be_read_no_mark_is_taken_and_nothing_is_sent(
    fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 2)
    resultado = await correr(RedisQueFalla("SMEMBERS", "alertas:zona:"))
    assert push.llamadas == [] and conjuntos(fake_upstash) == []  # the zone stays free for the next run
    assert resultado.errores == 1


async def test_a_zone_whose_recipient_set_is_empty_at_send_time_takes_no_mark(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 1)
    resultado = await correr(RedisQueFalla("SMEMBERS", "alertas:zona:", vaciar=True))
    assert push.llamadas == [] and conjuntos(fake_upstash) == []
    assert resultado.envio == despacho.ResumenEnvio()


def test_the_done_set_key_names_the_zone_the_notice_level_and_the_target_date() -> None:
    assert despacho.clave_de_enviados("cordoba", "hoy", FECHA_HOY) == CLAVE_ENVIADOS_HOY
    assert despacho.clave_de_enviados("san-juan", "manana", FECHA_MANANA) == "alertas:enviado:san-juan:manana:2026-10-15"
    assert despacho.ENVIADOS_TTL_SEGUNDOS == 36 * 60 * 60


# ---------------------------------------------------------------------------
# [2] The text: today or tomorrow, the franjas, hail inside the notice
# ---------------------------------------------------------------------------


async def test_the_today_notice_carries_the_approved_text_the_topic_inputs_and_the_destination(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 1)
    await correr(redis)
    llamada = push.llamadas[0]
    esperado = texto_aviso_hoy(CORDOBA, ("tarde",))
    assert llamada.payload["title"] == esperado.titulo and llamada.payload["body"] == esperado.cuerpo
    assert llamada.payload["url"] == envio.URL_ALERTAS == "https://skypulse-ar.vercel.app/prevision"
    assert llamada.payload["tag"] == envio.tag_de("cordoba", FECHA_HOY)
    assert (llamada.zona, llamada.fecha) == ("cordoba", FECHA_HOY)  # what the push Topic is made of
    assert llamada.vapid is not None


async def test_the_21_h_run_sends_the_tomorrow_text_for_tomorrows_date(
    redis, fake_upstash, install, push, reloj_de_openmeteo
) -> None:
    reloj_de_openmeteo.instante = AHORA_21H
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={24 + 15: 95}))
    await registrar(redis, "cordoba", 1)
    await correr(redis, AHORA_21H)
    llamada = push.llamadas[0]
    assert llamada.payload["body"] == texto_aviso_manana(CORDOBA, ("tarde",)).cuerpo
    assert "mañana" in llamada.payload["body"] and "hoy" not in llamada.payload["body"].split(".")[0]
    assert llamada.fecha == FECHA_MANANA and llamada.payload["tag"] == envio.tag_de("cordoba", FECHA_MANANA)
    assert conjuntos(fake_upstash) == [CLAVE_ENVIADOS_MANANA]


async def test_the_tomorrow_notice_also_carries_the_hail(
    redis, fake_upstash, install, push, reloj_de_openmeteo
) -> None:
    reloj_de_openmeteo.instante = AHORA_21H
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={24 + 15: 96}))
    await registrar(redis, "cordoba", 1)
    await correr(redis, AHORA_21H)
    assert push.llamadas[0].payload["body"] == texto_aviso_manana(CORDOBA, ("tarde",), ("tarde",)).cuerpo
    assert "Posible granizo." in push.llamadas[0].payload["body"]


@pytest.mark.parametrize("codigo", [96, 99])
async def test_hail_codes_put_possible_hail_inside_the_notice(redis, fake_upstash, install, push, codigo: int) -> None:
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={15: codigo}))
    await registrar(redis, "cordoba", 1)
    await correr(redis)
    cuerpo = push.llamadas[0].payload["body"]
    assert cuerpo == texto_aviso_hoy(CORDOBA, ("tarde",), ("tarde",)).cuerpo
    assert "Posible granizo." in cuerpo


@pytest.mark.parametrize(
    "serie",
    [
        payload_horario(codigos={15: 95}),
        payload_horario(cape={15: 3000.0}),
        payload_horario(codigos={15: 97}, cape={16: 3000.0}),
    ],
    ids=["codigo-95", "solo-cape", "codigo-97"],
)
async def test_a_storm_without_a_hail_code_never_mentions_hail(redis, fake_upstash, install, push, serie) -> None:
    tormenta_en(install, "cordoba", tormenta=serie)
    await registrar(redis, "cordoba", 1)
    await correr(redis)
    assert "granizo" not in push.llamadas[0].payload["body"]


async def test_hail_in_only_some_franjas_says_which(redis, fake_upstash, install, push) -> None:
    serie = payload_horario(codigos={15: 95, 20: 96})  # a storm in the afternoon, hail at night
    tormenta_en(install, "cordoba", tormenta=serie)
    await registrar(redis, "cordoba", 1)
    await correr(redis)
    assert push.llamadas[0].payload["body"] == texto_aviso_hoy(CORDOBA, ("tarde", "noche"), ("noche",)).cuerpo


async def test_the_text_is_built_from_the_rule_result_with_both_franja_helpers(redis, fake_upstash, install, push) -> None:
    serie = payload_horario(codigos={13: 96, 22: 99})
    tormenta_en(install, "cordoba", tormenta=serie)
    await registrar(redis, "cordoba", 1)
    resultado = await correr(redis)
    zona = next(z for z in resultado.zonas if z.slug == "cordoba")
    esperado = texto_aviso_hoy(CORDOBA, franjas_de(zona.revision), franjas_granizo(zona.revision))
    assert push.llamadas[0].payload["body"] == esperado.cuerpo


# ---------------------------------------------------------------------------
# [4] Recipients: OK, VENCIDA, ERROR with one retry, missing records
# ---------------------------------------------------------------------------


async def test_a_gone_subscription_is_deleted_and_counted(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 3)
    push.vencida_borra = False  # the stand-in does not delete: the dispatch must
    push.resultados[ids[0]] = [Resultado.VENCIDA]
    resultado = await correr(redis)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2, vencidos=1)
    assert f"alertas:sub:{ids[0]}" not in fake_upstash.strings
    assert ids[0] not in fake_upstash.sets["alertas:ids"] and ids[0] not in fake_upstash.sets["alertas:zona:cordoba"]
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in ids[1:])
    assert len(push.a(ids[0])) == 1  # a gone subscription is not retried


async def test_an_error_is_retried_once_after_a_short_wait_and_a_success_counts_as_sent(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push.resultados[sub_id] = [Resultado.ERROR, Resultado.ENVIADA]
    resultado = await correr(redis)
    assert len(push.a(sub_id)) == 2 and esperas == [despacho.ESPERA_REINTENTO_SEGUNDOS]
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=1)


async def test_an_error_that_fails_again_counts_as_failed_after_exactly_two_attempts_and_deletes_nothing(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push.resultados[sub_id] = [Resultado.ERROR]
    antes = {k: set(v) for k, v in fake_upstash.sets.items()}
    resultado = await correr(redis)
    assert len(push.a(sub_id)) == 2 and esperas == [despacho.ESPERA_REINTENTO_SEGUNDOS]
    assert resultado.envio == despacho.ResumenEnvio(fallidos=1)  # nobody reached: not an `avisada` zone
    assert f"alertas:sub:{sub_id}" in fake_upstash.strings  # a transient error NEVER deletes
    assert {k: set(v) for k, v in fake_upstash.sets.items() if k.startswith("alertas:z") or k == "alertas:ids"} == {
        k: v for k, v in antes.items() if k.startswith("alertas:z") or k == "alertas:ids"
    }


async def test_an_error_followed_by_a_gone_answer_counts_as_gone_and_deletes(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push.resultados[sub_id] = [Resultado.ERROR, Resultado.VENCIDA]
    resultado = await correr(redis)
    assert resultado.envio == despacho.ResumenEnvio(vencidos=1)
    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings


async def test_one_failure_does_not_stop_the_others(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 4)
    push.resultados[ids[1]] = [Resultado.ERROR]
    resultado = await correr(redis)
    assert resultado.envio.enviados == 3 and resultado.envio.fallidos == 1


async def test_an_unexpected_exception_while_sending_is_a_failure_not_a_crash_and_leaks_nothing(
    redis, fake_upstash, install, push, caplog
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 2)
    push.resultados[ids[0]] = [RuntimeError("SECRETO-ENDPOINT-boom")]
    caplog.set_level(logging.DEBUG)
    resultado = await correr(redis)
    assert resultado.envio.fallidos == 1 and resultado.envio.enviados == 1
    assert "SECRETO" not in caplog.text and ids[0] not in caplog.text
    assert f"alertas:sub:{ids[0]}" in fake_upstash.strings


async def test_an_id_without_a_record_is_an_expired_id_and_is_cleaned_up_without_sending(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 3)
    for vencido in ids[:2]:
        del fake_upstash.strings[f"alertas:sub:{vencido}"]  # its 180 days ran out
    resultado = await correr(redis)
    assert [c.sub_id for c in push.llamadas] == [ids[2]]
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=1, vencidos=2)
    for vencido in ids[:2]:
        assert vencido not in fake_upstash.sets["alertas:ids"] and vencido not in fake_upstash.sets["alertas:zona:cordoba"]
    assert ids[2] in fake_upstash.sets["alertas:ids"]


async def test_a_resubscription_between_the_read_and_the_cleanup_is_not_cleaned(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    registro = fake_upstash.strings.pop(f"alertas:sub:{sub_id}")
    original = svc.registro_de

    async def registro_que_reaparece(r, i):
        encontrado = await original(r, i)
        fake_upstash.strings[f"alertas:sub:{i}"] = registro  # the person subscribed again meanwhile
        return encontrado

    monkeypatch.setattr(svc, "registro_de", registro_que_reaparece)
    await correr(redis)
    assert sub_id in fake_upstash.sets["alertas:ids"] and sub_id in fake_upstash.sets["alertas:zona:cordoba"]


async def test_a_record_that_cannot_be_read_counts_as_failed_and_is_never_sent_or_deleted(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 2)
    original = svc.registro_de

    async def registro_que_falla(r, i):
        if i == ids[0]:
            raise UpstashUnavailableError("caido")
        return await original(r, i)

    monkeypatch.setattr(svc, "registro_de", registro_que_falla)
    resultado = await correr(redis)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=1, fallidos=1)
    assert push.a(ids[0]) == [] and f"alertas:sub:{ids[0]}" in fake_upstash.strings


async def test_an_error_is_not_retried_when_the_run_deadline_already_passed(
    redis, fake_upstash, install, push, esperas, reloj_del_bucle
) -> None:
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push.resultados[sub_id] = [Resultado.ERROR, Resultado.ENVIADA]
    push.bucle, push.avance = reloj_del_bucle, 200  # the first attempt alone outlasts the deadline
    revision = regla.evaluar_revision(parse_hourly_forecast(TORMENTA), AHORA)
    despachada = await despacho.despachar_zona(
        redis, vapid=object(), plazo=despacho.Plazo.desde_ahora(100), slug="cordoba", suscriptores=1,
        revision=revision, aviso="hoy", fecha=FECHA_HOY,
    )
    assert despachada.resumen == despacho.ResumenEnvio(fallidos=1)
    assert len(push.a(sub_id)) == 1 and esperas == []


async def test_a_notice_that_cannot_be_built_takes_no_mark_and_sends_nothing(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 1)

    def sin_texto(*args, **kwargs):
        raise ValueError("un aviso necesita al menos una franja")

    monkeypatch.setattr(despacho, "_mensaje", sin_texto)
    resultado = await correr(redis)
    assert push.llamadas == [] and conjuntos(fake_upstash) == []
    assert resultado.errores == 1 and resultado.envio == despacho.ResumenEnvio()


async def test_the_sends_of_a_zone_are_bounded_to_ten_at_a_time_but_still_parallel(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 25)
    push.cesiones = 3  # each send yields to the loop, so the sends of a batch really overlap (no real waiting)
    resultado = await correr(redis)
    assert resultado.envio.enviados == 25
    assert 2 <= push.max_en_vuelo <= 10 == despacho.ENVIOS_POR_LOTE


# ---------------------------------------------------------------------------
# [4b] The kill key and the run deadline cut the sending
# ---------------------------------------------------------------------------


async def test_the_kill_key_is_read_again_between_batches_and_a_present_key_stops_the_rest(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 25)

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"  # someone pulls the switch while the first batch goes out

    push.al_llamar = apagar
    resultado = await correr(redis)
    assert resultado.estado == "apagado_a_mitad"
    assert len(push.llamadas) == 10
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=10, diferidos=15)


async def test_an_unreadable_kill_key_between_batches_stops_the_sending_too(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 25)
    # reads: before the zone, before the dispatch, then Upstash stops answering the third (the first batch boundary)
    resultado = await correr(LecturaQueSeRompe(buenas=2))
    assert resultado.estado == "apagado_a_mitad"
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=10, diferidos=15)


async def test_the_kill_key_is_checked_right_before_the_dispatch_not_only_before_the_zone(
    redis, fake_upstash, install, push
) -> None:
    fuente_original = install(respond=respuestas_por_zona({"cordoba": TORMENTA}, por_defecto=CALMA))
    await registrar(redis, "cordoba", 2)
    await registrar(redis, "rosario", 1)
    base = fuente_original._respond

    def respuesta_que_apaga(params):
        fake_upstash.strings[CLAVE_APAGADO] = "1"  # pulled while the forecast of the storm zone is being fetched
        return base(params)

    fuente_original._respond = respuesta_que_apaga
    resultado = await correr(redis)
    assert resultado.estado == "apagado_a_mitad"
    assert push.llamadas == [] and conjuntos(fake_upstash) == []  # no mark burned by a send that never happened
    assert resultado.envio == despacho.ResumenEnvio(diferidos=2)
    # evaluating does not read the kill key per zone: rosario was evaluated too; the read before the dispatch stops it
    assert resultado.con_tormenta == 1 and resultado.sin_tormenta == 1 and resultado.diferidas == 0


async def test_a_run_deadline_between_batches_leaves_the_rest_counted_as_deferred(
    redis, fake_upstash, install, push, monkeypatch, reloj_del_bucle
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 100)
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 25)
    push.bucle, push.avance = reloj_del_bucle, 20  # the 10 sends of the first batch take 200 s of a 100 s deadline
    resultado = await correr(redis)
    assert resultado.estado == "evaluada_incompleta"
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=10, diferidos=15)


async def test_a_zone_with_a_storm_that_the_deadline_reached_before_its_dispatch_is_deferred_and_unmarked(
    redis, fake_upstash, install, push
) -> None:
    await registrar(redis, "cordoba", 3)
    plazo_vencido = despacho.Plazo(limite=asyncio.get_running_loop().time() - 1)
    revision = regla.evaluar_revision(parse_hourly_forecast(TORMENTA), AHORA)
    fake_upstash.commands.clear()
    corte = await despacho.despachar_zona(
        redis, vapid=object(), plazo=plazo_vencido, slug="cordoba", suscriptores=3, revision=revision,
        aviso="hoy", fecha=FECHA_HOY,
    )
    assert corte.corte == despacho.CORTE_PLAZO and corte.resumen == despacho.ResumenEnvio(diferidos=3)
    assert fake_upstash.commands == [] and push.llamadas == []  # nothing, not even the kill key, was touched


# ---------------------------------------------------------------------------
# The small pieces
# ---------------------------------------------------------------------------


async def test_the_deadline_object_counts_down_on_the_event_loop_clock() -> None:
    plazo = despacho.Plazo.desde_ahora(30)
    assert 29 < plazo.restante() <= 30 and not plazo.vencido()
    assert despacho.Plazo.desde_ahora(-1).vencido() and despacho.Plazo.desde_ahora(-1).restante() <= 0


def test_the_wait_before_the_second_pass_outlasts_the_failure_memory_of_the_forecast_cache() -> None:
    import inspect

    from app.core.cache import SingleFlightCache

    memoria = inspect.signature(SingleFlightCache.__init__).parameters["failure_ttl"].default
    assert despacho.ESPERA_SEGUNDA_PASADA_SEGUNDOS > memoria  # otherwise the retry would be answered from the cache
    assert despacho.ESPERA_SEGUNDA_PASADA_SEGUNDOS < settings.alertas_plazo_corrida_segundos / 4
    assert 0 < despacho.ESPERA_REINTENTO_SEGUNDOS <= 5


def test_the_sending_summary_is_frozen_adds_without_mutating_and_lists_only_counters() -> None:
    from dataclasses import FrozenInstanceError

    a, b = despacho.ResumenEnvio(avisadas=1, enviados=2), despacho.ResumenEnvio(enviados=3, fallidos=1)
    suma = a.sumar(b)
    assert suma == despacho.ResumenEnvio(avisadas=1, enviados=5, fallidos=1)
    assert a == despacho.ResumenEnvio(avisadas=1, enviados=2)  # the inputs are untouched
    with pytest.raises(FrozenInstanceError):
        a.enviados = 9  # type: ignore[misc]
    assert tuple(suma.como_respuesta()) == despacho.CONTADORES_ENVIO
    assert despacho.CONTADORES_ENVIO == (
        "avisadas", "ya_avisadas", "enviados", "vencidos", "fallidos", "diferidos", "reintentadas",
    )
    assert all(type(v) is int for v in suma.como_respuesta().values())


def test_only_the_dispatch_module_touches_the_sender_and_the_evaluation_never_imports_it() -> None:
    import ast
    from pathlib import Path

    def importados(modulo) -> set[str]:
        arbol = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
        return {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names} | {
            f"{n.module}.{a.name}" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) for a in n.names
        }

    assert "app.services.alertas.envio" in importados(despacho)
    assert not any(n.endswith(".envio") for n in importados(evaluacion))


# ---------------------------------------------------------------------------
# The REAL `envio.enviar` against the fake HTTP layer of pywebpush (no push is ever really sent)
# ---------------------------------------------------------------------------


async def test_end_to_end_the_real_sender_posts_one_encrypted_push_per_subscriber(
    redis, fake_upstash, install, push_http, vapid_efimera
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 2)
    resultado = await correr(redis)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert sorted(r.url for r in push_http.requests) == sorted(
        f"https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-cordoba-{i:03d}" for i in range(2)
    )
    for pedido in push_http.requests:
        assert pedido.headers["Topic"] == topic_de("cordoba", FECHA_HOY) and pedido.headers["Urgency"] == "high"
    assert len(ids) == 2


async def test_end_to_end_a_410_deletes_the_subscription_and_counts_it_as_gone(
    redis, fake_upstash, install, push_http, vapid_efimera
) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push_http.responder(410)
    resultado = await correr(redis)
    assert resultado.envio == despacho.ResumenEnvio(vencidos=1)
    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings and len(push_http.requests) == 1
    assert sub_id not in fake_upstash.sets["alertas:ids"] and sub_id not in fake_upstash.sets["alertas:zona:cordoba"]


async def test_end_to_end_a_500_is_retried_once_and_never_deletes(
    redis, fake_upstash, install, push_http, vapid_efimera, esperas
) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push_http.responder(500)
    resultado = await correr(redis)
    assert resultado.envio == despacho.ResumenEnvio(fallidos=1)
    assert len(push_http.requests) == 2 and esperas == [despacho.ESPERA_REINTENTO_SEGUNDOS]
    assert f"alertas:sub:{sub_id}" in fake_upstash.strings and sub_id in fake_upstash.sets["alertas:zona:cordoba"]


async def test_end_to_end_neither_the_summary_nor_the_logs_carry_ids_endpoints_texts_keys_or_zones(
    redis, fake_upstash, install, push_http, vapid_efimera, caplog
) -> None:
    caplog.set_level(logging.DEBUG)
    tormenta_en(install, "cordoba", "rosario")
    ids = await registrar(redis, "cordoba", 2) + await registrar(redis, "rosario", 1)
    push_http.responder(500)  # also exercise the failure logs
    resultado = await correr(redis)
    visible = json.dumps(resultado.como_respuesta()) + repr(resultado) + caplog.text
    secretos = (
        *ids, "SECRETO", "fcm.googleapis.com", vapid_efimera.privada, vapid_efimera.publica, "Posibles tormentas",
        "SkyPulse ·", "cordoba", "rosario", "Córdoba", fake_upstash.strings[CLAVE_LOCK],
    )
    for secreto in secretos:
        assert secreto not in visible, secreto
    assert resultado.envio.fallidos == 3


async def test_the_dispatch_uses_the_shared_send_switch_not_the_evaluation_one(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    visto: list[str] = []

    async def espia(r):
        visto.append("envio_activo")
        return True

    monkeypatch.setattr(interruptor, "envio_activo", espia)
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 12)
    await correr(redis)
    assert visto == ["envio_activo"] * 3  # once before the dispatch, then before each of its two batches


async def test_an_unexpected_error_dispatching_a_zone_is_an_error_of_that_zone_and_leaks_nothing(
    redis, fake_upstash, install, push, caplog, monkeypatch
) -> None:
    tormenta_en(install, "cordoba", "rosario")
    await registrar(redis, "cordoba", 2)
    await registrar(redis, "rosario", 1)
    original = despacho.despachar_plan

    async def falla_en_cordoba(redis_, plan, **kwargs):
        if plan.slug == "cordoba":
            raise RuntimeError("SECRETO-ENDPOINT-boom")
        return await original(redis_, plan, **kwargs)

    monkeypatch.setattr(despacho, "despachar_plan", falla_en_cordoba)
    caplog.set_level(logging.DEBUG)
    resultado = await correr(redis)
    assert resultado.errores == 1 and resultado.con_tormenta == 1  # cordoba is an error, rosario went on
    assert {c.zona for c in push.llamadas} == {"rosario"}
    assert "SECRETO" not in caplog.text and "cordoba" not in caplog.text


# ===========================================================================
# Correction round (security and code reviews of the PR5c)
# ===========================================================================


def guardar_a_mano(fake_upstash, slug: str, sub_id: str, registro: str) -> None:
    """Store a record straight into the fake, bypassing the validation of `alta` (an old record from before it)."""
    fake_upstash.strings[f"alertas:sub:{sub_id}"] = registro
    fake_upstash.sets.setdefault("alertas:ids", set()).add(sub_id)
    fake_upstash.sets.setdefault(f"alertas:zona:{slug}", set()).add(sub_id)
    fake_upstash.sets.setdefault("alertas:zonas", set()).add(slug)


def registro_envenenado(slug: str = "cordoba", **cambios) -> str:
    datos = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/SECRETO-ENDPOINT-veneno",
        "p256dh": P256DH_FUERA_DE_CURVA,
        "auth": AUTH,
        "zona": slug,
        "actualizada": "2026-01-01T00:00:00+00:00",
        **cambios,
    }
    return json.dumps(datos)


# --- [P1-1b] terminal failures: removed on the first send, never retried, never waited for -----------------------------


async def test_an_existing_off_curve_registration_is_removed_on_the_first_send_and_never_sleeps(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    buenos = await registrar(redis, "cordoba", 2)
    veneno = "V" * 22
    guardar_a_mano(fake_upstash, "cordoba", veneno, registro_envenenado())
    resultado = await correr(redis)
    assert push.a(veneno) == []  # it cannot be encrypted: it is not even attempted
    assert esperas == []  # and nothing waits for it
    assert f"alertas:sub:{veneno}" not in fake_upstash.strings
    assert veneno not in fake_upstash.sets["alertas:ids"] and veneno not in fake_upstash.sets["alertas:zona:cordoba"]
    assert {c.sub_id for c in push.llamadas} == set(buenos)
    # Counted as `vencidos` (a subscription that is gone for good), not as a new counter.
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2, vencidos=1)


@pytest.mark.parametrize("registro", ["no es json", "{}", "[]", "null", registro_envenenado(endpoint="https://169.254.169.254/x")])
async def test_an_unreadable_record_is_removed_not_retried(
    redis, fake_upstash, install, push, esperas, registro: str
) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 1)
    malo = "M" * 22
    guardar_a_mano(fake_upstash, "cordoba", malo, registro)
    resultado = await correr(redis)
    assert push.a(malo) == [] and esperas == []
    assert f"alertas:sub:{malo}" not in fake_upstash.strings and malo not in fake_upstash.sets["alertas:zona:cordoba"]
    assert resultado.envio.vencidos == 1 and resultado.envio.fallidos == 0


async def test_a_local_encryption_failure_removes_the_subscription_without_retry_or_wait(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push.resultados[sub_id] = [Resultado.INVALIDA]
    push.vencida_borra = False
    resultado = await correr(redis)
    assert len(push.a(sub_id)) == 1 and esperas == []
    assert f"alertas:sub:{sub_id}" not in fake_upstash.strings and sub_id not in fake_upstash.sets["alertas:ids"]
    assert resultado.envio == despacho.ResumenEnvio(vencidos=1)


# --- [P1-1c] only transient failures are retried, once, in a final tanda -----------------------------------------------


async def test_transient_errors_are_retried_once_in_one_final_tanda_after_a_single_wait(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 25)
    sorted_ids = sorted(ids)
    for sub_id in (sorted_ids[0], sorted_ids[15]):  # one in the first batch, one in the second
        push.resultados[sub_id] = [Resultado.ERROR, Resultado.ENVIADA]
    resultado = await correr(redis)
    assert esperas == [despacho.ESPERA_REINTENTO_SEGUNDOS]  # ONE wait for the whole zone, not one per batch
    primeras, reintentos = push.llamadas[:25], push.llamadas[25:]
    assert sorted(c.sub_id for c in primeras) == sorted_ids  # everybody is attempted once first ...
    assert sorted(c.sub_id for c in reintentos) == sorted([sorted_ids[0], sorted_ids[15]])  # ... then only the failures
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=25)


async def test_the_failures_of_the_final_tanda_are_retried_concurrently(
    redis, fake_upstash, install, push, esperas, monkeypatch
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 12))
    for sub_id in ids[:3]:
        push.resultados[sub_id] = [Resultado.ERROR, Resultado.ENVIADA]
    push.cesiones = 3
    previo = despacho._dormir

    async def dormir_y_medir_de_nuevo(segundos: float) -> None:
        await previo(segundos)
        push.max_en_vuelo = 0  # whatever comes after the single wait is the final tanda

    monkeypatch.setattr(despacho, "_dormir", dormir_y_medir_de_nuevo)
    await correr(redis)
    assert push.max_en_vuelo == 3  # the three retries were in flight together


async def test_a_persistent_refusal_is_not_retried_not_deleted_and_counts_as_failed(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    (sub_id,) = await registrar(redis, "cordoba", 1)
    push.resultados[sub_id] = [Resultado.RECHAZADA]
    resultado = await correr(redis)
    assert len(push.a(sub_id)) == 1 and esperas == []
    assert f"alertas:sub:{sub_id}" in fake_upstash.strings and sub_id in fake_upstash.sets["alertas:zona:cordoba"]
    assert resultado.envio == despacho.ResumenEnvio(fallidos=1)


async def test_a_run_cut_before_the_final_tanda_does_not_retry(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 25))
    push.resultados[ids[0]] = [Resultado.ERROR, Resultado.ENVIADA]

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"

    push.al_llamar = apagar
    resultado = await correr(redis)
    assert resultado.estado == "apagado_a_mitad" and esperas == [] and len(push.a(ids[0])) == 1
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=9, fallidos=1, diferidos=15)


# --- [P1-1d] a time cap per zone ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("restante", "pendientes", "restantes", "esperado"),
    [
        (100, 40, 45, 100 * 40 / 45),  # a big zone gets a big share, not the smallest one
        (100, 5, 45, 100 * 5 / 45 if 100 * 5 / 45 > 15 else 15),  # a small one still gets its floor
        (100, 1, 1000, 15),  # the floor
        (10, 5, 5, 10),  # never more than what is left
        (10, 1, 2, 10),  # the floor is clipped to what is left too
        (0, 5, 5, 0),  # nothing left, nothing granted
        (-3, 5, 5, 0),
        (100, 7, 7, 100),  # the only zone left takes everything
    ],
)
def test_the_zone_cap_is_the_time_left_in_proportion_to_the_pendientes_with_a_floor(
    restante, pendientes, restantes, esperado
) -> None:
    assert despacho.tope_para_zona(restante, pendientes, restantes) == pytest.approx(esperado)


async def test_the_time_is_shared_in_proportion_to_what_each_zone_has_to_send(
    redis, fake_upstash, install, push, monkeypatch, reloj_del_bucle
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 100)
    tormenta_en(install, "cordoba", "rosario")
    await registrar(redis, "cordoba", 40)
    await registrar(redis, "rosario", 5)
    push.bucle, push.avance = reloj_del_bucle, 2  # a batch takes 20 s: cordoba needs 80 s
    resultado = await correr(redis)
    # cordoba's share is 100 * 40 / 45 = 88.9 s: all four batches go out. Sharing equally (50 s) would have cut it at 30.
    por_zona = {z: sum(1 for c in push.llamadas if c.zona == z) for z in ("cordoba", "rosario")}
    assert por_zona == {"cordoba": 40, "rosario": 5} and resultado.estado == "evaluada"
    assert resultado.envio == despacho.ResumenEnvio(avisadas=2, enviados=45)


async def test_a_zone_that_exceeds_its_share_stops_and_the_next_zone_still_gets_its_turn(
    redis, fake_upstash, install, push, monkeypatch, reloj_del_bucle
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 100)
    tormenta_en(install, "cordoba", "rosario")
    ids_cordoba = sorted(await registrar(redis, "cordoba", 40))
    ids_rosario = await registrar(redis, "rosario", 5)
    push.bucle, push.avance = reloj_del_bucle, 3  # a batch takes 30 s; cordoba's share is 88.9 s
    resultado = await correr(redis)
    por_zona = {z: sum(1 for c in push.llamadas if c.zona == z) for z in ("cordoba", "rosario")}
    assert por_zona == {"cordoba": 30, "rosario": 5}  # three batches (90 s > 88.9 s) and then it stops; rosario is served
    assert resultado.estado == "evaluada"  # a zone-level cut does not cut the run
    assert resultado.envio == despacho.ResumenEnvio(avisadas=2, enviados=35, diferidos=10)
    assert hechos_de(fake_upstash) == set(ids_cordoba[:30])  # the other ten stay pending for the next run
    assert hechos_de(fake_upstash, "alertas:enviado:rosario:hoy:2026-10-14") == set(ids_rosario)


async def test_a_zone_with_nothing_left_to_send_takes_no_share_of_the_time(
    redis, fake_upstash, install, push, monkeypatch, reloj_del_bucle
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 100)
    tormenta_en(install, "cordoba", "rosario", "mendoza")
    ya_alcanzados = await registrar(redis, "mendoza", 40)
    fake_upstash.sets["alertas:enviado:mendoza:hoy:2026-10-14"] = set(ya_alcanzados)  # everybody there was reached before
    await registrar(redis, "cordoba", 40)
    await registrar(redis, "rosario", 5)
    push.bucle, push.avance = reloj_del_bucle, 2
    resultado = await correr(redis)
    # If mendoza's 40 counted, cordoba's share would be 100 * 40 / 85 = 47 s and it would stop after 3 batches (60 s).
    assert sum(1 for c in push.llamadas if c.zona == "cordoba") == 40
    assert resultado.envio.ya_avisadas == 1 and resultado.envio.enviados == 45


# --- [4] when the mark is released ----------------------------------------------------------------------------------------


async def test_a_partial_cut_resumes_exactly_where_it_left_off_with_no_duplicate_to_the_reached(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 25))

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"  # an operator pulls the switch while the first batch goes out

    push.al_llamar = apagar
    primera = await correr(redis)
    assert primera.estado == "apagado_a_mitad" and primera.envio == despacho.ResumenEnvio(avisadas=1, enviados=10, diferidos=15)
    assert hechos_de(fake_upstash) == set(ids[:10])
    del fake_upstash.strings[CLAVE_APAGADO]
    del fake_upstash.strings[CLAVE_LOCK]
    push.al_llamar = None
    antes = len(push.llamadas)
    segunda = await correr(redis)
    assert sorted(c.sub_id for c in push.llamadas[antes:]) == ids[10:]  # exactly the rest: none of the first ten again
    assert segunda.envio == despacho.ResumenEnvio(avisadas=1, enviados=15)
    assert hechos_de(fake_upstash) == set(ids)
    tercera_fecha = len(push.llamadas)
    del fake_upstash.strings[CLAVE_LOCK]
    assert (await correr(redis)).envio == despacho.ResumenEnvio(ya_avisadas=1) and len(push.llamadas) == tercera_fecha


async def test_a_deadline_cut_leaves_the_rest_pending_and_the_next_run_does_only_the_rest(
    redis, fake_upstash, install, push, monkeypatch, reloj_del_bucle
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 100)
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 25))
    push.bucle, push.avance = reloj_del_bucle, 20
    primera = await correr(redis)
    assert primera.estado == "evaluada_incompleta" and hechos_de(fake_upstash) == set(ids[:10])
    del fake_upstash.strings[CLAVE_LOCK]
    push.avance, antes = 0, len(push.llamadas)
    segunda = await correr(redis)
    assert sorted(c.sub_id for c in push.llamadas[antes:]) == ids[10:]
    assert segunda.envio == despacho.ResumenEnvio(avisadas=1, enviados=15)


async def test_a_total_failure_leaves_everybody_pending_and_records_nobody(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    ids = await registrar(redis, "cordoba", 3)
    for sub_id in ids:
        push.resultados[sub_id] = [Resultado.ERROR]
    primera = await correr(redis)
    assert primera.envio == despacho.ResumenEnvio(fallidos=3)  # nobody reached: not an `avisada` zone
    assert conjuntos(fake_upstash) == []  # nothing recorded, not even an empty set
    push.resultados = {}
    del fake_upstash.strings[CLAVE_LOCK]
    segunda = await correr(redis)
    assert segunda.envio == despacho.ResumenEnvio(avisadas=1, enviados=3)  # the next run does all of them


async def test_a_crash_between_a_push_and_its_record_repeats_at_most_one_batch(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    ids = sorted(await registrar(base, "cordoba", 25))
    primera = await correr(RedisQueFallaAlAnotar(desde=2))  # batch 2 is pushed but its SADD never lands
    assert len(push.llamadas) == 20 and hechos_de(fake_upstash) == set(ids[:10])
    assert primera.errores == 1  # the zone stopped: sending without recording would repeat people
    assert primera.envio.diferidos == 5  # batch 3 was never started
    del fake_upstash.strings[CLAVE_LOCK]
    antes = len(push.llamadas)
    segunda = await correr(base)
    repetidos = [c.sub_id for c in push.llamadas[antes:] if c.sub_id in set(ids[10:20])]
    assert sorted(c.sub_id for c in push.llamadas[antes:]) == ids[10:]
    assert len(repetidos) == 10  # the duplicate is ONE batch (ids 10 to 19), and the devices collapse it (same tag/Topic)
    assert segunda.envio.enviados == 15 and hechos_de(fake_upstash) == set(ids)


async def test_a_failed_record_stops_the_zone_counts_it_and_does_not_keep_sending(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba", "rosario")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 25)
    await registrar(base, "rosario", 2)
    redis_roto = RedisQueFallaAlAnotar(desde=1)
    resultado = await correr(redis_roto)
    assert sum(1 for c in push.llamadas if c.zona == "cordoba") == 10  # the first batch went out, nothing else
    assert resultado.errores == 2 and resultado.envio.diferidos == 15  # both zones: their first SADD failed
    assert hechos_de(fake_upstash) == set()


async def test_ids_that_failed_are_not_recorded_but_the_gone_and_invalid_ones_are(
    redis, fake_upstash, install, push, esperas
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 6))
    push.resultados[ids[0]] = [Resultado.ERROR]  # transient, fails again at the retry
    push.resultados[ids[1]] = [Resultado.VENCIDA]
    push.resultados[ids[2]] = [Resultado.INVALIDA]
    push.resultados[ids[3]] = [Resultado.RECHAZADA]
    await correr(redis)
    assert hechos_de(fake_upstash) == {ids[1], ids[2], ids[4], ids[5]}  # not the ERROR, not the RECHAZADA
    del fake_upstash.strings[CLAVE_LOCK]
    antes = len(push.llamadas)
    push.resultados = {}
    await correr(redis)
    assert sorted(c.sub_id for c in push.llamadas[antes:]) == sorted([ids[0], ids[3]])  # only the two that were left


async def test_the_today_and_tomorrow_sets_are_independent(redis, fake_upstash, install, push, reloj_de_openmeteo, own_caches) -> None:
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={15: 95, 24 + 15: 95}))
    ids = await registrar(redis, "cordoba", 2)
    await correr(redis, AHORA)
    assert hechos_de(fake_upstash) == set(ids) and hechos_de(fake_upstash, CLAVE_ENVIADOS_MANANA) == set()
    del fake_upstash.strings[CLAVE_LOCK]
    for cache in own_caches.caches.values():
        cache.clear()
    reloj_de_openmeteo.instante = AHORA_21H
    noche = await correr(redis, AHORA_21H)
    assert noche.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert conjuntos(fake_upstash) == [CLAVE_ENVIADOS_HOY, CLAVE_ENVIADOS_MANANA]


async def test_the_first_batch_is_checked_against_the_switch_too(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 3)
    # The kill key is pulled after the zones were evaluated and the done-set read, right before the first batch.
    resultado = await correr(RedisQueApagaAlLeer(fake_upstash))
    assert push.llamadas == [] and conjuntos(fake_upstash) == []
    assert resultado.estado == "apagado_a_mitad" and resultado.envio == despacho.ResumenEnvio(diferidos=3)


async def test_a_kill_key_that_is_present_stops_the_rest_and_records_only_what_was_sent(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 25))

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"

    push.al_llamar = apagar
    resultado = await correr(redis)
    assert resultado.estado == "apagado_a_mitad" and resultado.envio.diferidos == 15
    assert hechos_de(fake_upstash) == set(ids[:10])


async def test_an_unreadable_kill_key_stops_the_rest_and_records_only_what_was_sent(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    ids = sorted(await registrar(base, "cordoba", 25))
    resultado = await correr(LecturaQueSeRompe(buenas=2))
    assert resultado.estado == "apagado_a_mitad" and resultado.envio.diferidos == 15
    assert hechos_de(fake_upstash) == set(ids[:10])


async def test_one_blip_reading_the_kill_key_does_not_cut_the_run(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    await registrar(base, "cordoba", 25)
    flojo = LecturaQueFallaUnaVez(3)  # the read between the first two batches fails once; the re-read answers
    resultado = await correr(flojo)
    assert resultado.estado == "evaluada" and resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=25)
    assert flojo.lecturas >= 4 and conjuntos(fake_upstash) == [CLAVE_ENVIADOS_HOY]


# --- [5] a stale membership --------------------------------------------------------------------------------------------


async def test_an_id_that_now_belongs_to_another_zone_is_removed_from_this_set_and_not_sent(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    (propio,) = await registrar(redis, "cordoba", 1)
    (de_rosario,) = await registrar(redis, "rosario", 1)
    fake_upstash.sets["alertas:zona:cordoba"].add(de_rosario)  # the person changed city; the old set kept the id
    resultado = await correr(redis)
    assert [c.sub_id for c in push.llamadas] == [propio]  # no wrong-city notice
    assert de_rosario not in fake_upstash.sets["alertas:zona:cordoba"]
    assert de_rosario in fake_upstash.sets["alertas:zona:rosario"] and f"alertas:sub:{de_rosario}" in fake_upstash.strings
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=1)  # not counted as anything


# --- [7] smaller items -----------------------------------------------------------------------------------------------------


async def test_an_exception_escaping_a_send_is_counted_as_failed_and_never_raised(
    redis, fake_upstash, install, push, monkeypatch, caplog
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 3))
    original = despacho._enviar_uno

    async def a_veces_revienta(redis, vapid, plazo, sub_id, *args, **kwargs):
        if sub_id == ids[0]:
            raise RuntimeError("SECRETO-ENDPOINT-boom")
        return await original(redis, vapid, plazo, sub_id, *args, **kwargs)

    monkeypatch.setattr(despacho, "_enviar_uno", a_veces_revienta)
    caplog.set_level(logging.DEBUG)
    resultado = await correr(redis)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2, fallidos=1)
    assert "SECRETO" not in caplog.text


def test_seconds_until_the_silence_start_at_22_h_argentina_time() -> None:
    desde = lambda h, m=0, s=0: despacho.segundos_hasta_el_silencio(datetime(2026, 10, 14, h, m, s, tzinfo=AR))  # noqa: E731
    assert desde(21) == 3600 and desde(21, 59, 30) == 30
    assert desde(22) == 0 and desde(23) == 0  # already in the silence
    utc = datetime(2026, 10, 15, 0, 59, 30, tzinfo=timezone.utc)  # 21:59:30 in Argentina
    assert despacho.segundos_hasta_el_silencio(utc) == 30


async def test_the_21_h_run_does_not_keep_sending_after_22_h(redis, fake_upstash, install, push, reloj_de_openmeteo) -> None:
    reloj_de_openmeteo.instante = AHORA_21H
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={24 + 15: 95}))
    await registrar(redis, "cordoba", 3)
    reloj = RelojDeTest(datetime(2026, 10, 14, 22, 0, tzinfo=AR))  # the run was slow: the silence has started
    resultado = await correr(redis, AHORA_21H, reloj=reloj)
    assert resultado.estado == "evaluada_incompleta" and push.llamadas == [] and conjuntos(fake_upstash) == []
    assert [z.veredicto for z in resultado.zonas] == ["diferida"]


async def test_a_21_h_run_that_starts_on_time_still_sends(redis, fake_upstash, install, push, reloj_de_openmeteo) -> None:
    reloj_de_openmeteo.instante = AHORA_21H
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={24 + 15: 95}))
    await registrar(redis, "cordoba", 3)
    resultado = await correr(redis, AHORA_21H, reloj=RelojDeTest(AHORA_21H))
    assert resultado.estado == "evaluada" and len(push.llamadas) == 3


def test_the_today_notice_expires_at_midnight_argentina_time_and_tomorrows_keeps_the_usual_ttl() -> None:
    en = lambda h, m=0, s=0: datetime(2026, 10, 14, h, m, s, tzinfo=AR)  # noqa: E731
    assert despacho.ttl_de_aviso("hoy", en(19)) == 5 * 3600
    assert despacho.ttl_de_aviso("hoy", en(7)) == envio.TTL_ALERTA_SEGUNDOS  # 17 h to midnight: the usual 12 h
    assert despacho.ttl_de_aviso("hoy", en(23, 59, 50)) == 60  # never below a minute (a TTL of 0 is refused)
    assert despacho.ttl_de_aviso("manana", en(21)) == envio.TTL_ALERTA_SEGUNDOS
    assert despacho.ttl_de_aviso("manana", en(23, 59, 50)) == envio.TTL_ALERTA_SEGUNDOS


async def test_the_today_notice_is_sent_with_a_ttl_that_ends_at_midnight(
    redis, fake_upstash, install, push, reloj_de_openmeteo
) -> None:
    ahora = datetime(2026, 10, 14, 19, 30, tzinfo=AR)
    reloj_de_openmeteo.instante = ahora
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={22: 95}))
    await registrar(redis, "cordoba", 1)
    await correr(redis, ahora)
    assert push.llamadas[0].ttl == 4.5 * 3600  # to midnight, not the usual 12 h


async def test_the_tomorrow_notice_is_sent_with_the_usual_ttl(
    redis, fake_upstash, install, push, reloj_de_openmeteo
) -> None:
    reloj_de_openmeteo.instante = AHORA_21H
    tormenta_en(install, "cordoba", tormenta=payload_horario(codigos={24 + 15: 95}))
    await registrar(redis, "cordoba", 1)
    await correr(redis, AHORA_21H)
    assert push.llamadas[0].ttl == envio.TTL_ALERTA_SEGUNDOS


# --- circuit breaker for mass deletion ---------------------------------------------------------------------------------------


async def _zona_con_vencidas(redis, push, slug: str, total: int, vencidas: int) -> list[str]:
    ids = sorted(await registrar(redis, slug, total))
    for sub_id in ids[:vencidas]:
        push.resultados[sub_id] = [Resultado.VENCIDA]
    return ids


async def test_the_sender_is_asked_not_to_delete_by_itself(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 2)
    await correr(redis)
    assert all(c.borrar is False for c in push.llamadas)  # the dispatch decides, behind the breaker


async def test_more_than_half_of_a_batch_gone_trips_the_breaker_and_nothing_is_deleted(
    redis, fake_upstash, install, push, caplog
) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 8, 5)  # a proxy returning 404 for everything
    caplog.set_level(logging.DEBUG)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in ids)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=3, fallidos=5)  # kept, so not "gone"
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING and "deletion" in r.getMessage()]
    assert len(avisos) == 1
    assert not any(i in caplog.text for i in ids)


async def test_exactly_half_gone_is_a_normal_run_and_the_gone_ones_are_deleted(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 8, 4)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" not in fake_upstash.strings for i in ids[:4])
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=4, vencidos=4)


async def test_a_batch_smaller_than_four_never_trips_the_breaker(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 3, 3)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" not in fake_upstash.strings for i in ids)
    assert resultado.envio.vencidos == 3


async def test_once_tripped_the_breaker_stays_open_for_the_rest_of_the_run_and_the_next_zone(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba", "rosario")
    await _zona_con_vencidas(redis, push, "cordoba", 8, 5)
    del_otra = await _zona_con_vencidas(redis, push, "rosario", 2, 2)  # too few to trip it, but the breaker is open
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in del_otra)
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 7


async def test_a_new_run_starts_with_the_breaker_closed(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 8, 5)
    await correr(redis)
    del fake_upstash.strings[CLAVE_LOCK]
    fake_upstash.sets.pop(CLAVE_ENVIADOS_HOY)  # a new day's set: everybody pending again
    push.resultados = {i: [Resultado.VENCIDA] for i in ids[:2]}  # a normal, small expiry
    resultado = await correr(redis)
    assert resultado.envio.vencidos == 2 and f"alertas:sub:{ids[0]}" not in fake_upstash.strings


async def test_a_proxy_outage_answering_404_to_everyone_over_several_tiny_zones_deletes_nothing(
    redis, fake_upstash, install, push
) -> None:
    zonas = ("cordoba", "rosario", "mendoza", "salta")
    tormenta_en(install, *zonas)
    todos = []
    for slug in zonas:  # four zones of two subscribers: no batch ever reaches the minimum of four
        todos += await _zona_con_vencidas(redis, push, slug, 2, 2)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in todos)
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 8  # not "gone for good": kept and still failing


async def test_genuinely_dead_subscriptions_in_a_healthy_run_are_still_deleted(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba", "rosario")
    grande = await _zona_con_vencidas(redis, push, "cordoba", 20, 2)
    chica = await _zona_con_vencidas(redis, push, "rosario", 3, 1)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" not in fake_upstash.strings for i in grande[:2] + chica[:1])
    assert resultado.envio.vencidos == 3 and resultado.envio.enviados == 20


async def test_the_deletions_of_a_zone_wait_until_the_zone_is_closed(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 12, 1)
    vistas: list[bool] = []

    def espiar(n: int) -> None:
        if n == 11:  # the first call of the second batch: the gone one of the first batch is still there
            vistas.append(f"alertas:sub:{ids[0]}" in fake_upstash.strings)

    push.al_llamar = espiar
    await correr(redis)
    assert vistas == [True] and f"alertas:sub:{ids[0]}" not in fake_upstash.strings


async def test_an_outage_that_starts_late_in_a_healthy_run_still_trips_the_breaker(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba", "rosario")
    await registrar(redis, "cordoba", 20)  # twenty healthy sends first: the run's totals alone would not trip
    caida = await _zona_con_vencidas(redis, push, "rosario", 10, 10)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in caida)  # but a whole batch of gone does
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 10


async def test_invalid_records_count_with_the_gone_ones_in_the_breaker(redis, fake_upstash, install, push) -> None:
    """A bug in the validation that made every record "invalid" must not wipe the subscriptions either."""
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 3)
    venenos = [f"V{i}" * 11 for i in range(5)]
    for veneno in venenos:
        guardar_a_mano(fake_upstash, "cordoba", veneno, registro_envenenado())
    resultado = await correr(redis)
    assert all(f"alertas:sub:{v}" in fake_upstash.strings for v in venenos)  # 5 of 8 are "invalid": the breaker holds
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=3, fallidos=5)


async def test_invalid_records_in_a_healthy_run_are_deleted(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 9)
    veneno = "V" * 22
    guardar_a_mano(fake_upstash, "cordoba", veneno, registro_envenenado())
    await correr(redis)
    assert f"alertas:sub:{veneno}" not in fake_upstash.strings


# --- second correction round: the encryption self-test guards the whole run ------------------------------------------------


async def test_if_the_encryption_self_test_fails_the_run_is_sin_vapid_and_touches_nothing(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    fuente = tormenta_en(install, "cordoba")
    await registrar(redis, "cordoba", 2)
    fake_upstash.commands.clear()

    def falla(self, data, *args, **kwargs):
        raise RuntimeError("regresion en http_ece")

    monkeypatch.setattr(envio.WebPusher, "encode", falla)
    resultado = await correr(redis)
    assert resultado.estado == "sin_vapid" and resultado.como_respuesta() == {"estado": "sin_vapid"}
    assert fake_upstash.commands == [] and fuente.calls == [] and push.llamadas == []  # nothing sent, nothing deleted


def test_cargar_vapid_returns_none_when_the_self_test_fails_and_the_key_when_it_passes(vapid_efimera, monkeypatch) -> None:
    assert despacho.cargar_vapid() is not None
    monkeypatch.setattr(envio, "autoprueba_de_cifrado", lambda: False)
    assert despacho.cargar_vapid() is None


async def test_gone_ids_are_recorded_as_reached_even_when_the_breaker_kept_them(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 8, 5)
    await correr(redis)
    assert hechos_de(fake_upstash) == set(ids)  # nothing to send them: the next run does not try them again
    del fake_upstash.strings[CLAVE_LOCK]
    antes = len(push.llamadas)
    segunda = await correr(redis)
    assert len(push.llamadas) == antes and segunda.envio == despacho.ResumenEnvio(ya_avisadas=1)


async def test_deletions_left_waiting_by_an_aborted_zone_are_decided_at_the_end_of_the_run(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    """A zone whose dispatch blows up after it tripped the breaker never reaches its own close: the end of the run does."""
    tormenta_en(install, "cordoba", "rosario")
    a = await _zona_con_vencidas(redis, push, "cordoba", 2, 2)
    b = await _zona_con_vencidas(redis, push, "rosario", 2, 2)
    original = despacho.DisyuntorDeBajas.cerrar_zona
    llamadas: list[int] = []

    async def cerrar_zona_que_revienta_la_segunda(self, redis_, *args):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise RuntimeError("bug")
        return await original(self, redis_, *args)

    monkeypatch.setattr(despacho.DisyuntorDeBajas, "cerrar_zona", cerrar_zona_que_revienta_la_segunda)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in a + b)  # four of four gone: the breaker held
    assert resultado.errores == 1 and resultado.envio.vencidos == 0 and resultado.envio.fallidos == 2


async def test_the_share_of_a_zone_grows_when_the_zones_before_it_finish_early(
    redis, fake_upstash, install, push, monkeypatch, reloj_del_bucle
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 100)
    tormenta_en(install, "cordoba", "rosario", "mendoza")
    await registrar(redis, "cordoba", 40)
    await registrar(redis, "rosario", 40)
    await registrar(redis, "mendoza", 5)
    push.bucle, push.avance = reloj_del_bucle, 1  # a batch takes 10 s
    resultado = await correr(redis)
    # cordoba: 100 * 40 / 85 = 47 s, uses 40. rosario: the 60 s left shared with the 45 still to send = 53 s, uses 40.
    # If the zones already done kept weighing in the division, rosario would get 60 * 40 / 85 = 28 s and stop at 30 sends.
    assert resultado.envio == despacho.ResumenEnvio(avisadas=3, enviados=85)


async def test_a_run_cut_while_evaluating_does_not_even_read_who_was_reached(redis, fake_upstash, install, push) -> None:
    fuente = tormenta_en(install, "cordoba", "rosario")
    await registrar(redis, "cordoba", 2)
    await registrar(redis, "rosario", 1)
    base = fuente._respond

    def respuesta_que_apaga(params):
        fake_upstash.strings[CLAVE_APAGADO] = "1"
        return base(params)

    fuente._respond = respuesta_que_apaga
    fake_upstash.commands.clear()
    resultado = await correr(redis)
    # both zones were evaluated (no per-zone read of the kill key) and both found a storm: their 3 subscribers are deferred
    assert resultado.estado == "apagado_a_mitad" and resultado.envio == despacho.ResumenEnvio(diferidos=3)
    assert not [c for c in fake_upstash.commands if c[0] == "SMEMBERS" and c[1].startswith("alertas:enviado:")]
    assert push.llamadas == []


# --- final fix: the deferred deletions obey the kill switch, outages and the deadline ----------------------------------------


def borrados(fake_upstash) -> list[list[str]]:
    """The commands that remove a subscription or its index entries."""
    return [c for c in fake_upstash.commands if c[0] in ("DEL", "SREM")]


async def test_a_kill_key_set_mid_run_drops_the_deferred_deletions_of_the_zone(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 25, 1)  # one gone id; the breaker is far from tripping

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"

    push.al_llamar = apagar
    fake_upstash.commands.clear()
    resultado = await correr(redis)
    assert resultado.estado == "apagado_a_mitad"
    assert f"alertas:sub:{ids[0]}" in fake_upstash.strings and borrados(fake_upstash) == []
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 1  # kept: counted as failed, not as gone


async def test_a_kill_key_set_mid_run_also_drops_what_the_end_of_the_run_would_delete(
    redis, fake_upstash, install, push, monkeypatch
) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 25, 1)

    async def cierre_de_zona_que_no_decide(self, redis_, plazo=None, detenido=False):
        return 0  # the zone close never decides: only the close of the run does

    monkeypatch.setattr(despacho.DisyuntorDeBajas, "cerrar_zona", cierre_de_zona_que_no_decide)

    def apagar(n: int) -> None:
        if n == 10:
            fake_upstash.strings[CLAVE_APAGADO] = "1"

    push.al_llamar = apagar
    fake_upstash.commands.clear()
    resultado = await correr(redis)
    assert f"alertas:sub:{ids[0]}" in fake_upstash.strings and borrados(fake_upstash) == []
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 1


async def test_an_unreadable_kill_key_drops_the_deferred_deletions_too(fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    ids = await _zona_con_vencidas(base, push, "cordoba", 25, 1)
    fake_upstash.commands.clear()
    resultado = await correr(LecturaQueSeRompe(buenas=2))
    assert f"alertas:sub:{ids[0]}" in fake_upstash.strings and borrados(fake_upstash) == []
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 1


async def test_an_upstash_outage_during_the_deferred_deletions_stops_at_the_first_failure(
    fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    base = UpstashRedis(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN)
    ids = await _zona_con_vencidas(base, push, "cordoba", 20, 0)
    gone = ids[:3] + ids[10:13]  # six gone out of twenty, three per batch: healthy, all of them to be deleted
    for sub_id in gone:
        push.resultados[sub_id] = [Resultado.VENCIDA]
    intentos: list[str] = []

    class SinBorrado(UpstashRedis):
        async def delete(self, key: str) -> int:
            intentos.append(key)
            raise UpstashUnavailableError("caido")

    resultado = await correr(SinBorrado(FAKE_UPSTASH_URL, FAKE_UPSTASH_TOKEN))
    assert len(intentos) == 1  # no more Upstash calls after the first failure
    assert all(f"alertas:sub:{i}" in fake_upstash.strings for i in gone)
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 6  # kept for a later run


async def test_deferred_deletions_are_not_started_once_the_run_deadline_has_passed(
    redis, fake_upstash, install, push, monkeypatch, reloj_del_bucle
) -> None:
    monkeypatch.setattr(settings, "alertas_plazo_corrida_segundos", 100)
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 8, 1)  # one batch, healthy
    push.bucle, push.avance = reloj_del_bucle, 20  # the batch takes 160 s of a 100 s deadline
    fake_upstash.commands.clear()
    resultado = await correr(redis)
    assert f"alertas:sub:{ids[0]}" in fake_upstash.strings and borrados(fake_upstash) == []
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 1


async def test_with_no_kill_no_outage_and_time_left_the_deferred_deletions_still_happen(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 20, 2)
    resultado = await correr(redis)
    assert all(f"alertas:sub:{i}" not in fake_upstash.strings for i in ids[:2])
    assert resultado.envio.vencidos == 2 and resultado.envio.fallidos == 0


# --- hardening: an absolute cap of deletions per run (S1) ---------------------------------------------------------------


async def _zona_con_bajas_repartidas(redis, push, slug: str, total: int, por_lote: int = 5) -> tuple[list[str], list[str]]:
    """A zone of `total` ids where the first `por_lote` of every batch of 10 are gone. Half of a batch or less is gone, so
    the proportional breaker stays closed and only the absolute cap can stop the deletions."""
    ids = sorted(await registrar(redis, slug, total))
    gone = [i for n, i in enumerate(ids) if n % despacho.ENVIOS_POR_LOTE < por_lote]
    for sub_id in gone:
        push.resultados[sub_id] = [Resultado.VENCIDA]
    return ids, gone


def _con_registro(fake_upstash, ids: list[str]) -> list[str]:
    return [i for i in ids if f"alertas:sub:{i}" in fake_upstash.strings]


def test_the_cap_of_deletions_per_run_is_25() -> None:
    assert despacho.MAX_BAJAS_POR_CORRIDA == 25


async def test_past_the_cap_no_more_gone_subscriptions_are_deleted_and_the_rest_count_as_failed(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    _, gone = await _zona_con_bajas_repartidas(redis, push, "cordoba", 60)  # 30 gone, never more than half of a batch
    assert len(gone) == 30
    resultado = await correr(redis)
    assert _con_registro(fake_upstash, gone) == gone[25:]  # the first 25 were deleted, the other 5 wait for a later run
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=30, vencidos=25, fallidos=5)
    assert all(g in fake_upstash.sets["alertas:ids"] for g in gone[25:])  # still indexed: they will be tried again


async def test_exactly_the_cap_of_gone_subscriptions_are_all_deleted(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    _, gone = await _zona_con_bajas_repartidas(redis, push, "cordoba", 50)  # 25 gone
    resultado = await correr(redis)
    assert len(gone) == 25 and _con_registro(fake_upstash, gone) == []
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=25, vencidos=25)


async def test_the_cap_is_shared_by_all_the_zones_of_the_run(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba", "rosario")
    _, gone_a = await _zona_con_bajas_repartidas(redis, push, "cordoba", 40)  # 20 gone
    _, gone_b = await _zona_con_bajas_repartidas(redis, push, "rosario", 20)  # 10 gone: 30 in the run, each zone under 25
    resultado = await correr(redis)
    assert len(_con_registro(fake_upstash, gone_a + gone_b)) == 5
    assert resultado.envio.vencidos == 25 and resultado.envio.fallidos == 5 and resultado.envio.enviados == 30


async def test_the_deletions_dropped_by_the_cap_are_done_by_the_next_run(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    _, gone = await _zona_con_bajas_repartidas(redis, push, "cordoba", 60)
    await correr(redis)
    del fake_upstash.strings[CLAVE_LOCK]
    fake_upstash.sets.pop(CLAVE_ENVIADOS_HOY)  # the cap counts per run: a new run starts again from zero
    resultado = await correr(redis)
    assert _con_registro(fake_upstash, gone) == [] and resultado.envio.vencidos == 5


async def test_the_breaker_by_proportion_still_wins_below_the_cap(redis, fake_upstash, install, push) -> None:
    tormenta_en(install, "cordoba")
    ids = await _zona_con_vencidas(redis, push, "cordoba", 20, 12)  # 12 of 20 gone: far fewer than the cap, but over half
    resultado = await correr(redis)
    assert len(_con_registro(fake_upstash, ids)) == 20
    assert resultado.envio.vencidos == 0 and resultado.envio.fallidos == 12


async def test_the_breaker_counts_each_deletion_that_was_made_against_the_cap(redis) -> None:
    ids = sorted(await registrar(redis, "cordoba", 26))
    disyuntor = despacho.DisyuntorDeBajas()
    disyuntor.registrar(100, 26)  # healthy as a whole: 26 gone out of 100
    disyuntor.diferir("cordoba", ids)
    assert await disyuntor.cerrar_corrida(redis) == 1  # 25 deleted, the 26th is dropped
    assert disyuntor.borradas == 25


async def test_a_run_that_deleted_the_cap_drops_everything_that_comes_later(redis) -> None:
    ids = sorted(await registrar(redis, "cordoba", 28))
    disyuntor = despacho.DisyuntorDeBajas()
    disyuntor.registrar(100, 28)
    disyuntor.diferir("cordoba", ids[:25])
    assert await disyuntor.cerrar_zona(redis) == 0 and disyuntor.borradas == 25
    disyuntor.diferir("cordoba", ids[25:])
    assert await disyuntor.cerrar_corrida(redis) == 3 and disyuntor.borradas == 25


# --- hardening: a doubtful read is not an absent record (S2) -----------------------------------------------------------


async def test_a_doubtful_record_read_is_a_failure_not_an_expired_id_and_nothing_is_cleaned(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 3))
    dudoso = RedisConLecturaDudosa(solo=ids[0])  # a 200 without `result` for ONE record
    resultado = await correr(dudoso)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2, fallidos=1)
    assert push.a(ids[0]) == []
    assert f"alertas:sub:{ids[0]}" in fake_upstash.strings  # the record is still there
    assert ids[0] in fake_upstash.sets["alertas:ids"] and ids[0] in fake_upstash.sets["alertas:zona:cordoba"]
    assert ids[0] not in hechos_de(fake_upstash)  # not marked as reached
    del fake_upstash.strings[CLAVE_LOCK]
    otra = await correr(redis)  # the next run, with Upstash healthy, delivers it
    assert otra.envio == despacho.ResumenEnvio(avisadas=1, enviados=1) and push.a(ids[0])


async def test_a_doubtful_second_read_while_cleaning_an_absent_record_keeps_the_id_and_counts_as_failed(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 3))
    del fake_upstash.strings[f"alertas:sub:{ids[0]}"]  # confirmed absent by the first read
    dudoso = RedisConLecturaDudosa(solo=ids[0], normales=1)  # ...but the re-read before cleaning is doubtful
    resultado = await correr(dudoso)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2, fallidos=1)
    assert ids[0] in fake_upstash.sets["alertas:ids"] and ids[0] in fake_upstash.sets["alertas:zona:cordoba"]
    assert ids[0] not in hechos_de(fake_upstash)


async def test_a_confirmed_absent_record_is_still_cleaned_even_if_the_index_cleanup_fails(
    redis, fake_upstash, install, push
) -> None:
    tormenta_en(install, "cordoba")
    ids = sorted(await registrar(redis, "cordoba", 3))
    del fake_upstash.strings[f"alertas:sub:{ids[0]}"]
    resultado = await correr(RedisConFalla("SREM"))  # the record IS gone; only the cleanup of the indexes fails
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2, vencidos=1)
    assert ids[0] in hechos_de(fake_upstash)
