"""Textos de las notificaciones de alertas push (FRA-354, T4.2).

Los textos son un BORRADOR que el dueño aprueba antes del merge: estos tests fijan la forma (franjas del
día, leyenda, sin horas exactas), no la última palabra de cada frase.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.services.alertas.regla import HoraTormenta, ResultadoRegla
from app.services.alertas.textos import (
    FRANJAS,
    LEYENDA,
    Mensaje,
    franja,
    franjas_de,
    texto_aviso_hoy,
    texto_aviso_manana,
    texto_prueba,
)
from app.services.alertas.zonas import ZONAS, zona_por_slug

pytestmark = pytest.mark.unit

_AR = timezone(timedelta(hours=-3))
CORDOBA = zona_por_slug("cordoba")

LEYENDA_ESPERADA = (
    "Pronóstico de SkyPulse, no es un aviso oficial. "
    "Consultá los avisos del SMN en smn.gob.ar"
)


def _hora(hora_ar: int, dia: int = 9) -> HoraTormenta:
    momento = datetime(2026, 10, dia, hora_ar, tzinfo=_AR)
    return HoraTormenta(
        hora=f"{hora_ar:02d}:00",
        timestamp=int(momento.timestamp()),
        weather_code=95,
        cape_j_kg=None,
        motivo="codigo",
    )


# ---------------------------------------------------------------------------
# Franjas del día
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hora", "esperada"),
    [
        (0, "madrugada"),
        (5, "madrugada"),
        (6, "mañana"),
        (11, "mañana"),
        (12, "tarde"),
        (17, "tarde"),
        (18, "noche"),
        (23, "noche"),
    ],
)
def test_franja_boundaries(hora: int, esperada: str) -> None:
    assert franja(hora) == esperada


@pytest.mark.parametrize("fuera", [-1, 24, 99])
def test_franja_rejects_hours_outside_the_day(fuera: int) -> None:
    with pytest.raises(ValueError):
        franja(fuera)


def test_every_hour_of_the_day_belongs_to_exactly_one_franja() -> None:
    assert {franja(h) for h in range(24)} == set(FRANJAS)


def test_franjas_de_orders_by_the_day_and_drops_duplicates() -> None:
    resultado = ResultadoRegla(
        horas=(_hora(19), _hora(14), _hora(15), _hora(2), _hora(22))
    )
    assert franjas_de(resultado) == ("madrugada", "tarde", "noche")


def test_franjas_de_reads_the_argentine_hour_not_utc() -> None:
    # 22 h de Argentina son las 01 h UTC del día siguiente: la franja es "noche", no "madrugada".
    assert franjas_de(ResultadoRegla(horas=(_hora(22),))) == ("noche",)


def test_franjas_de_without_storm_is_empty() -> None:
    assert franjas_de(ResultadoRegla(horas=())) == ()


# ---------------------------------------------------------------------------
# Los tres textos
# ---------------------------------------------------------------------------


def test_the_legend_is_the_approved_wording() -> None:
    assert LEYENDA == LEYENDA_ESPERADA


@pytest.mark.parametrize(
    ("franjas", "frase"),
    [
        (("tarde",), "a la tarde"),
        (("tarde", "noche"), "a la tarde y a la noche"),
        (("madrugada", "mañana", "tarde"), "de madrugada, a la mañana y a la tarde"),
        (
            ("madrugada", "mañana", "tarde", "noche"),
            "de madrugada, a la mañana, a la tarde y a la noche",
        ),
        (("madrugada",), "de madrugada"),
        (("mañana", "noche"), "a la mañana y a la noche"),
    ],
)
def test_aviso_manana_joins_one_to_four_franjas(franjas, frase: str) -> None:
    mensaje = texto_aviso_manana(CORDOBA, franjas)

    assert mensaje == Mensaje(
        titulo="SkyPulse · Córdoba",
        cuerpo=f"Posibles tormentas mañana {frase}. {LEYENDA_ESPERADA}",
    )


def test_aviso_manana_matches_the_ticket_draft() -> None:
    mensaje = texto_aviso_manana(CORDOBA, ("tarde", "noche"))
    assert mensaje.titulo == "SkyPulse · Córdoba"
    assert mensaje.cuerpo == (
        "Posibles tormentas mañana a la tarde y a la noche. "
        "Pronóstico de SkyPulse, no es un aviso oficial. Consultá los avisos del SMN en smn.gob.ar"
    )


@pytest.mark.parametrize(
    ("franjas", "frase"),
    [
        (("noche",), "a la noche"),
        (("tarde", "noche"), "a la tarde y a la noche"),
        (("mañana", "tarde", "noche"), "a la mañana, a la tarde y a la noche"),
    ],
)
def test_aviso_hoy_says_today_with_the_same_joins(franjas, frase: str) -> None:
    mensaje = texto_aviso_hoy(CORDOBA, franjas)

    assert mensaje.titulo == "SkyPulse · Córdoba"
    assert mensaje.cuerpo == f"Posibles tormentas hoy {frase}. {LEYENDA_ESPERADA}"


def test_franjas_are_reordered_and_deduplicated() -> None:
    mensaje = texto_aviso_manana(CORDOBA, ("noche", "tarde", "noche"))
    assert "mañana a la tarde y a la noche." in mensaje.cuerpo


@pytest.mark.parametrize("texto", [texto_aviso_manana, texto_aviso_hoy])
def test_an_alert_without_franjas_is_a_bug(texto) -> None:
    with pytest.raises(ValueError):
        texto(CORDOBA, ())


@pytest.mark.parametrize("texto", [texto_aviso_manana, texto_aviso_hoy])
def test_an_unknown_franja_is_a_bug(texto) -> None:
    with pytest.raises(ValueError):
        texto(CORDOBA, ("mediodia",))


def test_prueba_matches_the_ticket_draft_and_uses_the_zone_name() -> None:
    mensaje = texto_prueba(CORDOBA)

    assert mensaje == Mensaje(
        titulo="SkyPulse · Prueba",
        cuerpo="Así vas a ver los avisos de tormenta para Córdoba. Si te llegó, está todo listo.",
    )
    assert texto_prueba(zona_por_slug("san-salvador-de-jujuy")).cuerpo.startswith(
        "Así vas a ver los avisos de tormenta para San Salvador de Jujuy."
    )


# ---------------------------------------------------------------------------
# Reglas que valen para todos los textos y todas las ciudades
# ---------------------------------------------------------------------------

_COMBINACIONES = [
    ("madrugada",),
    ("tarde", "noche"),
    ("madrugada", "mañana", "tarde"),
    FRANJAS,
]


def _todos_los_textos():
    for zona in ZONAS:
        yield texto_prueba(zona)
        for franjas in _COMBINACIONES:
            yield texto_aviso_manana(zona, franjas)
            yield texto_aviso_hoy(zona, franjas)


def test_alert_texts_always_end_with_the_legend_and_prueba_does_not_need_it() -> None:
    for zona in ZONAS:
        for franjas in _COMBINACIONES:
            for mensaje in (
                texto_aviso_manana(zona, franjas),
                texto_aviso_hoy(zona, franjas),
            ):
                assert mensaje.cuerpo.endswith(LEYENDA_ESPERADA), zona.slug


def test_no_text_names_an_exact_hour() -> None:
    hora_exacta = re.compile(r"\d{1,2}\s*[:h]|\d")
    textos = list(_todos_los_textos())
    assert textos  # el test mira textos de verdad
    for mensaje in textos:
        assert not hora_exacta.search(mensaje.titulo + " " + mensaje.cuerpo), mensaje


def test_notification_bodies_are_plain_text_not_markdown() -> None:
    for mensaje in _todos_los_textos():
        for marca in ("](", "**", "`", "<", ">"):
            assert marca not in mensaje.cuerpo
            assert marca not in mensaje.titulo
