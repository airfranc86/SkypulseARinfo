"""Tests for the pure blend of the dashboard "now": METAR observation over the Open-Meteo model."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.weather import (
    CurrentDetailedSchema,
    ModelTempDiffersNotice,
    PossibleChangeNotice,
    ReportedPhenomenonNotice,
)
from app.services.calculators import compute_sensacion_termica
from app.services.current_blend import blend_current
from app.services.metar_observation import MetarObservation, MetarSelection
from app.utils.wind import wind_icon_code, wind_intensity_tier

OBS_TIME = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc)
MODEL_TIME = datetime(2026, 10, 5, 21, 15, tzinfo=timezone.utc)
FRESH = OBS_TIME + timedelta(minutes=10)


def _base(**overrides: object) -> CurrentDetailedSchema:
    """Dashboard `current` built from the model (Open-Meteo)."""
    values: dict = {
        "temp_c": 20.0,
        "feels_like_c": 19.0,
        "humidity": 60.0,
        "wind_speed_kmh": 10.0,
        "wind_dir_deg": 90.0,
        "wind_dir_cardinal": "E",
        "uv_index": 5.0,
        "description": "Despejado",
        "icon": "clear-day",
        "is_day": True,
        "source": "openmeteo",
        "observed_at": MODEL_TIME,
        "wind_icon": wind_icon_code(10.0),
        "wind_intensity": wind_intensity_tier(10.0),
        "wind_gust_kmh": 18.0,
    }
    values.update(overrides)
    return CurrentDetailedSchema(**values)


def _obs(**overrides: object) -> MetarObservation:
    base = MetarObservation(
        icao="SAAR",
        observed_at=OBS_TIME,
        temp_c=22.0,
        dewpoint_c=11.0,
        humidity=50.0,
        wind_dir_deg=80.0,
        wind_speed_kmh=14.8,
        wind_gust_kmh=None,
        wx_string=None,
        raw="METAR SAAR 052100Z 08008KT CAVOK 22/11 Q1013",
    )
    return replace(base, **overrides)


def _ok(obs: MetarObservation | None = None) -> MetarSelection:
    return MetarSelection(
        reason="metar_ok", icao="SAAR", name="Rosario", distance_km=12.6,
        observation=obs or _obs(),
    )


def _blend(
    base: CurrentDetailedSchema | None = None,
    selection: MetarSelection | None = None,
    *,
    precip: float | None = 0.0,
    code: int | None = 0,
    now: datetime = FRESH,
) -> CurrentDetailedSchema:
    return blend_current(
        base or _base(),
        selection or _ok(),
        model_precip_1h_mm=precip,
        model_weather_code=code,
        now=now,
    )


def _codes(result: CurrentDetailedSchema) -> list[str]:
    return [n.code for n in result.notices]


def _possible_change(result: CurrentDetailedSchema) -> PossibleChangeNotice | None:
    return next((n for n in result.notices if isinstance(n, PossibleChangeNotice)), None)


# ---------------------------------------------------------------------------
# Valid METAR
# ---------------------------------------------------------------------------

def test_valid_metar_takes_observed_fields_and_keeps_model_sky():
    result = _blend()

    assert result.source == "metar"
    assert result.source_reason == "metar_ok"
    assert result.temp_c == 22.0
    assert result.humidity == 50.0
    assert result.wind_speed_kmh == 14.8
    assert result.wind_dir_deg == 80.0
    assert result.wind_dir_cardinal == "E"
    assert result.wind_gust_kmh is None
    assert result.feels_like_c == compute_sensacion_termica(22.0, 50.0, 14.8).feels_like_c
    assert result.wind_icon == wind_icon_code(14.8)
    assert result.wind_intensity == wind_intensity_tier(14.8)
    assert result.observed_at == OBS_TIME
    assert result.model_temp_c == 20.0
    assert result.station is not None
    assert (result.station.icao, result.station.name, result.station.distance_km) == (
        "SAAR", "Rosario", 12.6,
    )
    # Sky, icon, description and UV stay from the model.
    assert (result.description, result.icon, result.uv_index, result.is_day) == (
        "Despejado", "clear-day", 5.0, True,
    )
    assert result.notices == []


def test_feels_like_is_recalculated_in_the_cold():
    result = _blend(selection=_ok(_obs(temp_c=2.0, dewpoint_c=0.0, humidity=87.0,
                                       wind_speed_kmh=30.0)))
    assert result.feels_like_c == compute_sensacion_termica(2.0, 87.0, 30.0).feels_like_c
    assert result.feels_like_c < 2.0


def test_variable_wind_has_no_direction_or_cardinal():
    result = _blend(selection=_ok(_obs(wind_dir_deg=None, wind_speed_kmh=5.6)))
    assert result.wind_dir_deg is None
    assert result.wind_dir_cardinal is None
    assert result.wind_speed_kmh == 5.6


def test_metar_gust_replaces_model_gust():
    result = _blend(selection=_ok(_obs(wind_gust_kmh=46.3)))
    assert result.wind_gust_kmh == 46.3


# ---------------------------------------------------------------------------
# Without a valid METAR
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "reason", ["metar_too_far", "metar_unavailable", "metar_stale", "metar_missing_fields"]
)
def test_without_valid_metar_everything_comes_from_the_model(reason):
    selection = MetarSelection(
        reason=reason, icao="SAAR", name="Rosario", distance_km=12.6, observation=None
    )
    result = _blend(selection=selection)

    assert result == _base(source_reason=reason)
    assert result.source == "openmeteo"
    assert result.observed_at == MODEL_TIME
    assert result.wind_gust_kmh == 18.0
    assert result.station is None
    assert result.model_temp_c is None
    assert result.notices == []


def test_stale_metar_observation_is_ignored_even_if_attached():
    selection = MetarSelection(
        reason="metar_stale", icao="SAAR", name="Rosario", distance_km=12.6, observation=_obs()
    )
    assert _blend(selection=selection).source == "openmeteo"


# ---------------------------------------------------------------------------
# model_temp_differs (>= 5 °C)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("metar_temp", "expected"), [(25.0, True), (15.0, True), (24.9, False), (15.1, False)]
)
def test_model_temp_differs_from_five_degrees(metar_temp, expected):
    result = _blend(selection=_ok(_obs(temp_c=metar_temp)))
    notice = next((n for n in result.notices if isinstance(n, ModelTempDiffersNotice)), None)
    assert (notice is not None) is expected
    if notice is not None:
        assert notice.model_temp_c == 20.0


def test_no_temp_notice_without_model_temperature():
    result = _blend(base=_base(temp_c=None), selection=_ok(_obs(temp_c=40.0)))
    assert "model_temp_differs" not in _codes(result)
    assert result.model_temp_c is None


# ---------------------------------------------------------------------------
# possible_change: only when the METAR is older than 30 min
# ---------------------------------------------------------------------------

def test_no_possible_change_at_exactly_thirty_minutes():
    result = _blend(base=_base(wind_speed_kmh=60.0), now=OBS_TIME + timedelta(minutes=30))
    assert _possible_change(result) is None


def test_possible_change_after_thirty_minutes():
    result = _blend(base=_base(wind_speed_kmh=60.0), now=OBS_TIME + timedelta(minutes=31))
    notice = _possible_change(result)
    assert notice is not None
    assert notice.reasons == ["wind"]
    assert notice.model_wind_speed_kmh == 60.0
    assert notice.model_wind_gust_kmh == 18.0


LATE = OBS_TIME + timedelta(minutes=45)


@pytest.mark.parametrize(
    ("model_wind", "model_gust", "expected"),
    [
        (29.8, None, True),    # 14.8 + 15 exactly
        (29.7, None, False),
        (10.0, 29.8, True),    # the model gust counts too
        (10.0, 29.7, False),
    ],
)
def test_wind_reason_from_fifteen_kmh_over_metar(model_wind, model_gust, expected):
    result = _blend(base=_base(wind_speed_kmh=model_wind, wind_gust_kmh=model_gust), now=LATE)
    notice = _possible_change(result)
    assert (notice is not None and "wind" in notice.reasons) is expected


def test_wind_reason_compares_against_the_metar_gust():
    obs = _obs(wind_speed_kmh=14.8, wind_gust_kmh=40.0)
    result = _blend(base=_base(wind_speed_kmh=50.0), selection=_ok(obs), now=LATE)
    assert _possible_change(result) is None
    result = _blend(base=_base(wind_speed_kmh=55.0), selection=_ok(obs), now=LATE)
    assert _possible_change(result) is not None


@pytest.mark.parametrize(
    ("precip", "expected"), [(0.9, True), (0.89, False), (0.5, False), (None, False)]
)
def test_rain_reason_from_point_nine_millimetres(precip, expected):
    notice = _possible_change(_blend(precip=precip, now=LATE))
    assert (notice is not None and notice.reasons == ["rain"]) is expected
    if notice is not None:
        assert notice.model_precip_1h_mm == precip


@pytest.mark.parametrize("wx", ["-RA", "DZ", "VCSH", "+TSRA"])
def test_no_rain_reason_when_metar_already_reports_it(wx):
    result = _blend(selection=_ok(_obs(wx_string=wx)), precip=3.0, now=LATE)
    notice = _possible_change(result)
    assert notice is None or "rain" not in notice.reasons


@pytest.mark.parametrize(("code", "expected"), [(94, False), (95, True), (99, True), (100, False)])
def test_storm_reason_for_codes_95_to_99(code, expected):
    notice = _possible_change(_blend(code=code, now=LATE))
    assert (notice is not None and notice.reasons == ["storm"]) is expected
    if notice is not None:
        assert notice.model_weather_code == code


def test_no_storm_reason_when_metar_reports_ts():
    result = _blend(selection=_ok(_obs(wx_string="TS")), code=95, now=LATE)
    assert _possible_change(result) is None


def test_possible_change_lists_every_reason():
    result = _blend(base=_base(wind_speed_kmh=60.0), precip=2.0, code=97, now=LATE)
    notice = _possible_change(result)
    assert notice is not None
    assert notice.reasons == ["wind", "rain", "storm"]


def test_possible_change_ignores_missing_model_values():
    result = _blend(base=_base(wind_speed_kmh=None, wind_gust_kmh=None), precip=None,
                    code=None, now=LATE)
    assert _possible_change(result) is None


# ---------------------------------------------------------------------------
# reported_phenomenon
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("wx", "kind"),
    [("-RA", "rain"), ("DZ BR", "rain"), ("-SHRA", "rain"), ("TS", "storm"), ("+TSRA", "storm")],
)
def test_reported_phenomenon_for_rain_and_storm(wx, kind):
    result = _blend(selection=_ok(_obs(wx_string=wx)))
    notice = next(n for n in result.notices if isinstance(n, ReportedPhenomenonNotice))
    assert (notice.kind, notice.wx) == (kind, wx)


@pytest.mark.parametrize("wx", ["BR", "FG", "HZ", None, ""])
def test_other_phenomena_do_not_generate_a_notice(wx):
    result = _blend(selection=_ok(_obs(wx_string=wx)))
    assert "reported_phenomenon" not in _codes(result)


def test_notices_are_ordered_and_combined():
    obs = _obs(temp_c=27.0, wx_string="-RA")
    result = _blend(base=_base(wind_speed_kmh=60.0), selection=_ok(obs), now=LATE)
    assert _codes(result) == ["model_temp_differs", "possible_change", "reported_phenomenon"]


def test_blend_does_not_mutate_the_base():
    base = _base()
    _blend(base=base)
    assert base == _base()
