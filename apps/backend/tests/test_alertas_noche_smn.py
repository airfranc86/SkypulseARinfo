"""The night rule of the official SMN alerts (FRA-359, T5, S7): `avisos_smn.se_omite_de_noche`.

The SMN run works 24 h, but from 22 to 5 h in Argentina (the same silence the forecast reviews keep,
`umbrales.SILENCIO_DESDE_H` / `SILENCIO_HASTA_H`) only the RED alerts go out. An amarillo or naranja alert found in
that stretch is omitted: not sent, not marked, counted as `smn_omitidas`, and sent by the first run from 5:00 on if it
is still in force (an omitted alert that expires before 5:00 is never sent). A red alert is sent at any hour. The
decision is the owner's (L5, L7); the start of the silence is not a cut of the run (that is the forecast's) but a
filter per pair.

Three layers: the pure function (a 24 h × 3 levels table, the exact borders, the time zone of `ahora`), the run
`evaluar_avisos_smn` with the real plug (what is sent, read and marked, run after run), and the HTTP mode
`{"modo":"smn"}` with its response and its log line. Upstash, the SMN feed and the sender are fakes.
"""
from __future__ import annotations

import inspect
import logging
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.upstash import UpstashRedis
from app.routers import alertas as router_alertas
from app.services.alertas import avisos_smn, despacho, envio, evaluacion, regla, umbrales
from app.services.alertas.envio import tag_smn, topic_smn
from app.services.alertas.mensajes_smn import texto_aviso_smn
from app.services.smn_alertas import clave_dedupe
from tests.alertas_helpers import (  # noqa: F401  (fixtures are used by name)
    AR,
    CLAVE_APAGADO,
    CLAVE_LOCK_SMN,
    envio_activo,
    esperas,
    estado_de_alertas_limpio,
    lineas_de_resumen,
    lineas_de_resumen_smn,
    redis,
    registrar,
    reloj_de_openmeteo,
)
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.test_alertas_avisos_smn import (  # noqa: F401  (`push` and `_entorno` are fixtures)
    CORDOBA,
    _entorno,
    alerta,
    avisos_por_zona,
    conjuntos_smn,
    push,
)
from tests.test_alertas_evaluar_smn import (  # noqa: F401
    CERO_ENVIO,
    CERO_SMN,
    LINEA_SMN_ENVIADA,
    RESPUESTA_SMN_ENVIADA,
    feed,
    llamar_smn,
    open_meteo_prohibido,
)

pytestmark = pytest.mark.integration

UTC = timezone.utc
TOKIO = timezone(timedelta(hours=9))  # any other zone: the rule reads the hour in Argentina, not the zone of `ahora`

# The hours of the night in Argentina (22:00:00 up to, not including, 05:00:00), written by hand: not read from the code.
HORAS_DE_NOCHE = frozenset({22, 23, 0, 1, 2, 3, 4})
HORAS_DE_DIA = frozenset(range(24)) - HORAS_DE_NOCHE
NIVELES = ("amarillo", "naranja", "rojo")

# One night of October 2026 (Wednesday 14 to Thursday 15), in Argentina.
NOCHE = datetime(2026, 10, 14, 23, 30, tzinfo=AR)
MADRUGADA = datetime(2026, 10, 15, 2, 30, tzinfo=AR)
MANANA = datetime(2026, 10, 15, 5, 0, tzinfo=AR)  # the first run from 5:00 on
DESDE_ANOCHE = datetime(2026, 10, 14, 20, 0, tzinfo=AR)
HASTA_MEDIODIA = datetime(2026, 10, 15, 12, 0, tzinfo=AR)

# Alerts in force across the whole night (published at 20 h, until noon of the next day).
AMARILLO_NOCTURNO = alerta(fecha_desde=DESDE_ANOCHE, fecha_hasta=HASTA_MEDIODIA)
NARANJA_NOCTURNO = alerta(nivel="naranja", severidad="Severe", fecha_desde=DESDE_ANOCHE, fecha_hasta=HASTA_MEDIODIA)
ROJO_NOCTURNO = alerta(nivel="rojo", severidad="Extreme", fecha_desde=DESDE_ANOCHE, fecha_hasta=HASTA_MEDIODIA)
# An alert that expires at 4:00: omitted at night and expired by the time the silence ends.
AMARILLO_QUE_VENCE_DE_MADRUGADA = alerta(fecha_desde=DESDE_ANOCHE, fecha_hasta=datetime(2026, 10, 15, 4, 0, tzinfo=AR))
# L8: published at 23 h, in force from 7 h (the text of T2 says "Rige desde las 7 h").
AMARILLO_DESDE_LAS_7 = alerta(fecha_desde=datetime(2026, 10, 15, 7, 0, tzinfo=AR), fecha_hasta=HASTA_MEDIODIA)

ENVIADOS_AMARILLO_NOCTURNO = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", AMARILLO_NOCTURNO))
ENVIADOS_ROJO_NOCTURNO = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", ROJO_NOCTURNO))
ENVIADOS_DESDE_LAS_7 = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", AMARILLO_DESDE_LAS_7))

# TTLs computed by hand (not by the code under test). The push TTL is capped at the usual 12 h; the done-set outlives
# `fecha_hasta` by 36 h.
TTL_PUSH_A_LAS_5 = 7 * 3600  # 05:00 -> 12:00, under 12 h
TTL_ENVIADOS_A_LAS_5 = 7 * 3600 + 36 * 3600
TTL_PUSH_A_LAS_2330 = 12 * 3600  # 23:30 -> 12:00 is 12 h 30 min: capped
TTL_ENVIADOS_A_LAS_2330 = 12 * 3600 + 30 * 60 + 36 * 3600

RESPUESTA_SMN_OMITIDA = {"estado": "evaluada", **CERO_SMN, "smn_avisos": 1, "smn_omitidas": 1, **CERO_ENVIO}
LINEA_SMN_OMITIDA = (
    "alertas: smn evaluation estado=evaluada smn_sin_datos=0 smn_avisos=1 smn_avisadas=0 smn_ya_avisadas=0 "
    "smn_omitidas=1 smn_errores=0 avisadas=0 ya_avisadas=0 enviados=0 vencidos=0 fallidos=0 diferidos=0 reintentadas=0"
)


def a_la_hora(hora: int, minuto: int = 0, segundo: int = 0, *, dia: int = 14) -> datetime:
    return datetime(2026, 10, dia, hora, minuto, segundo, tzinfo=AR)


async def correr(redis: UpstashRedis, ahora: datetime, *alertas, **kwargs) -> avisos_smn.ResultadoSmn:
    """A run that SENDS the given alerts over Córdoba at `ahora`, with the REAL night rule (nothing injected)."""
    kwargs.setdefault("vapid", object())
    return await avisos_smn.evaluar_avisos_smn(
        redis, ahora, obtener_avisos=avisos_por_zona({"cordoba": list(alertas)}), **kwargs
    )


def reloj_del_router(monkeypatch: pytest.MonkeyPatch, momento: datetime) -> None:
    """The router's clock pinned at `momento` (given in Argentina, handed over in UTC like the real clock)."""
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: momento.astimezone(UTC))


# ---------------------------------------------------------------------------
# [S7] The pure rule: every hour of the day in Argentina × the three levels
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hora", sorted(range(24)))
@pytest.mark.parametrize("nivel", NIVELES)
def test_from_22_to_5_in_argentina_only_the_red_alert_goes_out_at_any_other_hour_every_level_does(
    hora: int, nivel: str
) -> None:
    esperado = hora in HORAS_DE_NOCHE and nivel != "rojo"
    for minuto in (0, 30, 59):
        assert avisos_smn.se_omite_de_noche(alerta(nivel=nivel), a_la_hora(hora, minuto)) is esperado


def test_the_exact_borders_21_59_59_sends_22_00_00_omits_4_59_59_omits_and_5_00_00_sends() -> None:
    bordes = [
        (a_la_hora(21, 59, 59), False),
        (a_la_hora(22, 0, 0), True),
        (a_la_hora(4, 59, 59, dia=15), True),
        (a_la_hora(5, 0, 0, dia=15), False),
    ]
    for momento, omitido in bordes:
        assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, momento) is omitido, momento
        assert avisos_smn.se_omite_de_noche(NARANJA_NOCTURNO, momento) is omitido, momento
        assert avisos_smn.se_omite_de_noche(ROJO_NOCTURNO, momento) is False, momento  # red: never omitted
    # Sub-second precision does not move the border either.
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, a_la_hora(21, 59, 59).replace(microsecond=999_999)) is False
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, a_la_hora(4, 59, 59, dia=15).replace(microsecond=999_999))


def test_the_rule_reads_the_hour_in_argentina_whatever_the_zone_of_ahora() -> None:
    for hora in range(24):
        for nivel in NIVELES:
            en_ar = a_la_hora(hora, 30)
            esperado = avisos_smn.se_omite_de_noche(alerta(nivel=nivel), en_ar)
            assert avisos_smn.se_omite_de_noche(alerta(nivel=nivel), en_ar.astimezone(UTC)) is esperado, (hora, nivel)
            assert avisos_smn.se_omite_de_noche(alerta(nivel=nivel), en_ar.astimezone(TOKIO)) is esperado, (hora, nivel)
    # 02:30 UTC is 23:30 in Argentina (night); 02:30 in Argentina is 05:30 UTC (night too, read in Argentina).
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, datetime(2026, 10, 15, 2, 30, tzinfo=UTC)) is True
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, datetime(2026, 10, 15, 8, 30, tzinfo=UTC)) is False  # 5:30 AR


def test_a_naive_ahora_is_refused_with_the_error_of_the_module_for_every_level() -> None:
    for nivel in ("amarillo", "naranja", "rojo", "otro"):
        with pytest.raises(ValueError, match="ahora necesita zona horaria"):
            avisos_smn.se_omite_de_noche(alerta(nivel=nivel), datetime(2026, 10, 14, 23, 30))
        with pytest.raises(ValueError, match="ahora necesita zona horaria"):
            avisos_smn.se_omite_de_noche(alerta(nivel=nivel), datetime(2026, 10, 14, 13, 0))


def test_the_level_otro_never_gets_here_but_does_not_raise_it_is_treated_as_not_red() -> None:
    assert avisos_smn.se_omite_de_noche(alerta(nivel="otro"), NOCHE) is True
    assert avisos_smn.se_omite_de_noche(alerta(nivel="otro"), a_la_hora(13)) is False
    assert avisos_smn.se_omite_de_noche(alerta(nivel="ROJO"), NOCHE) is True  # the level is exact, as everywhere else


# ---------------------------------------------------------------------------
# The hours and the level are the owner's constants, not numbers of this module
# ---------------------------------------------------------------------------


def test_the_night_is_the_silence_of_the_forecast_reviews_from_umbrales(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (umbrales.SILENCIO_DESDE_H, umbrales.SILENCIO_HASTA_H) == (22, 5)
    assert umbrales.SMN_NIVEL_QUE_PASA_DE_NOCHE == "rojo"
    # Moving the owner's constants moves the rule: it reads them, it does not repeat them.
    monkeypatch.setattr(umbrales, "SILENCIO_HASTA_H", 7)
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, a_la_hora(6, 30)) is True
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, a_la_hora(7, 0)) is False
    monkeypatch.setattr(umbrales, "SILENCIO_DESDE_H", 21)
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, a_la_hora(21, 0)) is True
    assert avisos_smn.se_omite_de_noche(AMARILLO_NOCTURNO, a_la_hora(20, 59, 59)) is False
    monkeypatch.setattr(umbrales, "SMN_NIVEL_QUE_PASA_DE_NOCHE", "naranja")
    assert avisos_smn.se_omite_de_noche(NARANJA_NOCTURNO, NOCHE) is False
    assert avisos_smn.se_omite_de_noche(ROJO_NOCTURNO, NOCHE) is True


def test_the_night_of_the_smn_rule_and_the_silence_of_the_forecast_agree_hour_by_hour_and_on_the_borders() -> None:
    """`regla.ventana` has no window in the silence and `segundos_hasta_el_silencio` reaches 0 at 22:00:00: the SMN
    rule must call the same hours "night", so the two never disagree about a border. Both forecast functions keep
    their previous behaviour (pinned here, they are not touched by T5)."""
    for hora in range(24):
        momento = a_la_hora(hora, 0)
        if avisos_smn.es_de_noche(momento):
            assert hora in HORAS_DE_NOCHE and regla.ventana(momento) is None, hora
        else:
            assert hora in HORAS_DE_DIA, hora
    for hora_de_revision in (*umbrales.REVISIONES_HOY, umbrales.REVISION_MANANA):
        assert avisos_smn.es_de_noche(a_la_hora(hora_de_revision)) is False
    assert regla.ventana(a_la_hora(21, 59, 59)) is not None and regla.ventana(a_la_hora(22, 0, 0)) is None
    assert regla.ventana(a_la_hora(4, 59, 59, dia=15)) is None and regla.ventana(a_la_hora(5, 0, 0, dia=15)) is not None
    assert despacho.segundos_hasta_el_silencio(a_la_hora(21, 59, 59)) == 1.0
    assert despacho.segundos_hasta_el_silencio(a_la_hora(22, 0, 0)) == 0.0
    assert avisos_smn.es_de_noche(a_la_hora(21, 59, 59)) is False and avisos_smn.es_de_noche(a_la_hora(22, 0, 0)) is True
    with pytest.raises(ValueError, match="ahora necesita zona horaria"):
        avisos_smn.es_de_noche(datetime(2026, 10, 14, 23, 30))


def test_the_run_uses_the_real_rule_by_default_the_plug_of_t3_is_the_same() -> None:
    assert inspect.signature(avisos_smn.evaluar_avisos_smn).parameters["omitir"].default is avisos_smn.se_omite_de_noche
    assert "omitir" not in inspect.signature(evaluacion.evaluar_smn).parameters  # T4 does not override it


# ---------------------------------------------------------------------------
# [S7] The run: a yellow alert at night is omitted, then sent from 5:00; a red one goes out at night
# ---------------------------------------------------------------------------


async def test_a_yellow_alert_at_night_is_omitted_counted_and_neither_read_sent_nor_marked(
    redis, fake_upstash, push
) -> None:
    await registrar(redis, "cordoba", 2)
    for momento in (NOCHE, MADRUGADA):
        fake_upstash.commands.clear()
        resultado = await correr(redis, momento, AMARILLO_NOCTURNO)

        assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1), momento
        assert resultado.envio == despacho.ResumenEnvio() and resultado.corte is None
        assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
        assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]  # only the index: no members, no done-set
        assert not [k for k in fake_upstash.sets if k.startswith("alertas:enviado:")]


async def test_the_alert_omitted_at_night_is_sent_and_marked_by_the_first_run_from_5_00_on(
    redis, fake_upstash, push
) -> None:
    ids = await registrar(redis, "cordoba", 2)
    assert (await correr(redis, NOCHE, AMARILLO_NOCTURNO)).smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1)
    assert (await correr(redis, MADRUGADA, AMARILLO_NOCTURNO)).smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1)
    assert push.llamadas == []
    fake_upstash.commands.clear()
    resultado = await correr(redis, MANANA, AMARILLO_NOCTURNO)

    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2) and resultado.corte is None
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    clave = clave_dedupe("cordoba", AMARILLO_NOCTURNO)
    for llamada in push.llamadas:
        assert llamada.payload["body"] == "Aviso oficial de nivel amarillo por tormentas, ya vigente. Fuente: SMN"
        assert llamada.payload["title"] == "SkyPulse · Córdoba" and llamada.payload["tag"] == tag_smn(clave)
        assert llamada.topic == topic_smn(clave) and llamada.ttl == TTL_PUSH_A_LAS_5 and llamada.zona == "cordoba"
    assert conjuntos_smn(fake_upstash) == [ENVIADOS_AMARILLO_NOCTURNO]
    assert fake_upstash.sets[ENVIADOS_AMARILLO_NOCTURNO] == set(ids)
    assert ["EXPIRE", ENVIADOS_AMARILLO_NOCTURNO, str(TTL_ENVIADOS_A_LAS_5), "NX"] in fake_upstash.commands
    assert fake_upstash.ttls[ENVIADOS_AMARILLO_NOCTURNO] == TTL_ENVIADOS_A_LAS_5
    # And once sent, the next run of the day knows it (the omission never touched the dedupe).
    otra = await correr(redis, MANANA + timedelta(minutes=30), AMARILLO_NOCTURNO)
    assert otra.smn == despacho.ResumenSmn(smn_avisos=1, smn_ya_avisadas=1) and len(push.llamadas) == 2


async def test_a_red_alert_at_night_is_sent_and_marked_like_any_other_hour(redis, fake_upstash, push) -> None:
    ids = await registrar(redis, "cordoba", 2)
    fake_upstash.commands.clear()
    resultado = await correr(redis, NOCHE, ROJO_NOCTURNO)

    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2) and resultado.corte is None
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    clave = clave_dedupe("cordoba", ROJO_NOCTURNO)
    for llamada in push.llamadas:
        assert llamada.payload["body"] == "Aviso oficial de nivel rojo por tormentas, ya vigente. Fuente: SMN"
        assert llamada.payload["tag"] == tag_smn(clave) and llamada.topic == topic_smn(clave)
        assert llamada.ttl == TTL_PUSH_A_LAS_2330
    assert conjuntos_smn(fake_upstash) == [ENVIADOS_ROJO_NOCTURNO]
    assert fake_upstash.sets[ENVIADOS_ROJO_NOCTURNO] == set(ids)
    assert ["EXPIRE", ENVIADOS_ROJO_NOCTURNO, str(TTL_ENVIADOS_A_LAS_2330), "NX"] in fake_upstash.commands
    assert fake_upstash.ttls[ENVIADOS_ROJO_NOCTURNO] == TTL_ENVIADOS_A_LAS_2330
    # At 2:30 it is already sent; nothing new goes out.
    segunda = await correr(redis, MADRUGADA, ROJO_NOCTURNO)
    assert segunda.smn == despacho.ResumenSmn(smn_avisos=1, smn_ya_avisadas=1) and len(push.llamadas) == 2


async def test_a_red_and_a_yellow_alert_over_the_same_zone_at_night_only_the_red_one_goes_out(
    redis, fake_upstash, push
) -> None:
    ids = await registrar(redis, "cordoba", 2)
    resultado = await correr(redis, MADRUGADA, AMARILLO_NOCTURNO, ROJO_NOCTURNO)

    assert resultado.smn == despacho.ResumenSmn(smn_avisos=2, smn_avisadas=1, smn_omitidas=1)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert {c.topic for c in push.llamadas} == {topic_smn(clave_dedupe("cordoba", ROJO_NOCTURNO))}
    assert conjuntos_smn(fake_upstash) == [ENVIADOS_ROJO_NOCTURNO]


async def test_an_alert_omitted_at_night_that_expires_before_5_00_is_never_sent(redis, fake_upstash, push) -> None:
    await registrar(redis, "cordoba", 2)
    assert (await correr(redis, NOCHE, AMARILLO_QUE_VENCE_DE_MADRUGADA)).smn == despacho.ResumenSmn(
        smn_avisos=1, smn_omitidas=1
    )
    assert (await correr(redis, MADRUGADA, AMARILLO_QUE_VENCE_DE_MADRUGADA)).smn == despacho.ResumenSmn(
        smn_avisos=1, smn_omitidas=1
    )
    fake_upstash.commands.clear()
    resultado = await correr(redis, MANANA, AMARILLO_QUE_VENCE_DE_MADRUGADA)

    assert resultado.smn == despacho.ResumenSmn()  # expired: not even a pair (T1's filter), so nothing to omit
    assert resultado.envio == despacho.ResumenEnvio()
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]


async def test_a_yellow_alert_published_at_23_h_in_force_from_7_h_is_omitted_at_night_and_sent_at_5_00_saying_since_when(
    redis, fake_upstash, push
) -> None:
    """L8: an alert with a future start is sent as soon as it is published, and the night rule only delays it."""
    ids = await registrar(redis, "cordoba", 2)
    de_noche = await correr(redis, a_la_hora(23, 0), AMARILLO_DESDE_LAS_7)
    assert de_noche.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1)
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    resultado = await correr(redis, MANANA, AMARILLO_DESDE_LAS_7)

    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert resultado.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    for llamada in push.llamadas:
        assert llamada.payload["body"] == "Aviso oficial de nivel amarillo por tormentas. Rige desde las 7 h. Fuente: SMN"
        assert llamada.payload["body"] == texto_aviso_smn(CORDOBA, AMARILLO_DESDE_LAS_7, ahora=MANANA).cuerpo
        assert llamada.ttl == TTL_PUSH_A_LAS_5
    assert conjuntos_smn(fake_upstash) == [ENVIADOS_DESDE_LAS_7]
    assert fake_upstash.sets[ENVIADOS_DESDE_LAS_7] == set(ids)
    assert fake_upstash.ttls[ENVIADOS_DESDE_LAS_7] == TTL_ENVIADOS_A_LAS_5


async def test_the_dry_run_at_night_counts_the_pairs_and_omits_nothing_as_in_t3(redis, fake_upstash, push) -> None:
    """Pinned, not decided here: a dry run (`vapid=None`) returns before the night rule is consulted (T3), so at night
    it answers `smn_avisos=1 smn_omitidas=0`. If the owner wants the dry-run line to show the omissions, this is the
    test to change."""
    await registrar(redis, "cordoba", 2)
    fake_upstash.commands.clear()
    resultado = await correr(redis, NOCHE, AMARILLO_NOCTURNO, vapid=None)

    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1) and resultado.envio == despacho.ResumenEnvio()
    assert push.llamadas == [] and fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]


async def test_the_injected_rule_of_the_tests_still_wins_over_the_real_one(redis, fake_upstash, push) -> None:
    """T3's plug keeps working: `omitir=` replaces the real rule (a yellow alert at night goes out when told so)."""
    ids = await registrar(redis, "cordoba", 2)
    resultado = await correr(redis, NOCHE, AMARILLO_NOCTURNO, omitir=lambda alerta_, ahora: False)

    assert resultado.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)


# ---------------------------------------------------------------------------
# [S2 + S7] Through HTTP: the SMN mode at night answers and logs `smn_omitidas`, and sends from 5:00
# ---------------------------------------------------------------------------


async def test_the_smn_mode_at_night_omits_the_yellow_alert_answers_and_logs_smn_omitidas_and_sends_it_from_5_00(
    async_client: AsyncClient, alertas_redis, fake_upstash, push, feed, open_meteo_prohibido, monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ids = await registrar(alertas_redis, "cordoba", 2)
    feed.obtener = avisos_por_zona({"cordoba": [AMARILLO_NOCTURNO]})

    for momento in (NOCHE, MADRUGADA):
        fake_upstash.strings.pop(CLAVE_LOCK_SMN, None)  # the lock of the previous run expired
        fake_upstash.commands.clear()
        caplog.clear()
        reloj_del_router(monkeypatch, momento)
        response = await llamar_smn(async_client)

        assert response.status_code == 200 and response.json() == RESPUESTA_SMN_OMITIDA, momento
        assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
        valor = fake_upstash.strings[CLAVE_LOCK_SMN]
        assert fake_upstash.commands == [  # the switch, the lock and the index: nothing else is read or written
            ["GET", CLAVE_APAGADO],
            ["SET", CLAVE_LOCK_SMN, valor, "NX", "EX", str(fake_upstash.ttls[CLAVE_LOCK_SMN])],
            ["SMEMBERS", "alertas:zonas"],
        ]
        lineas = lineas_de_resumen_smn(caplog)
        assert [(r.levelno, r.getMessage()) for r in lineas] == [(logging.INFO, LINEA_SMN_OMITIDA)], momento
        assert lineas_de_resumen(caplog) == []
        assert open_meteo_prohibido.calls == []

    fake_upstash.strings.pop(CLAVE_LOCK_SMN, None)
    caplog.clear()
    reloj_del_router(monkeypatch, MANANA)
    response = await llamar_smn(async_client)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert fake_upstash.sets[ENVIADOS_AMARILLO_NOCTURNO] == set(ids)
    assert fake_upstash.ttls[ENVIADOS_AMARILLO_NOCTURNO] == TTL_ENVIADOS_A_LAS_5
    assert [(r.levelno, r.getMessage()) for r in lineas_de_resumen_smn(caplog)] == [(logging.INFO, LINEA_SMN_ENVIADA)]
    assert [a for a, _ in feed.llamadas] == [m.astimezone(UTC) for m in (NOCHE, MADRUGADA, MANANA)]
    assert open_meteo_prohibido.calls == []


async def test_the_smn_mode_at_night_sends_a_red_alert(
    async_client: AsyncClient, alertas_redis, fake_upstash, push, feed, open_meteo_prohibido, monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ids = await registrar(alertas_redis, "cordoba", 2)
    feed.obtener = avisos_por_zona({"cordoba": [ROJO_NOCTURNO]})
    reloj_del_router(monkeypatch, MADRUGADA)
    response = await llamar_smn(async_client)

    assert response.status_code == 200 and response.json() == RESPUESTA_SMN_ENVIADA
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert all("rojo" in c.payload["body"] for c in push.llamadas)
    assert conjuntos_smn(fake_upstash) == [ENVIADOS_ROJO_NOCTURNO]
    assert fake_upstash.sets[ENVIADOS_ROJO_NOCTURNO] == set(ids)
    assert [(r.levelno, r.getMessage()) for r in lineas_de_resumen_smn(caplog)] == [(logging.INFO, LINEA_SMN_ENVIADA)]
    assert open_meteo_prohibido.calls == []


def test_the_push_ttl_cap_the_tests_compute_by_hand_is_the_usual_one() -> None:
    assert envio.TTL_ALERTA_SEGUNDOS == 12 * 3600 and despacho.ENVIADOS_TTL_SEGUNDOS == 36 * 3600
