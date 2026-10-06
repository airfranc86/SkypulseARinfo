"""Tests de la regla de tormenta para alertas push (FRA-351, T1)."""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.alertas import regla, umbrales, zonas
from tests.hourly_fixtures import AR, make_hourly

_CITIES_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "cities-ar.ts"
_CITY_RE = re.compile(
    r"\{\s*name:\s*'([^']+)',\s*province:\s*'([^']+)',\s*lat:\s*(-?[\d.]+),\s*lon:\s*(-?[\d.]+)\s*\}"
)


def _ciudades_del_frontend() -> list[tuple[str, str, float, float]]:
    texto = _CITIES_TS.read_text(encoding="utf-8")
    return [(n, p, float(la), float(lo)) for n, p, la, lo in _CITY_RE.findall(texto)]


def test_codigos_de_tormenta_son_95_a_99():
    assert umbrales.CODIGOS_TORMENTA == frozenset({95, 96, 97, 98, 99})
    assert 94 not in umbrales.CODIGOS_TORMENTA


def test_cape_de_tormenta_es_2500():
    assert umbrales.CAPE_TORMENTA_J_KG == 2500.0


def test_revisiones_de_hoy_y_de_manana():
    assert umbrales.REVISIONES_HOY == (7, 10, 13, 16, 19)
    assert umbrales.REVISION_MANANA == 21


def test_silencio_de_22_a_7():
    assert umbrales.SILENCIO_DESDE_H == 22
    assert umbrales.SILENCIO_HASTA_H == 7


def test_ninguna_revision_cae_en_silencio():
    horas = (*umbrales.REVISIONES_HOY, umbrales.REVISION_MANANA)
    for h in horas:
        en_silencio = h >= umbrales.SILENCIO_DESDE_H or h < umbrales.SILENCIO_HASTA_H
        assert not en_silencio, f"la revisión de las {h} h cae en silencio"


# --- Zonas (T1.2): paridad con apps/frontend/src/lib/cities-ar.ts -------------


def test_hay_tantas_zonas_como_ciudades_en_el_frontend():
    ciudades = _ciudades_del_frontend()
    assert len(ciudades) > 0, "el regex no encontró ciudades en cities-ar.ts"
    assert len(zonas.ZONAS) == len(ciudades)


def test_zonas_coinciden_con_cities_ar_en_orden():
    esperado = _ciudades_del_frontend()
    actual = [(z.nombre, z.provincia, z.lat, z.lon) for z in zonas.ZONAS]
    assert actual == esperado


def test_slugs_unicos_y_sin_tildes():
    slugs = [z.slug for z in zonas.ZONAS]
    assert len(set(slugs)) == len(slugs)
    for s in slugs:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s), s


@pytest.mark.parametrize(
    ("nombre", "slug"),
    [
        ("Córdoba", "cordoba"),
        ("San Salvador de Jujuy", "san-salvador-de-jujuy"),
        ("Malargüe", "malargue"),
        ("Buenos Aires", "buenos-aires"),
    ],
)
def test_slug_de_zonas_conocidas(nombre, slug):
    assert zonas.zona_por_slug(slug).nombre == nombre


def test_zona_por_slug_desconocido_da_none():
    assert zonas.zona_por_slug("no-existe") is None


# --- Regla (T1.3): función pura sobre la serie horaria de ECMWF ---------------


@pytest.mark.parametrize(
    ("codigo", "cape", "esperado"),
    [
        (95, None, True),
        (96, 0.0, True),
        (99, 0.0, True),
        (94, 0.0, False),
        (80, 100.0, False),
        (0, 2500.0, True),
        (0, 2499.9, False),
        (None, 2500.0, True),
        (None, None, False),
        (None, 2499.0, False),
    ],
)
def test_es_hora_de_tormenta(codigo, cape, esperado):
    assert regla.es_hora_de_tormenta(codigo, cape) is esperado


def _ar(dia: int, hora: int) -> datetime:
    return datetime(2026, 9, dia, hora, 30, tzinfo=AR)


def test_ventana_de_revision_de_hoy_va_de_esa_hora_a_medianoche():
    for hora in umbrales.REVISIONES_HOY:
        inicio, fin = regla.ventana(_ar(19, hora))
        assert inicio == int(datetime(2026, 9, 19, hora, tzinfo=AR).timestamp())
        assert fin == int(datetime(2026, 9, 20, 0, tzinfo=AR).timestamp())


def test_ventana_de_las_21_es_todo_el_dia_siguiente():
    inicio, fin = regla.ventana(_ar(19, 21))
    assert inicio == int(datetime(2026, 9, 20, 0, tzinfo=AR).timestamp())
    assert fin == int(datetime(2026, 9, 21, 0, tzinfo=AR).timestamp())


@pytest.mark.parametrize("hora", [0, 3, 6, 8, 11, 20, 22, 23])
def test_ventana_es_none_fuera_de_las_revisiones(hora):
    assert regla.ventana(_ar(19, hora)) is None


def test_ventana_convierte_otras_zonas_horarias_a_argentina():
    diez_utc = datetime(2026, 9, 19, 10, 30, tzinfo=timezone.utc)  # 07:30 en Argentina
    assert regla.ventana(diez_utc) is not None
    assert regla.ventana(diez_utc)[0] == int(datetime(2026, 9, 19, 7, tzinfo=AR).timestamp())


def _ventana_de_hoy_desde(hora: int) -> tuple[int, int]:
    return regla.ventana(_ar(19, hora))


def test_codigo_95_en_la_ventana_da_tormenta_y_94_no():
    con_95 = make_hourly(weather_codes={15: 95})
    con_94 = make_hourly(weather_codes={15: 94})
    ventana = _ventana_de_hoy_desde(7)
    assert regla.evaluar_tormenta(con_95, *ventana).hay_tormenta is True
    assert regla.evaluar_tormenta(con_94, *ventana).hay_tormenta is False


def test_cape_2500_da_tormenta_y_2499_no():
    ventana = _ventana_de_hoy_desde(7)
    assert regla.evaluar_tormenta(make_hourly(cape_j_kg={15: 2500.0}), *ventana).hay_tormenta
    assert not regla.evaluar_tormenta(make_hourly(cape_j_kg={15: 2499.0}), *ventana).hay_tormenta


def test_datos_nulos_nunca_dan_tormenta():
    ventana = _ventana_de_hoy_desde(7)
    nulos = make_hourly(weather_codes={h: None for h in range(48)}, cape_j_kg={h: None for h in range(48)})
    assert not regla.evaluar_tormenta(nulos, *ventana).hay_tormenta
    vacia = make_hourly()
    vacia.weather_codes.clear()
    vacia.cape_j_kg.clear()
    assert not regla.evaluar_tormenta(vacia, *ventana).hay_tormenta
    assert not regla.evaluar_tormenta(None, *ventana).hay_tormenta


def test_fuera_de_la_ventana_no_cuenta():
    ventana = _ventana_de_hoy_desde(10)  # 10:00 de hoy a medianoche
    antes = make_hourly(weather_codes={5: 95})
    despues = make_hourly(weather_codes={24: 95})  # 00:00 de mañana: el fin es exclusivo
    assert not regla.evaluar_tormenta(antes, *ventana).hay_tormenta
    assert not regla.evaluar_tormenta(despues, *ventana).hay_tormenta


def test_el_inicio_de_la_ventana_es_inclusivo():
    ventana = _ventana_de_hoy_desde(10)
    assert regla.evaluar_tormenta(make_hourly(weather_codes={10: 95}), *ventana).hay_tormenta


def test_el_resultado_lista_las_horas_con_su_motivo():
    hourly = make_hourly(weather_codes={12: 95, 14: 95}, cape_j_kg={14: 3000.0, 16: 2600.0})
    res = regla.evaluar_tormenta(hourly, *_ventana_de_hoy_desde(7))
    assert [h.hora for h in res.horas] == ["12:00", "14:00", "16:00"]
    assert [h.motivo for h in res.horas] == ["codigo", "codigo+cape", "cape"]


def test_revision_de_hoy_mira_solo_hasta_la_medianoche():
    ahora = _ar(19, 13)
    de_hoy = make_hourly(weather_codes={17: 95})
    de_manana = make_hourly(weather_codes={30: 95})
    assert regla.evaluar_revision(de_hoy, ahora).hay_tormenta
    assert not regla.evaluar_revision(de_manana, ahora).hay_tormenta


def test_revision_de_las_21_mira_todo_el_dia_siguiente():
    ahora = _ar(19, 21)
    de_manana = make_hourly(weather_codes={24: 95})  # 00:00 de mañana
    ultima_hora = make_hourly(cape_j_kg={47: 2500.0})  # 23:00 de mañana
    de_hoy = make_hourly(weather_codes={22: 95})
    assert regla.evaluar_revision(de_manana, ahora).hay_tormenta
    assert regla.evaluar_revision(ultima_hora, ahora).hay_tormenta
    assert not regla.evaluar_revision(de_hoy, ahora).hay_tormenta


@pytest.mark.parametrize("hora", [22, 23, 0, 3, 6])
def test_en_el_silencio_no_se_evalua(hora):
    assert regla.evaluar_revision(make_hourly(weather_codes={30: 95}), _ar(19, hora)) is None
