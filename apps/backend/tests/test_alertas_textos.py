"""Textos de las notificaciones de alertas push (FRA-354, T4.2).

Los textos son un BORRADOR que el dueño aprueba antes del merge: estos tests fijan la forma (franjas del
día con su rango, aviso de granizo, leyenda, sin la hora puntual de la tormenta), no la última palabra de
cada frase.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.services.alertas import umbrales
from app.services.alertas.regla import HoraTormenta, ResultadoRegla
from app.services.alertas.textos import (
    FRANJAS,
    LEYENDA,
    Mensaje,
    franja,
    franjas_de,
    franjas_granizo,
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


RANGOS = {
    "madrugada": "0 a 6 h",
    "mañana": "6 a 12 h",
    "tarde": "12 a 18 h",
    "noche": "18 a 24 h",
}


def _hora(hora_ar: int, dia: int = 9, codigo: int | None = 95) -> HoraTormenta:
    momento = datetime(2026, 10, dia, hora_ar, tzinfo=_AR)
    return HoraTormenta(
        hora=f"{hora_ar:02d}:00",
        timestamp=int(momento.timestamp()),
        weather_code=codigo,
        cape_j_kg=None if codigo is not None else 3000.0,
        motivo="codigo" if codigo is not None else "cape",
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
# Granizo: solo lo que el modelo marca (códigos 96 y 99)
# ---------------------------------------------------------------------------


def test_the_hail_codes_are_the_wmo_thunderstorm_with_hail_inside_the_storm_codes() -> (
    None
):
    assert umbrales.CODIGOS_GRANIZO == frozenset({96, 99})
    assert umbrales.CODIGOS_GRANIZO <= umbrales.CODIGOS_TORMENTA


def test_franjas_granizo_only_counts_hours_with_a_hail_code() -> None:
    resultado = ResultadoRegla(
        horas=(_hora(14, codigo=95), _hora(15, codigo=96), _hora(20, codigo=99))
    )
    assert franjas_granizo(resultado) == ("tarde", "noche")


@pytest.mark.parametrize("codigo", [95, 97, 98, None])
def test_franjas_granizo_ignores_storms_without_a_hail_code(codigo) -> None:
    # `None` es una hora de tormenta marcada solo por CAPE: eso no dice que haya granizo.
    assert franjas_granizo(ResultadoRegla(horas=(_hora(15, codigo=codigo),))) == ()


def test_franjas_granizo_without_storm_is_empty() -> None:
    assert franjas_granizo(ResultadoRegla(horas=())) == ()


# ---------------------------------------------------------------------------
# Los tres textos
# ---------------------------------------------------------------------------


def test_the_legend_is_the_approved_wording() -> None:
    assert LEYENDA == LEYENDA_ESPERADA


@pytest.mark.parametrize(
    ("franjas", "frase"),
    [
        (("tarde",), "a la tarde (12 a 18 h)"),
        (("tarde", "noche"), "a la tarde (12 a 18 h) y a la noche (18 a 24 h)"),
        (
            ("madrugada", "mañana", "tarde"),
            "de madrugada (0 a 6 h), a la mañana (6 a 12 h) y a la tarde (12 a 18 h)",
        ),
        (
            ("madrugada", "mañana", "tarde", "noche"),
            (
                "de madrugada (0 a 6 h), a la mañana (6 a 12 h), a la tarde (12 a 18 h) "
                "y a la noche (18 a 24 h)"
            ),
        ),
        (("madrugada",), "de madrugada (0 a 6 h)"),
        (("mañana", "noche"), "a la mañana (6 a 12 h) y a la noche (18 a 24 h)"),
    ],
)
def test_aviso_manana_joins_one_to_four_franjas_with_their_range(
    franjas, frase: str
) -> None:
    mensaje = texto_aviso_manana(CORDOBA, franjas)

    assert mensaje == Mensaje(
        titulo="SkyPulse · Córdoba",
        cuerpo=f"Posibles tormentas mañana {frase}. {LEYENDA_ESPERADA}",
    )


def test_aviso_manana_matches_the_owner_corrected_draft() -> None:
    mensaje = texto_aviso_manana(CORDOBA, ("tarde", "noche"))
    assert mensaje.titulo == "SkyPulse · Córdoba"
    assert mensaje.cuerpo == (
        "Posibles tormentas mañana a la tarde (12 a 18 h) y a la noche (18 a 24 h). "
        "Pronóstico de SkyPulse, no es un aviso oficial. Consultá los avisos del SMN en smn.gob.ar"
    )


@pytest.mark.parametrize(
    ("franjas", "frase"),
    [
        (("noche",), "a la noche (18 a 24 h)"),
        (("tarde", "noche"), "a la tarde (12 a 18 h) y a la noche (18 a 24 h)"),
        (
            ("mañana", "tarde", "noche"),
            "a la mañana (6 a 12 h), a la tarde (12 a 18 h) y a la noche (18 a 24 h)",
        ),
    ],
)
def test_aviso_hoy_says_today_with_the_same_joins(franjas, frase: str) -> None:
    mensaje = texto_aviso_hoy(CORDOBA, franjas)

    assert mensaje.titulo == "SkyPulse · Córdoba"
    assert mensaje.cuerpo == f"Posibles tormentas hoy {frase}. {LEYENDA_ESPERADA}"


def test_franjas_are_reordered_and_deduplicated() -> None:
    mensaje = texto_aviso_manana(CORDOBA, ("noche", "tarde", "noche"))
    assert "mañana a la tarde (12 a 18 h) y a la noche (18 a 24 h)." in mensaje.cuerpo


# --- granizo ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "dia"), [(texto_aviso_manana, "mañana"), (texto_aviso_hoy, "hoy")]
)
def test_hail_in_every_franja_says_possible_hail_once(texto, dia: str) -> None:
    mensaje = texto(CORDOBA, ("tarde", "noche"), granizo=("tarde", "noche"))

    assert mensaje.cuerpo == (
        f"Posibles tormentas {dia} a la tarde (12 a 18 h) y a la noche (18 a 24 h). "
        f"Posible granizo. {LEYENDA_ESPERADA}"
    )


@pytest.mark.parametrize(
    ("texto", "dia"), [(texto_aviso_manana, "mañana"), (texto_aviso_hoy, "hoy")]
)
def test_hail_in_only_some_franjas_names_them(texto, dia: str) -> None:
    mensaje = texto(CORDOBA, ("tarde", "noche"), granizo=("tarde",))

    assert mensaje.cuerpo == (
        f"Posibles tormentas {dia} a la tarde (12 a 18 h) y a la noche (18 a 24 h). "
        f"Posible granizo a la tarde (12 a 18 h). {LEYENDA_ESPERADA}"
    )


@pytest.mark.parametrize("texto", [texto_aviso_manana, texto_aviso_hoy])
def test_without_hail_the_text_does_not_mention_it(texto) -> None:
    for granizo in ((), None):
        kwargs = {} if granizo is None else {"granizo": granizo}
        assert "granizo" not in texto(CORDOBA, ("tarde", "noche"), **kwargs).cuerpo


@pytest.mark.parametrize("texto", [texto_aviso_manana, texto_aviso_hoy])
def test_hail_outside_the_storm_franjas_is_a_bug(texto) -> None:
    with pytest.raises(ValueError):
        texto(CORDOBA, ("tarde",), granizo=("noche",))


@pytest.mark.parametrize("texto", [texto_aviso_manana, texto_aviso_hoy])
def test_an_unknown_hail_franja_is_a_bug(texto) -> None:
    with pytest.raises(ValueError):
        texto(CORDOBA, ("tarde",), granizo=("mediodia",))


def test_hail_is_reordered_and_deduplicated_like_the_franjas() -> None:
    mensaje = texto_aviso_manana(
        CORDOBA, ("tarde", "noche"), granizo=("noche", "tarde", "noche")
    )
    assert "Posible granizo. " in mensaje.cuerpo
    assert mensaje.cuerpo.count("granizo") == 1


@pytest.mark.parametrize("texto", [texto_aviso_manana, texto_aviso_hoy])
def test_an_alert_without_franjas_is_a_bug(texto) -> None:
    with pytest.raises(ValueError):
        texto(CORDOBA, ())


@pytest.mark.parametrize("texto", [texto_aviso_manana, texto_aviso_hoy])
def test_an_unknown_franja_is_a_bug(texto) -> None:
    with pytest.raises(ValueError):
        texto(CORDOBA, ("mediodia",))


def test_prueba_says_it_is_a_test_and_that_automatic_alerts_are_not_active_yet() -> None:
    mensaje = texto_prueba(CORDOBA)

    assert mensaje == Mensaje(
        titulo="SkyPulse · Prueba",
        cuerpo=(
            "Esto es un aviso de prueba para Córdoba. "
            "Los avisos automáticos de tormenta todavía no están activos."
        ),
    )
    assert texto_prueba(zona_por_slug("san-salvador-de-jujuy")).cuerpo.startswith(
        "Esto es un aviso de prueba para San Salvador de Jujuy."
    )


def test_prueba_does_not_suggest_that_storm_alerts_are_ready() -> None:
    """Es el único aviso que se envía hoy: no puede decir 'así vas a ver los avisos' ni 'está todo listo'."""
    for zona in ZONAS:
        cuerpo = texto_prueba(zona).cuerpo
        assert "Así vas a ver" not in cuerpo
        assert "todo listo" not in cuerpo
        assert "todavía no están activos" in cuerpo


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
            for granizo in ((), franjas[:1], franjas):
                yield texto_aviso_manana(zona, franjas, granizo=granizo)
                yield texto_aviso_hoy(zona, franjas, granizo=granizo)


def test_alert_texts_always_end_with_the_legend_and_prueba_does_not_need_it() -> None:
    for zona in ZONAS:
        for franjas in _COMBINACIONES:
            for granizo in ((), franjas[:1], franjas):
                for mensaje in (
                    texto_aviso_manana(zona, franjas, granizo=granizo),
                    texto_aviso_hoy(zona, franjas, granizo=granizo),
                ):
                    assert mensaje.cuerpo.endswith(LEYENDA_ESPERADA), zona.slug


def test_no_text_names_an_exact_hour_only_the_fixed_franja_ranges() -> None:
    # Lo único con números son los rangos fijos de las franjas ("12 a 18 h"): nunca la hora de la tormenta.
    textos = list(_todos_los_textos())
    assert textos  # el test mira textos de verdad
    for mensaje in textos:
        completo = mensaje.titulo + " " + mensaje.cuerpo
        sin_rangos = completo
        for rango in RANGOS.values():
            sin_rangos = sin_rangos.replace(f"({rango})", "")
        assert not re.search(r"\d", sin_rangos), mensaje


def test_the_franja_ranges_in_the_text_are_the_ones_that_franja_uses() -> None:
    # El rango que dice el texto tiene que coincidir con las horas que `franja()` asigna a esa franja.
    for nombre, rango in RANGOS.items():
        desde, hasta = (int(n) for n in re.findall(r"\d+", rango))
        horas = [h for h in range(24) if franja(h) == nombre]
        assert (horas[0], horas[-1] + 1) == (desde, hasta), nombre
        mensaje = texto_aviso_manana(CORDOBA, (nombre,))
        assert f"({rango})" in mensaje.cuerpo


def test_notification_bodies_are_plain_text_not_markdown() -> None:
    for mensaje in _todos_los_textos():
        for marca in ("](", "**", "`", "<", ">"):
            assert marca not in mensaje.cuerpo
            assert marca not in mensaje.titulo
