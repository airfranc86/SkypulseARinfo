"""Íconos del tiempo según código WMO y nubosidad (chubascos, nieve, tormenta y granizo).

La convección es muy localizada: un día de sol puede traer chubascos, tormenta o granizo fuerte a unos
kilómetros. Por eso el ícono de 80 a 86 y de 95 a 99 depende de la nubosidad. Cubierto (3) y niebla
(45, 48) siguen sin sol (decisión del 2026-06-04) y el código 1 no depende de la nubosidad.

Bordes de nubosidad (%): poca < 25, parcial de 25 a 62 inclusive, mucha > 62.
"""
from __future__ import annotations

import pytest

from app.services.daily_anchor import resolve_row_icon
from app.utils import wmo_codes
from app.utils.wmo_codes import WMO_CODE_MAP, describe_wmo, resolve_daily_icon

# (code, poca, parcial, mucha); "{t}" es day/night.
CLOUD_AWARE = [
    (80, "mostly-clear-{t}-rain", "partly-cloudy-{t}-rain", "rain"),
    (81, "mostly-clear-{t}-rain", "partly-cloudy-{t}-rain", "rain"),
    (82, "mostly-clear-{t}-rain", "partly-cloudy-{t}-rain", "rain"),
    (85, "mostly-clear-{t}-snow", "partly-cloudy-{t}-snow", "snow"),
    (86, "mostly-clear-{t}-snow", "partly-cloudy-{t}-snow", "snow"),
    (95, "thunderstorms-mostly-clear-{t}", "thunderstorms-{t}", "thunderstorms"),
    (96, "thunderstorms-mostly-clear-{t}-hail", "thunderstorms-{t}-hail", "thunderstorms-overcast-hail"),
    (99, "thunderstorms-mostly-clear-{t}-hail", "thunderstorms-{t}-hail", "thunderstorms-overcast-hail"),
]

# El ícono de hoy cuando no hay dato de nubosidad.
WITHOUT_DATA_DAY = {
    80: "partly-cloudy-day-rain",
    81: "rain",
    82: "rain",
    85: "snow",
    86: "snow",
    95: "thunderstorms",
    96: "thunderstorms-overcast-hail",
    99: "thunderstorms-overcast-hail",
}
WITHOUT_DATA_NIGHT = {**WITHOUT_DATA_DAY, 80: "partly-cloudy-night-rain"}

# Nubosidad de cada nivel, y los bordes que importan.
LEVEL_SAMPLES = [
    (0.0, 0),
    (10.0, 0),
    (24.9, 0),
    (25.0, 1),
    (40.0, 1),
    (62.0, 1),
    (62.1, 2),
    (80.0, 2),
    (100.0, 2),
]
ALL_COVERS = [None, 0.0, 24.9, 25.0, 50.0, 62.0, 62.1, 100.0]


def _expected(template: str, is_day: bool) -> str:
    return template.format(t="day" if is_day else "night")


# ---------------------------------------------------------------------------
# Códigos que dependen de la nubosidad
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_day", [True, False], ids=["day", "night"])
@pytest.mark.parametrize("cover,level", LEVEL_SAMPLES)
@pytest.mark.parametrize("code,poca,parcial,mucha", CLOUD_AWARE)
def test_icon_follows_cloud_cover(code, poca, parcial, mucha, cover, level, is_day):
    template = (poca, parcial, mucha)[level]
    _, icon = describe_wmo(code, is_day, cover)
    assert icon == _expected(template, is_day), f"WMO {code}, {cover} %"


def test_borders_of_cloud_cover_are_25_and_62_inclusive():
    assert describe_wmo(95, True, 24.9)[1] == "thunderstorms-mostly-clear-day"
    assert describe_wmo(95, True, 25.0)[1] == "thunderstorms-day"
    assert describe_wmo(95, True, 62.0)[1] == "thunderstorms-day"
    assert describe_wmo(95, True, 62.1)[1] == "thunderstorms"


def test_thresholds_are_the_ones_of_the_daily_sky_icon():
    assert wmo_codes.CLEAR_BELOW_PCT == 25.0
    assert wmo_codes.PARTLY_UP_TO_PCT == 62.0


@pytest.mark.parametrize("code", sorted(WITHOUT_DATA_DAY))
def test_without_cloud_cover_the_icon_is_todays(code):
    assert describe_wmo(code, True, None)[1] == WITHOUT_DATA_DAY[code]
    assert describe_wmo(code, False, None)[1] == WITHOUT_DATA_NIGHT[code]
    # Sin pasar el argumento es lo mismo (firma compatible).
    assert describe_wmo(code, True)[1] == WITHOUT_DATA_DAY[code]
    assert describe_wmo(code, False)[1] == WITHOUT_DATA_NIGHT[code]


@pytest.mark.parametrize("code", [96, 99])
def test_hail_without_data_is_the_overcast_hail_and_plain_hail_is_retired(code):
    assert describe_wmo(code, True)[1] == "thunderstorms-overcast-hail"
    assert describe_wmo(code, False)[1] == "thunderstorms-overcast-hail"
    icons = {v for entry in WMO_CODE_MAP.values() for v in (entry["icon_day"], entry["icon_night"])}
    assert "hail" not in icons


def test_hail_with_sun_over_a_sunny_day_shows_sun_and_hail():
    # El caso real: día de sol con granizo fuerte a unos kilómetros.
    assert describe_wmo(99, True, 10.0)[1] == "thunderstorms-mostly-clear-day-hail"
    assert describe_wmo(99, False, 10.0)[1] == "thunderstorms-mostly-clear-night-hail"


# ---------------------------------------------------------------------------
# Código 1: mayormente despejado, no depende de la nubosidad
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cover", ALL_COVERS)
def test_code_1_is_mostly_clear_whatever_the_cloud_cover(cover):
    assert describe_wmo(1, True, cover)[1] == "mostly-clear-day"
    assert describe_wmo(1, False, cover)[1] == "mostly-clear-night"


def test_code_1_without_cover_argument():
    assert describe_wmo(1, True)[1] == "mostly-clear-day"
    assert describe_wmo(1, False)[1] == "mostly-clear-night"


# ---------------------------------------------------------------------------
# Sin cambios: cubierto, niebla y el resto no miran la nubosidad
# ---------------------------------------------------------------------------

UNCHANGED = {
    0: ("clear-day", "clear-night"),
    2: ("partly-cloudy-day", "partly-cloudy-night"),
    3: ("overcast", "overcast"),
    45: ("fog", "fog"),
    48: ("fog", "fog"),
    51: ("overcast-drizzle", "overcast-drizzle"),
    53: ("overcast-drizzle", "overcast-drizzle"),
    55: ("overcast-drizzle", "overcast-drizzle"),
    56: ("sleet", "sleet"),
    57: ("sleet", "sleet"),
    61: ("partly-cloudy-day-rain", "partly-cloudy-night-rain"),
    63: ("rain", "rain"),
    65: ("rain", "rain"),
    66: ("sleet", "sleet"),
    67: ("sleet", "sleet"),
    71: ("partly-cloudy-day-snow", "partly-cloudy-night-snow"),
    73: ("snow", "snow"),
    75: ("snow", "snow"),
    77: ("snow", "snow"),
}


@pytest.mark.parametrize("cover", ALL_COVERS)
@pytest.mark.parametrize("code", sorted(UNCHANGED))
def test_other_codes_ignore_cloud_cover(code, cover):
    day, night = UNCHANGED[code]
    assert describe_wmo(code, True, cover)[1] == day
    assert describe_wmo(code, False, cover)[1] == night


@pytest.mark.parametrize("cover", ALL_COVERS)
@pytest.mark.parametrize("code", [3, 45, 48])
def test_overcast_and_fog_never_get_a_sun(code, cover):
    for is_day in (True, False):
        icon = describe_wmo(code, is_day, cover)[1]
        assert icon in {"overcast", "fog"}
        assert "day" not in icon and "night" not in icon and "clear" not in icon


@pytest.mark.parametrize("code", sorted(WMO_CODE_MAP))
def test_descriptions_do_not_depend_on_cloud_cover(code):
    base = describe_wmo(code, True)[0]
    for cover in ALL_COVERS:
        assert describe_wmo(code, True, cover)[0] == base
        assert describe_wmo(code, False, cover)[0] == base


@pytest.mark.parametrize("code", [None, 999, -1])
def test_unknown_code_keeps_the_clear_fallback_with_any_cover(code):
    assert describe_wmo(code, True, 90.0) == ("Sin datos", "clear-day")
    assert describe_wmo(code, False, 90.0) == ("Sin datos", "clear-night")


# ---------------------------------------------------------------------------
# Pronóstico diario: nubosidad media del día, is_day=True, overrides intactos
# ---------------------------------------------------------------------------

def test_resolve_daily_icon_uses_the_cloud_cover():
    assert resolve_daily_icon(95, 70.0, is_day=True, cloud_cover=10.0) == "thunderstorms-mostly-clear-day"
    assert resolve_daily_icon(95, 70.0, is_day=True, cloud_cover=50.0) == "thunderstorms-day"
    assert resolve_daily_icon(95, 70.0, is_day=True, cloud_cover=90.0) == "thunderstorms"


def test_resolve_daily_icon_without_cover_is_todays():
    assert resolve_daily_icon(95, 70.0, is_day=True) == "thunderstorms"
    assert resolve_daily_icon(96, 80.0, is_day=True) == "thunderstorms-overcast-hail"
    assert resolve_daily_icon(99, 50.0, is_day=False) == "thunderstorms-overcast-hail"


def test_row_icon_sunny_day_with_hail_shows_sun_and_hail():
    assert resolve_row_icon(99, 0.0, 10.0, 10.0) == "thunderstorms-mostly-clear-day-hail"
    assert resolve_row_icon(96, 0.0, 10.0, 40.0) == "thunderstorms-day-hail"
    assert resolve_row_icon(96, 0.0, 10.0, 90.0) == "thunderstorms-overcast-hail"


def test_row_icon_confirmed_showers_follow_the_cloud_cover():
    assert resolve_row_icon(80, 5.0, 40.0, 10.0) == "mostly-clear-day-rain"
    assert resolve_row_icon(81, 5.0, 40.0, 50.0) == "partly-cloudy-day-rain"
    assert resolve_row_icon(82, 5.0, 40.0, 90.0) == "rain"
    assert resolve_row_icon(85, 0.0, 40.0, 10.0) == "mostly-clear-day-snow"
    assert resolve_row_icon(86, 0.0, 40.0, 90.0) == "snow"


def test_row_icon_showers_without_rain_amount_keep_the_sky_icon_override():
    # <= 0,9 mm del ancla: el cielo por nubosidad, como hasta ahora (FRA-322).
    assert resolve_row_icon(80, 0.5, 40.0, 10.0) == "clear-day"
    assert resolve_row_icon(81, 0.9, 40.0, 50.0) == "partly-cloudy-day"
    assert resolve_row_icon(82, 0.0, 40.0, 70.0) == "overcast"


def test_row_icon_overcast_override_is_unchanged_at_any_cover():
    for cover in ALL_COVERS:
        assert resolve_row_icon(3, 5.0, 80.0, cover) == "rain"
        assert resolve_row_icon(3, 5.0, 59.0, cover) == "overcast"
        assert resolve_row_icon(3, 0.9, 80.0, cover) == "overcast"
        assert resolve_row_icon(45, 0.0, 80.0, cover) == "fog"


def test_row_icon_code_1_is_mostly_clear_day_at_any_cover():
    for cover in ALL_COVERS:
        assert resolve_row_icon(1, 0.0, 0.0, cover) == "mostly-clear-day"


# ---------------------------------------------------------------------------
# "Ahora": el ícono del dashboard usa la nubosidad de la observación
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_rate_limit():
    """/dashboard permite 30 pedidos por minuto y el limitador es de toda la sesión."""
    from app.core.rate_limit import limiter

    limiter.reset()
    yield
    limiter.reset()


async def _now_icon(client, *, code, cloud_cover):
    from tests.test_dashboard import _dashboard_mocks, _make_current_response

    current = _make_current_response().model_copy(update={"weather_code": code, "cloud_cover": cloud_cover})
    with _dashboard_mocks(current=current):
        response = await client.get("/api/weather/dashboard?lat=-31.4&lon=-64.2")
    assert response.status_code == 200
    data = response.json()["current"]
    return data["icon"], data["is_day"]


@pytest.mark.integration
async def test_dashboard_now_icon_follows_the_cloud_cover(async_client, fresh_rate_limit):
    icon, is_day = await _now_icon(async_client, code=95, cloud_cover=10.0)
    assert icon == f"thunderstorms-mostly-clear-{'day' if is_day else 'night'}"

    icon, is_day = await _now_icon(async_client, code=95, cloud_cover=50.0)
    assert icon == f"thunderstorms-{'day' if is_day else 'night'}"

    icon, _ = await _now_icon(async_client, code=95, cloud_cover=90.0)
    assert icon == "thunderstorms"


@pytest.mark.integration
async def test_dashboard_now_icon_without_cloud_cover_is_todays(async_client, fresh_rate_limit):
    icon, _ = await _now_icon(async_client, code=99, cloud_cover=None)
    assert icon == "thunderstorms-overcast-hail"
