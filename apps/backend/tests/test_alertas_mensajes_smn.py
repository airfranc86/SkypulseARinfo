"""Push of an OFFICIAL SMN storm alert (FRA-359, T2): text, Topic/tag and counters.

The text is a DRAFT the owner approves before the merge: these tests pin its shape (official notice, level in words,
"Fuente: SMN", the start of validity when it starts later, never the hour of the storm, never the "not an official
notice" legend of the forecast push), not the last word of each sentence.

The Topic and the tag of an SMN push derive from the dedupe key of T1 (`smn_alertas.clave_dedupe`): same alert, same
Topic and tag; another alert (a rise from yellow to orange) gets new ones; and they never collide with the forecast
push of the same city and day (`topic_de`, `tag_de`). RFC 8030 section 5.4: a Topic is at most 32 characters of the
URL and filename-safe base64 alphabet (verified against the RFC text, 2026-10-15).
"""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

import pytest

from app.schemas.smn_alertas import SmnAlerta
from app.services.alertas import despacho, envio, evaluacion
from app.services.alertas.envio import TAG_ALERTA, TAG_SMN, construir_payload, enviar, tag_de, tag_smn, topic_de, topic_smn
from app.services.alertas.mensajes_smn import FUENTE, Mensaje, texto_aviso_smn
from app.services.alertas.zonas import ZONAS, zona_por_slug
from app.services.smn_alertas import clave_dedupe

pytestmark = pytest.mark.unit

_AR = timezone(timedelta(hours=-3))
CORDOBA = zona_por_slug("cordoba")
ROSARIO = zona_por_slug("rosario")

AHORA = datetime(2026, 10, 14, 13, 0, tzinfo=_AR)  # the evaluation of 13 h of L2
DESDE_PASADO = datetime(2026, 10, 14, 9, 0, tzinfo=_AR)  # already in force at AHORA
DESDE_HOY = datetime(2026, 10, 14, 15, 0, tzinfo=_AR)  # later today
DESDE_MANANA = datetime(2026, 10, 15, 9, 0, tzinfo=_AR)
DESDE_OTRO_DIA = datetime(2026, 10, 16, 9, 30, tzinfo=_AR)
HASTA = datetime(2026, 10, 14, 20, 59, 59, tzinfo=_AR)
FECHA = date(2026, 10, 14)

_TOPIC_RFC_8030 = re.compile(r"[A-Za-z0-9_-]{1,32}")


def _alerta(**overrides: object) -> SmnAlerta:
    fields: dict[str, object] = {
        "nivel": "amarillo",
        "tipo": "Tormentas",
        "fecha_desde": DESDE_PASADO,
        "fecha_hasta": HASTA,
        "descripcion": "Tormentas fuertes con actividad electrica frecuente.",
        "severidad": "Moderate",
        "instruccion": None,
    }
    fields.update(overrides)
    return SmnAlerta(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Text (S5): the three cases the owner approves, verbatim
# ---------------------------------------------------------------------------


def test_a_yellow_alert_already_in_force() -> None:
    mensaje = texto_aviso_smn(CORDOBA, _alerta(nivel="amarillo"), ahora=AHORA)

    assert mensaje == Mensaje(
        titulo="SkyPulse · Córdoba",
        cuerpo="Aviso oficial de nivel amarillo por tormentas, ya vigente. Fuente: SMN",
    )


def test_an_orange_alert_that_starts_later_today_says_since_when_it_is_in_force() -> None:
    mensaje = texto_aviso_smn(CORDOBA, _alerta(nivel="naranja", fecha_desde=DESDE_HOY), ahora=AHORA)

    assert mensaje == Mensaje(
        titulo="SkyPulse · Córdoba",
        cuerpo="Aviso oficial de nivel naranja por tormentas. Rige desde las 15 h. Fuente: SMN",
    )


def test_a_red_alert_already_in_force() -> None:
    mensaje = texto_aviso_smn(CORDOBA, _alerta(nivel="rojo", severidad="Extreme"), ahora=AHORA)

    assert mensaje == Mensaje(
        titulo="SkyPulse · Córdoba",
        cuerpo="Aviso oficial de nivel rojo por tormentas, ya vigente. Fuente: SMN",
    )


@pytest.mark.parametrize(
    ("desde", "frase"),
    [
        (DESDE_MANANA, "Rige desde mañana a las 9 h."),
        (DESDE_OTRO_DIA, "Rige desde el 16/10 a las 9:30 h."),
        (datetime(2026, 10, 14, 16, 30, tzinfo=_AR), "Rige desde las 16:30 h."),
        (datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc), "Rige desde las 15 h."),  # in Argentina time
    ],
    ids=["manana", "otro-dia", "con-minutos", "utc-se-convierte"],
)
def test_the_start_of_validity_is_argentina_time_tomorrow_or_the_day(desde: datetime, frase: str) -> None:
    cuerpo = texto_aviso_smn(CORDOBA, _alerta(fecha_desde=desde), ahora=AHORA).cuerpo

    assert cuerpo == f"Aviso oficial de nivel amarillo por tormentas. {frase} {FUENTE}"


@pytest.mark.parametrize("desde", [None, AHORA, DESDE_PASADO], ids=["sin-inicio", "empieza-ahora", "ya-empezo"])
def test_an_alert_in_force_or_without_a_start_carries_no_start(desde: datetime | None) -> None:
    cuerpo = texto_aviso_smn(CORDOBA, _alerta(fecha_desde=desde), ahora=AHORA).cuerpo

    assert cuerpo == "Aviso oficial de nivel amarillo por tormentas, ya vigente. Fuente: SMN"
    assert "Rige" not in cuerpo


def test_a_naive_start_is_read_as_utc() -> None:
    con_tz = texto_aviso_smn(CORDOBA, _alerta(fecha_desde=datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)), ahora=AHORA)
    sin_tz = texto_aviso_smn(CORDOBA, _alerta(fecha_desde=datetime(2026, 10, 14, 18, 0)), ahora=AHORA)

    assert sin_tz == con_tz and "Rige desde las 15 h." in sin_tz.cuerpo


def test_the_text_is_about_the_official_notice_never_the_forecast_nor_the_hour_of_the_storm() -> None:
    for alerta in (_alerta(), _alerta(nivel="rojo", fecha_desde=DESDE_HOY)):
        cuerpo = texto_aviso_smn(CORDOBA, alerta, ahora=AHORA).cuerpo
        assert cuerpo.endswith(FUENTE) and FUENTE == "Fuente: SMN"
        assert "no es un aviso oficial" not in cuerpo and "Pronóstico" not in cuerpo
        assert "20:59" not in cuerpo and "21" not in cuerpo  # `fecha_hasta` and the hour of the storm are never said
        assert alerta.descripcion not in cuerpo  # the free text of the feed is not relayed


def test_the_title_is_the_city_like_the_forecast_push() -> None:
    assert texto_aviso_smn(ROSARIO, _alerta(), ahora=AHORA).titulo == "SkyPulse · Rosario"


@pytest.mark.parametrize("nivel", ["otro", "verde", "", "Amarillo"])
def test_a_level_without_a_word_is_refused(nivel: str) -> None:
    with pytest.raises(ValueError):
        texto_aviso_smn(CORDOBA, _alerta(nivel=nivel), ahora=AHORA)


def test_the_text_fits_a_push_payload_for_every_zone() -> None:
    for zona in ZONAS:
        for alerta in (_alerta(nivel="naranja", fecha_desde=DESDE_OTRO_DIA), _alerta(nivel="rojo")):
            payload = construir_payload(texto_aviso_smn(zona, alerta, ahora=AHORA), tag=tag_smn(clave_dedupe(zona.slug, alerta)))
            datos = json.loads(payload)
            assert datos["title"] == f"SkyPulse · {zona.nombre}" and datos["tag"].startswith(TAG_SMN)


# ---------------------------------------------------------------------------
# Topic and tag (S4): derived from the dedupe key, never the forecast's
# ---------------------------------------------------------------------------


def test_the_smn_topic_fits_rfc_8030_for_every_zone_and_level() -> None:
    for zona in ZONAS:
        for nivel in ("amarillo", "naranja", "rojo"):
            topic = topic_smn(clave_dedupe(zona.slug, _alerta(nivel=nivel)))
            assert len(topic) == 32 and _TOPIC_RFC_8030.fullmatch(topic), (zona.slug, nivel, topic)


def test_the_same_alert_gives_the_same_topic_and_tag_even_if_the_text_changes() -> None:
    clave = clave_dedupe("cordoba", _alerta())
    reescrita = clave_dedupe("cordoba", _alerta(descripcion="Texto actualizado por el SMN.", fecha_hasta=HASTA + timedelta(hours=2)))

    assert clave == reescrita
    assert topic_smn(clave) == topic_smn(reescrita)
    assert tag_smn(clave) == tag_smn(reescrita)


def test_another_alert_gives_another_topic_and_tag() -> None:
    base = clave_dedupe("cordoba", _alerta())
    otras = {
        "sube-a-naranja": clave_dedupe("cordoba", _alerta(nivel="naranja")),
        "otra-zona": clave_dedupe("rosario", _alerta()),
        "otro-inicio": clave_dedupe("cordoba", _alerta(fecha_desde=DESDE_MANANA)),
        "otro-tipo": clave_dedupe("cordoba", _alerta(tipo="Viento")),
    }
    for nombre, clave in otras.items():
        assert topic_smn(clave) != topic_smn(base), nombre
        assert tag_smn(clave) != tag_smn(base), nombre
    assert len({topic_smn(c) for c in otras.values()}) == len(otras)


def test_the_same_instant_in_another_time_zone_gives_the_same_topic_and_tag() -> None:
    en_ar = clave_dedupe("cordoba", _alerta(fecha_desde=datetime(2026, 10, 14, 15, 0, tzinfo=_AR)))
    en_utc = clave_dedupe("cordoba", _alerta(fecha_desde=datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)))

    assert topic_smn(en_ar) == topic_smn(en_utc) and tag_smn(en_ar) == tag_smn(en_utc)


def test_an_alert_without_a_start_still_gets_a_topic_and_tag() -> None:
    clave = clave_dedupe("cordoba", _alerta(fecha_desde=None))

    assert _TOPIC_RFC_8030.fullmatch(topic_smn(clave)) and tag_smn(clave).startswith(f"{TAG_SMN}-cordoba-")
    assert topic_smn(clave) != topic_smn(clave_dedupe("cordoba", _alerta()))


def test_the_smn_topic_and_tag_never_collide_with_the_forecast_push_of_the_same_city_and_day() -> None:
    clave = clave_dedupe("cordoba", _alerta())

    assert topic_smn(clave) != topic_de("cordoba", FECHA)
    assert topic_smn(clave) != topic_de("cordoba", AHORA.date())
    assert tag_smn(clave) != tag_de("cordoba", FECHA)
    assert TAG_SMN == "skypulse-smn" and not TAG_SMN.startswith(TAG_ALERTA)
    assert tag_smn(clave).startswith("skypulse-smn-cordoba-")
    assert re.fullmatch(r"skypulse-smn-cordoba-[A-Za-z0-9_-]{12}", tag_smn(clave))


def test_the_forecast_topic_and_tag_are_unchanged() -> None:
    assert tag_de("cordoba", date(2026, 10, 9)) == "skypulse-alerta-cordoba-2026-10-09"
    assert topic_de("cordoba", FECHA) == topic_de("cordoba", FECHA) and len(topic_de("cordoba", FECHA)) == 32
    assert topic_de("cordoba", FECHA) != topic_de("rosario", FECHA)


# ---------------------------------------------------------------------------
# `enviar` accepts the Topic of the message (the forecast keeps deriving it from zone and date)
# ---------------------------------------------------------------------------


async def test_enviar_sends_the_given_topic(alertas_redis, suscribir, push_http, vapid_efimera) -> None:
    sub = await suscribir()
    clave = clave_dedupe("cordoba", _alerta())
    payload = construir_payload(texto_aviso_smn(CORDOBA, _alerta(), ahora=AHORA), tag=tag_smn(clave))

    resultado = await enviar(
        alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA, topic=topic_smn(clave)
    )

    assert resultado is envio.Resultado.ENVIADA
    cabeceras = push_http.requests[0].headers
    assert cabeceras["Topic"] == topic_smn(clave) and cabeceras["Urgency"] == "high"


async def test_enviar_without_a_topic_keeps_the_topic_of_the_city_and_day(
    alertas_redis, suscribir, push_http, vapid_efimera
) -> None:
    sub = await suscribir()
    payload = construir_payload(texto_aviso_smn(CORDOBA, _alerta(), ahora=AHORA))

    await enviar(alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA)

    assert push_http.requests[0].headers["Topic"] == topic_de("cordoba", FECHA)


@pytest.mark.parametrize("topic", ["", "a" * 33, "con espacio", "con+mas", "con/barra", "tilde-á"])
async def test_a_topic_outside_rfc_8030_is_refused_before_anything_is_sent(
    alertas_redis, suscribir, push_http, vapid_efimera, topic: str
) -> None:
    sub = await suscribir()
    payload = construir_payload(texto_aviso_smn(CORDOBA, _alerta(), ahora=AHORA))

    with pytest.raises(ValueError):
        await enviar(alertas_redis, sub.id, sub.registro, payload, zona="cordoba", fecha=FECHA, topic=topic)

    assert push_http.requests == []


# ---------------------------------------------------------------------------
# Counters of the SMN sending (S2 context): their own, next to the existing ones, never inside them
# ---------------------------------------------------------------------------


def test_the_smn_summary_is_frozen_adds_without_mutating_and_lists_only_counters() -> None:
    a = despacho.ResumenSmn(smn_avisos=2, smn_avisadas=1)
    b = despacho.ResumenSmn(smn_avisos=1, smn_ya_avisadas=1, smn_errores=1)
    suma = a.sumar(b)

    assert suma == despacho.ResumenSmn(smn_avisos=3, smn_avisadas=1, smn_ya_avisadas=1, smn_errores=1)
    assert a == despacho.ResumenSmn(smn_avisos=2, smn_avisadas=1)  # the inputs are untouched
    with pytest.raises(FrozenInstanceError):
        a.smn_avisos = 9  # type: ignore[misc]
    assert tuple(suma.como_respuesta()) == despacho.CONTADORES_SMN
    assert despacho.CONTADORES_SMN == (
        "smn_sin_datos", "smn_avisos", "smn_avisadas", "smn_ya_avisadas", "smn_omitidas", "smn_errores",
    )
    assert all(type(v) is int for v in suma.como_respuesta().values())
    assert suma.como_respuesta() == {
        "smn_sin_datos": 0, "smn_avisos": 3, "smn_avisadas": 1, "smn_ya_avisadas": 1, "smn_omitidas": 0, "smn_errores": 1,
    }


def test_the_smn_summary_logs_in_the_same_shape_as_the_existing_counters() -> None:
    formato, argumentos = despacho.ResumenSmn(smn_avisos=2, smn_avisadas=1, smn_omitidas=1).como_log()

    assert formato == "smn_sin_datos=%d smn_avisos=%d smn_avisadas=%d smn_ya_avisadas=%d smn_omitidas=%d smn_errores=%d"
    assert argumentos == (0, 2, 1, 0, 1, 0)
    assert formato % argumentos == "smn_sin_datos=0 smn_avisos=2 smn_avisadas=1 smn_ya_avisadas=0 smn_omitidas=1 smn_errores=0"


def test_the_smn_counters_are_new_names_and_the_existing_ones_did_not_change() -> None:
    assert despacho.CONTADORES_ENVIO == (
        "avisadas", "ya_avisadas", "enviados", "vencidos", "fallidos", "diferidos", "reintentadas",
    )
    assert evaluacion.CONTADORES == (
        "zonas_con_suscriptores", "evaluadas", "con_tormenta", "sin_tormenta", "sin_datos", "errores", "diferidas",
        "desconocidas",
    )
    assert set(despacho.CONTADORES_SMN).isdisjoint(despacho.CONTADORES_ENVIO)
    assert set(despacho.CONTADORES_SMN).isdisjoint(evaluacion.CONTADORES)
    assert all(nombre.startswith("smn_") for nombre in despacho.CONTADORES_SMN)
    assert tuple(despacho.ResumenEnvio(avisadas=1).como_respuesta()) == despacho.CONTADORES_ENVIO
