"""T5 (FRA-359, S7): the night rule of the SMN alerts checked against a reference written from the spec, not from the code
nor from `tests/test_alertas_noche_smn.py`. A reference implementation written here (hour in Argentina = (UTC - 3 h).hour;
night = 22 <= h or h < 5; only "rojo" passes) is compared against `avisos_smn.se_omite_de_noche` over an exhaustive
enumeration, and the end-to-end effects (a whole night every 30 minutes, mixed zones, live constants) are observed through
`evaluar_avisos_smn` and through the signed HTTP mode `{"modo":"smn"}`."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.rate_limit import limiter
from app.routers import alertas as router_alertas
from app.services.alertas import avisos_smn, despacho, regla, umbrales
from app.services.alertas.envio import topic_smn
from app.services.alertas.zonas import ZONAS
from app.services.smn_alertas import clave_dedupe
from tests.alertas_helpers import (  # noqa: F401
    AR,
    CLAVE_LOCK_SMN,
    envio_activo,
    esperas,
    estado_de_alertas_limpio,
    lineas_de_resumen_smn,
    redis,
    registrar,
    reloj_de_openmeteo,
)
from tests.openmeteo_fake_source import install, own_caches  # noqa: F401
from tests.test_alertas_avisos_smn import _entorno, alerta, avisos_por_zona, conjuntos_smn, push  # noqa: F401
from tests.test_alertas_evaluar_smn import CERO_ENVIO, CERO_SMN, feed, llamar_smn, open_meteo_prohibido  # noqa: F401

pytestmark = pytest.mark.integration

UTC = timezone.utc
TOKIO = timezone(timedelta(hours=9))
LOS_ANGELES = timezone(timedelta(hours=-8))
ZONAS_HORARIAS = (AR, UTC, TOKIO, LOS_ANGELES)
NIVELES = ("amarillo", "naranja", "rojo")


# --------------------------------------------------------------------------- reference, written from the spec
def hora_ar_de_referencia(momento: datetime) -> int:
    return (momento.astimezone(UTC) - timedelta(hours=3)).hour


def omitido_de_referencia(nivel: str, momento: datetime) -> bool:
    h = hora_ar_de_referencia(momento)
    return (h >= 22 or h < 5) and nivel != "rojo"


def momentos() -> list[datetime]:
    out = []
    for dia in (14, 15):
        for hora in range(24):
            for minuto in (0, 30, 59):
                for segundo in (0, 59):
                    for micro in (0, 999_999):
                        for tz in ZONAS_HORARIAS:
                            out.append(datetime(2026, 10, dia, hora, minuto, segundo, micro, tzinfo=tz))
    return out


def test_truth_table_against_the_reference_over_every_hour_level_and_zone() -> None:
    puntos = momentos()
    assert len(puntos) == 2 * 24 * 3 * 2 * 2 * 4
    errores = []
    for momento in puntos:
        for nivel in NIVELES:
            real = avisos_smn.se_omite_de_noche(alerta(nivel=nivel), momento)
            esperado = omitido_de_referencia(nivel, momento)
            if real is not esperado:
                errores.append((momento.isoformat(), nivel, real, esperado))
    assert errores == []
    # Sanity of the reference itself: a red one is never omitted, whatever the moment.
    assert not any(omitido_de_referencia("rojo", m) for m in puntos)


def test_borders_in_argentina_and_their_utc_equivalents_including_the_day_change() -> None:
    casos = [
        (datetime(2026, 10, 14, 21, 59, 59, 999_999, tzinfo=AR), False),
        (datetime(2026, 10, 14, 22, 0, 0, tzinfo=AR), True),
        (datetime(2026, 10, 14, 23, 59, 59, 999_999, tzinfo=AR), True),
        (datetime(2026, 10, 15, 0, 0, 0, tzinfo=AR), True),  # the day changes inside the night
        (datetime(2026, 10, 15, 4, 59, 59, 999_999, tzinfo=AR), True),
        (datetime(2026, 10, 15, 5, 0, 0, tzinfo=AR), False),
        (datetime(2026, 10, 15, 0, 59, 59, tzinfo=UTC), False),  # 21:59:59 AR
        (datetime(2026, 10, 15, 1, 0, 0, tzinfo=UTC), True),  # 22:00:00 AR
        (datetime(2026, 10, 15, 3, 0, 0, tzinfo=UTC), True),  # 00:00:00 AR (day change)
        (datetime(2026, 10, 15, 7, 59, 59, tzinfo=UTC), True),  # 04:59:59 AR
        (datetime(2026, 10, 15, 8, 0, 0, tzinfo=UTC), False),  # 05:00:00 AR
        (datetime(2026, 10, 15, 10, 0, 0, tzinfo=TOKIO), True),  # 01:00 UTC = 22:00 AR
        (datetime(2026, 10, 14, 17, 0, 0, tzinfo=LOS_ANGELES), True),  # 01:00 UTC = 22:00 AR
        (datetime(2026, 10, 14, 16, 59, 59, tzinfo=LOS_ANGELES), False),  # 21:59:59 AR
    ]
    for momento, omitido in casos:
        assert avisos_smn.es_de_noche(momento) is omitido, momento
        for nivel in ("amarillo", "naranja"):
            assert avisos_smn.se_omite_de_noche(alerta(nivel=nivel), momento) is omitido, (momento, nivel)
        assert avisos_smn.se_omite_de_noche(alerta(nivel="rojo"), momento) is False, momento


def test_coherence_with_the_forecast_silence_hour_by_hour() -> None:
    for dia in (14, 15):
        for hora in range(24):
            for minuto, segundo in ((0, 0), (59, 59)):
                m = datetime(2026, 10, dia, hora, minuto, segundo, tzinfo=AR)
                noche = avisos_smn.es_de_noche(m)
                if noche:
                    assert regla.ventana(m) is None, m
                if hora >= 22:
                    assert noche and despacho.segundos_hasta_el_silencio(m) == 0.0, m
                if hora < 22 and not noche:
                    assert despacho.segundos_hasta_el_silencio(m) > 0.0, m
                if hora in umbrales.REVISIONES_HOY or hora == umbrales.REVISION_MANANA:
                    assert not noche and regla.ventana(m) is not None, m


# --------------------------------------------------------------------------- robustness of the pure rule
def test_naive_ahora_raises_the_same_message_as_the_run_for_every_level_and_none() -> None:
    for nivel in ("amarillo", "naranja", "rojo", "otro", "ROJO", None):
        with pytest.raises(ValueError, match=r"^ahora necesita zona horaria$"):
            avisos_smn.se_omite_de_noche(SimpleNamespace(nivel=nivel), datetime(2026, 10, 14, 23, 0))
        with pytest.raises(ValueError, match=r"^ahora necesita zona horaria$"):
            avisos_smn.es_de_noche(datetime(2026, 10, 14, 23, 0))


def test_unexpected_levels_never_raise_and_never_pass_at_night() -> None:
    noche, dia = datetime(2026, 10, 14, 23, 0, tzinfo=AR), datetime(2026, 10, 14, 13, 0, tzinfo=AR)
    for nivel in ("otro", "ROJO", "Rojo", " rojo", None, "", "rojo "):
        assert avisos_smn.se_omite_de_noche(SimpleNamespace(nivel=nivel), noche) is True, nivel
        assert avisos_smn.se_omite_de_noche(SimpleNamespace(nivel=nivel), dia) is False, nivel
    sin_fechas = alerta(fecha_desde=None, fecha_hasta=None)
    assert avisos_smn.se_omite_de_noche(sin_fechas, noche) is True
    assert avisos_smn.se_omite_de_noche(alerta(nivel="rojo", fecha_desde=None, fecha_hasta=None), noche) is False


def test_the_constants_are_read_on_every_call_even_through_the_run(monkeypatch, redis, fake_upstash, push) -> None:
    amarillo = alerta(fecha_desde=None, fecha_hasta=None)
    seis = datetime(2026, 10, 15, 6, 0, tzinfo=AR)
    assert avisos_smn.se_omite_de_noche(amarillo, seis) is False
    monkeypatch.setattr(umbrales, "SILENCIO_HASTA_H", 7)
    assert avisos_smn.se_omite_de_noche(amarillo, seis) is True
    monkeypatch.setattr(umbrales, "SMN_NIVEL_QUE_PASA_DE_NOCHE", "amarillo")
    assert avisos_smn.se_omite_de_noche(amarillo, seis) is False
    assert avisos_smn.se_omite_de_noche(alerta(nivel="rojo"), seis) is True


async def test_the_run_reads_the_live_constants(monkeypatch, redis, fake_upstash, push) -> None:
    ids = await registrar(redis, "cordoba", 1)
    monkeypatch.setattr(umbrales, "SILENCIO_HASTA_H", 7)
    seis = datetime(2026, 10, 15, 6, 0, tzinfo=AR)
    feed_ = avisos_por_zona({"cordoba": [alerta(fecha_desde=None, fecha_hasta=None)]})
    r = await avisos_smn.evaluar_avisos_smn(redis, seis, vapid=object(), obtener_avisos=feed_)
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1) and push.llamadas == []
    monkeypatch.setattr(umbrales, "SILENCIO_HASTA_H", 5)
    r = await avisos_smn.evaluar_avisos_smn(redis, seis, vapid=object(), obtener_avisos=feed_)
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1) and [c.sub_id for c in push.llamadas] == ids


# --------------------------------------------------------------------------- end to end through the run
def en_ar(dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 10, dia, hora, minuto, tzinfo=AR)


AMARILLO_FUTURO_7 = alerta(fecha_desde=en_ar(15, 7), fecha_hasta=en_ar(15, 12))
AMARILLO_VENCE_3 = alerta(fecha_desde=en_ar(14, 20), fecha_hasta=en_ar(15, 3))
AMARILLO = alerta(fecha_desde=None, fecha_hasta=None)
NARANJA = alerta(nivel="naranja", severidad="Severe", fecha_desde=None, fecha_hasta=None)
ROJO = alerta(nivel="rojo", severidad="Extreme", fecha_desde=None, fecha_hasta=None)


async def correr(redis, momento, por_zona, **kw):
    kw.setdefault("vapid", object())
    return await avisos_smn.evaluar_avisos_smn(redis, momento, obtener_avisos=avisos_por_zona(por_zona), **kw)


async def test_a_yellow_in_force_from_7_at_23_is_omitted_and_sent_at_5_saying_since_when(redis, fake_upstash, push):
    ids = await registrar(redis, "cordoba", 2)
    fake_upstash.commands.clear()
    r = await correr(redis, en_ar(14, 23), {"cordoba": [AMARILLO_FUTURO_7]})
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1) and r.envio == despacho.ResumenEnvio()
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]
    assert not [k for k in fake_upstash.sets if k.startswith("alertas:enviado:")]
    r = await correr(redis, en_ar(15, 5), {"cordoba": [AMARILLO_FUTURO_7]})
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert r.envio == despacho.ResumenEnvio(avisadas=1, enviados=2)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    for c in push.llamadas:
        assert "Rige desde las 7 h" in c.payload["body"] and "amarillo" in c.payload["body"]
        assert c.ttl == 7 * 3600  # 05:00 -> 12:00
    clave = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", AMARILLO_FUTURO_7))
    assert conjuntos_smn(fake_upstash) == [clave] and fake_upstash.sets[clave] == set(ids)
    assert fake_upstash.ttls[clave] == 7 * 3600 + 36 * 3600


@pytest.mark.parametrize("momento", [en_ar(14, 23, 30), en_ar(15, 2, 30)])
async def test_a_red_at_night_is_pushed_and_marked(redis, fake_upstash, push, momento):
    ids = await registrar(redis, "cordoba", 2)
    r = await correr(redis, momento, {"cordoba": [ROJO]})
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    clave = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", ROJO))
    assert conjuntos_smn(fake_upstash) == [clave] and fake_upstash.sets[clave] == set(ids)


async def test_a_yellow_omitted_that_expires_at_3_is_never_sent_nor_marked(redis, fake_upstash, push):
    await registrar(redis, "cordoba", 2)
    # At 3:00:00 sharp T1 still lists it (its end is inclusive) and the night rule omits it: nothing goes out either.
    for momento in (en_ar(14, 23), en_ar(15, 2, 30), en_ar(15, 3, 0)):
        r = await correr(redis, momento, {"cordoba": [AMARILLO_VENCE_3]})
        assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1), momento
    for momento in (en_ar(15, 3, 0).replace(second=1), en_ar(15, 5), en_ar(15, 5, 30)):
        r = await correr(redis, momento, {"cordoba": [AMARILLO_VENCE_3]})
        assert r.smn == despacho.ResumenSmn(), momento  # expired: not even a pair
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []


async def test_an_orange_at_night_behaves_like_the_yellow(redis, fake_upstash, push):
    ids = await registrar(redis, "cordoba", 2)
    for momento in (en_ar(14, 22), en_ar(15, 0), en_ar(15, 4, 59)):
        r = await correr(redis, momento, {"cordoba": [NARANJA]})
        assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1) and push.llamadas == [], momento
    r = await correr(redis, en_ar(15, 5), {"cordoba": [NARANJA]})
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1)
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert all("naranja" in c.payload["body"] for c in push.llamadas)


def corridas_de_la_noche() -> list[datetime]:
    t = en_ar(14, 22)
    out = []
    while t <= en_ar(15, 6):
        out.append(t)
        t += timedelta(minutes=30)
    return out


async def test_a_whole_night_every_30_min_red_once_at_22_yellow_and_orange_once_at_5(redis, fake_upstash, push):
    ids = await registrar(redis, "cordoba", 2)
    por_hora = {}
    for momento in corridas_de_la_noche():
        antes = len(push.llamadas)
        r = await correr(redis, momento, {"cordoba": [AMARILLO, NARANJA, ROJO]})
        por_hora[momento.strftime("%H:%M")] = (r.smn, len(push.llamadas) - antes)
    assert len(por_hora) == 17
    assert por_hora["22:00"] == (despacho.ResumenSmn(smn_avisos=3, smn_avisadas=1, smn_omitidas=2), 2)
    for h in ("22:30", "23:00", "23:30", "00:00", "00:30", "01:00", "01:30", "02:00", "02:30", "03:00", "03:30",
              "04:00", "04:30"):
        assert por_hora[h] == (despacho.ResumenSmn(smn_avisos=3, smn_ya_avisadas=1, smn_omitidas=2), 0), h
    assert por_hora["05:00"] == (despacho.ResumenSmn(smn_avisos=3, smn_avisadas=2, smn_ya_avisadas=1), 4)
    for h in ("05:30", "06:00"):
        assert por_hora[h] == (despacho.ResumenSmn(smn_avisos=3, smn_ya_avisadas=3), 0), h
    por_topic = {}
    for c in push.llamadas:
        por_topic.setdefault(c.topic, []).append(c.sub_id)
    esperado = {topic_smn(clave_dedupe("cordoba", a)): sorted(ids) for a in (AMARILLO, NARANJA, ROJO)}
    assert {t: sorted(v) for t, v in por_topic.items()} == esperado  # each level exactly once per subscriber
    assert len(push.llamadas) == 6


async def test_yellow_raised_to_red_at_3_red_goes_out_at_3_and_the_yellow_at_5_if_still_listed(
    redis, fake_upstash, push
):
    ids = await registrar(redis, "cordoba", 2)
    cronica = []
    for momento in corridas_de_la_noche():
        listado = [AMARILLO] if momento < en_ar(15, 3) else [AMARILLO, ROJO]
        antes = len(push.llamadas)
        r = await correr(redis, momento, {"cordoba": listado})
        nuevos = push.llamadas[antes:]
        cronica.append((momento.strftime("%H:%M"), r.smn, sorted({c.payload["body"].split(" ")[4] for c in nuevos})))
    enviados = [(h, niveles) for h, _, niveles in cronica if niveles]
    assert enviados == [("03:00", ["rojo"]), ("05:00", ["amarillo"])]
    assert len(push.llamadas) == 4 and sorted(c.sub_id for c in push.llamadas[:2]) == sorted(ids)
    assert cronica[10][0] == "03:00" and cronica[10][1] == despacho.ResumenSmn(smn_avisos=2, smn_avisadas=1, smn_omitidas=1)


async def test_several_zones_with_mixed_levels_at_night_only_the_red_zones_get_a_push(redis, fake_upstash, push):
    z = [zona.slug for zona in ZONAS[:4]]
    ids = {slug: await registrar(redis, slug, 1) for slug in z}
    r = await correr(redis, en_ar(15, 1, 30), {z[0]: [AMARILLO], z[1]: [ROJO], z[2]: [NARANJA], z[3]: [ROJO, AMARILLO]})
    assert r.smn == despacho.ResumenSmn(smn_avisos=5, smn_avisadas=2, smn_omitidas=3)
    assert sorted(c.zona for c in push.llamadas) == sorted([z[1], z[3]])
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids[z[1]] + ids[z[3]])
    assert all("rojo" in c.payload["body"] for c in push.llamadas)
    assert conjuntos_smn(fake_upstash) == sorted(
        avisos_smn.clave_de_enviados_smn(clave_dedupe(s, ROJO)) for s in (z[1], z[3])
    )


async def test_a_dry_run_at_night_counts_the_pairs_but_no_omission(redis, fake_upstash, push):
    await registrar(redis, "cordoba", 1)
    r = await correr(redis, en_ar(14, 23), {"cordoba": [AMARILLO, ROJO]}, vapid=None)
    assert r.smn == despacho.ResumenSmn(smn_avisos=2) and r.envio == despacho.ResumenEnvio()
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []


async def test_a_rule_that_raises_for_one_pair_leaves_nothing_sent_nor_marked(redis, fake_upstash, push):
    await registrar(redis, "cordoba", 2)

    def rota(alerta_, ahora):
        if alerta_.nivel == "naranja":
            raise RuntimeError("boom")
        return False

    fake_upstash.commands.clear()
    with pytest.raises(RuntimeError, match="boom"):
        await correr(redis, en_ar(14, 13), {"cordoba": [AMARILLO, NARANJA, ROJO]}, omitir=rota)
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert fake_upstash.commands == [["SMEMBERS", "alertas:zonas"]]


async def test_a_naive_ahora_in_the_run_touches_nothing(redis, fake_upstash, push):
    await registrar(redis, "cordoba", 1)
    fake_upstash.commands.clear()
    with pytest.raises(ValueError, match=r"^ahora necesita zona horaria$"):
        await correr(redis, datetime(2026, 10, 14, 23, 0), {"cordoba": [AMARILLO]})
    assert fake_upstash.commands == [] and push.llamadas == []


async def test_ahora_with_microseconds_at_the_borders_through_the_run(redis, fake_upstash, push):
    ids = await registrar(redis, "cordoba", 1)
    r = await correr(redis, en_ar(15, 4, 59).replace(second=59, microsecond=999_999), {"cordoba": [AMARILLO]})
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_omitidas=1) and push.llamadas == []
    r = await correr(redis, en_ar(15, 5).replace(microsecond=1), {"cordoba": [AMARILLO]})
    assert r.smn == despacho.ResumenSmn(smn_avisos=1, smn_avisadas=1) and [c.sub_id for c in push.llamadas] == ids


# --------------------------------------------------------------------------- through HTTP, signed
def reloj(monkeypatch, momento: datetime) -> None:
    monkeypatch.setattr(router_alertas, "_ahora_utc", lambda: momento.astimezone(UTC))


async def test_http_yellow_at_23_omitted_then_sent_at_5_with_the_text_since_7(
    async_client: AsyncClient, alertas_redis, fake_upstash, push, feed, open_meteo_prohibido, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    ids = await registrar(alertas_redis, "cordoba", 2)
    feed.obtener = avisos_por_zona({"cordoba": [AMARILLO_FUTURO_7]})
    reloj(monkeypatch, en_ar(14, 23))
    limiter.reset()
    resp = await llamar_smn(async_client)
    assert resp.status_code == 200
    assert resp.json() == {"estado": "evaluada", **CERO_SMN, "smn_avisos": 1, "smn_omitidas": 1, **CERO_ENVIO}
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    linea = lineas_de_resumen_smn(caplog)
    assert len(linea) == 1 and linea[0].levelno == logging.INFO and "smn_omitidas=1" in linea[0].getMessage()
    fake_upstash.strings.pop(CLAVE_LOCK_SMN, None)
    reloj(monkeypatch, en_ar(15, 5))
    limiter.reset()
    resp = await llamar_smn(async_client)
    assert resp.status_code == 200
    assert resp.json() == {
        "estado": "evaluada", **CERO_SMN, "smn_avisos": 1, "smn_avisadas": 1, **CERO_ENVIO, "avisadas": 1, "enviados": 2
    }
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert all(c.payload["body"] == "Aviso oficial de nivel amarillo por tormentas. Rige desde las 7 h. Fuente: SMN"
               for c in push.llamadas)
    clave = avisos_smn.clave_de_enviados_smn(clave_dedupe("cordoba", AMARILLO_FUTURO_7))
    assert fake_upstash.sets[clave] == set(ids) and fake_upstash.ttls[clave] == 7 * 3600 + 36 * 3600
    assert open_meteo_prohibido.calls == []


@pytest.mark.parametrize("momento", [en_ar(14, 23, 30), en_ar(15, 2, 30)])
async def test_http_red_at_night_is_sent(
    async_client: AsyncClient, alertas_redis, fake_upstash, push, feed, open_meteo_prohibido, monkeypatch, momento
):
    ids = await registrar(alertas_redis, "cordoba", 2)
    feed.obtener = avisos_por_zona({"cordoba": [ROJO]})
    reloj(monkeypatch, momento)
    limiter.reset()
    resp = await llamar_smn(async_client)
    assert resp.status_code == 200 and resp.json()["smn_avisadas"] == 1 and resp.json()["enviados"] == 2
    assert sorted(c.sub_id for c in push.llamadas) == sorted(ids)
    assert open_meteo_prohibido.calls == []


async def test_http_dry_run_at_night_counts_without_omissions(
    async_client: AsyncClient, alertas_redis, fake_upstash, push, feed, open_meteo_prohibido, monkeypatch, caplog
):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(settings, "alertas_envio_activo", False)
    monkeypatch.setattr(settings, "alertas_evaluar_en_seco", True)
    await registrar(alertas_redis, "cordoba", 2)
    feed.obtener = avisos_por_zona({"cordoba": [AMARILLO]})
    reloj(monkeypatch, en_ar(14, 23))
    limiter.reset()
    resp = await llamar_smn(async_client)
    assert resp.status_code == 200
    assert resp.json() == {"estado": "evaluada", **CERO_SMN, "smn_avisos": 1}
    assert push.llamadas == [] and conjuntos_smn(fake_upstash) == []
    assert "smn_avisos=1 smn_avisadas=0 smn_ya_avisadas=0 smn_omitidas=0" in lineas_de_resumen_smn(caplog)[0].getMessage()
