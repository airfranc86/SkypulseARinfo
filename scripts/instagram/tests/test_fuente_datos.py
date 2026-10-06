"""Data adapter: the numbers must be the ones the web shows (ECMWF anchor, mean temperature)."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from report_factories import (
    ECMWF,
    GFS,
    TARGET,
    make_daily,
    make_daily_multi,
    make_ecmwf_rain,
    make_hourly,
    make_raw,
)

import fuente_datos
from ciudades import CABA, CITIES, CORDOBA, RESISTENCIA, City
from fuente_datos import (
    DatosNoDisponibles,
    build_report_data,
    collect_reports,
    day_slots,
    day_temperatures,
)
from reglas import RAIN_THRESHOLD_MM

TARGET_INDEX = 2  # TARGET is the third day of the synthetic forecast
DRY_ECMWF = make_ecmwf_rain()


def build(daily, hourly, city: City = CORDOBA, target: date = TARGET, ecmwf_rain=DRY_ECMWF):
    return build_report_data(city, target, daily, hourly, ecmwf_rain=ecmwf_rain)


def test_temperature_is_the_whole_degree_mean_of_both_models_rounded_half_up() -> None:
    daily = make_daily_multi(
        gfs=make_daily(at={TARGET_INDEX: {"temp_max": 20.0, "temp_min": 8.0}}),
        ecmwf=make_daily(at={TARGET_INDEX: {"temp_max": 23.0, "temp_min": 9.0}}),
    )
    data = build(daily, make_hourly())
    assert data.temp_max == 22  # 21.5 rounds up, like Math.round on the web
    assert data.temp_min == 9  # 8.5 rounds up


def test_rain_wind_code_and_direction_come_from_ecmwf_by_key_not_position() -> None:
    gfs = make_daily(at={TARGET_INDEX: {"precip_sum": 0.0, "wind_speed_max": 11.0, "weather_codes": 1}})
    ecmwf = make_daily(
        at={
            TARGET_INDEX: {
                "precip_sum": 12.34,
                "precip_prob_max": 85.0,
                "wind_speed_max": 33.0,
                "wind_dir_dominant": 225.0,
                "weather_codes": 63,
            }
        }
    )
    data = build(make_daily_multi(gfs=gfs, ecmwf=ecmwf), make_hourly())
    assert data.anchor_model == "ecmwf"
    assert data.precip_sum == 12.3
    assert data.precip_prob == 85.0
    assert data.wind_speed_max == 33.0
    assert data.wind_dir_deg == 225.0
    assert data.weather_code == 63
    assert data.icon == "rain"


def test_daily_gust_is_the_ecmwf_one_not_gfs() -> None:
    gfs = make_daily(at={TARGET_INDEX: {"wind_gusts_max": 90.0}})
    ecmwf = make_daily(at={TARGET_INDEX: {"wind_gusts_max": 55.4}})
    data = build(make_daily_multi(gfs=gfs, ecmwf=ecmwf), make_hourly())
    assert data.wind_gust_max == 55.4


def test_without_ecmwf_the_anchor_is_gfs_and_it_is_reported() -> None:
    gfs = make_daily(at={TARGET_INDEX: {"wind_gusts_max": 61.0, "temp_max": 19.4}})
    data = build(make_daily_multi(gfs=gfs), make_hourly())
    assert data.anchor_model == "gfs"
    assert data.wind_gust_max == 61.0
    assert data.temp_max == 19


def test_the_day_is_matched_by_date_not_by_position() -> None:
    # GFS starts one day later than ECMWF: the target is index 1 in GFS and index 2 in ECMWF.
    gfs = make_daily(first_day=date(2026, 10, 6), at={1: {"temp_max": 24.0}})
    ecmwf = make_daily(at={TARGET_INDEX: {"temp_max": 20.0}})
    data = build(make_daily_multi(gfs=gfs, ecmwf=ecmwf), make_hourly())
    assert data.temp_max == 22  # mean of 24 (GFS, by date) and 20 (ECMWF); by position GFS would say 20


def test_a_rain_code_without_rain_shows_a_sky_icon_like_the_web() -> None:
    ecmwf = make_daily(at={TARGET_INDEX: {"weather_codes": 61, "precip_sum": 0.4, "cloud_cover_mean": 10.0}})
    data = build(make_daily_multi(gfs=make_daily(), ecmwf=ecmwf), make_hourly())
    assert data.icon == "clear-day"


def test_convective_risk_comes_from_the_hourly_cape_of_that_day() -> None:
    hourly = make_hourly(cape={(TARGET_INDEX, 15): 3000.0})
    daily, _, _ = make_raw()
    assert build(daily, hourly).convective_risk == "high"
    assert build(daily, make_hourly()).convective_risk == "low"


def test_slots_of_the_day_cover_exactly_24_hours() -> None:
    slots = day_slots(make_hourly(), TARGET)
    assert [(s.start_hour, s.end_hour) for s in slots] == [(h, h + 3) for h in range(0, 24, 3)]


def test_a_slot_ending_at_midnight_comes_from_the_next_days_00_label() -> None:
    hourly = make_hourly(rain={(TARGET_INDEX + 1, 0): 2.5})  # rain of 23:00-24:00 of the target day
    last = day_slots(hourly, TARGET)[-1]
    assert (last.start_hour, last.end_hour) == (21, 24)
    assert last.precip_mm == 2.5


def test_the_00_label_of_the_target_day_belongs_to_the_previous_day() -> None:
    hourly = make_hourly(rain={(TARGET_INDEX, 0): 9.0})  # 23:00-24:00 of the day before
    assert all((s.precip_mm or 0.0) == 0.0 for s in day_slots(hourly, TARGET))


def test_slot_values_come_from_the_three_hours_that_end_at_the_label() -> None:
    hourly = make_hourly(
        rain={(TARGET_INDEX, 7): 1.0, (TARGET_INDEX, 8): 2.0, (TARGET_INDEX, 9): 0.5},
        gust={(TARGET_INDEX, 8): 64.0},
    )
    slot = next(s for s in day_slots(hourly, TARGET) if s.end_hour == 9)
    assert slot.start_hour == 6
    assert slot.precip_mm == 3.5
    assert slot.gust_kmh == 64.0
    assert slot.precip_prob == 20.0


def test_report_data_carries_the_slots_and_the_city() -> None:
    daily, hourly, _ = make_raw()
    data = build(daily, hourly, city=RESISTENCIA)
    assert data.city == RESISTENCIA
    assert data.date == TARGET
    assert len(data.slots) == 8


def test_date_outside_the_forecast_is_an_error() -> None:
    daily, hourly, _ = make_raw()
    with pytest.raises(DatosNoDisponibles, match="2026-11-01"):
        build(daily, hourly, target=date(2026, 11, 1))


def test_report_data_is_immutable_and_serialisable() -> None:
    daily, hourly, _ = make_raw()
    data = build(daily, hourly)
    with pytest.raises(AttributeError):
        data.temp_max = 99  # type: ignore[misc]
    as_dict = data.to_dict()
    assert as_dict["date"] == "2026-10-07"
    assert as_dict["city"]["slug"] == "Cordoba"
    assert isinstance(as_dict["slots"], list) and len(as_dict["slots"]) == 8


def test_temperature_curve_has_one_point_every_3_hours_from_00_to_24() -> None:
    hourly = make_hourly(
        temp={
            (TARGET_INDEX, 0): 11.0,
            (TARGET_INDEX, 6): 9.5,
            (TARGET_INDEX, 15): 24.2,
            (TARGET_INDEX + 1, 0): 13.0,  # midnight at the end of the target day
            (TARGET_INDEX, 1): 99.0,  # not a 3 h mark: never used
        }
    )
    curve = day_temperatures(hourly, TARGET)
    assert [p.hour for p in curve] == list(range(0, 25, 3))
    by_hour = {p.hour: p.temp_c for p in curve}
    assert by_hour[0] == 11.0
    assert by_hour[6] == 9.5
    assert by_hour[15] == 24.2
    assert by_hour[24] == 13.0
    assert by_hour[3] == 15.0


def test_temperature_curve_skips_missing_values_instead_of_inventing_them() -> None:
    hourly = make_hourly(temp={(TARGET_INDEX, 9): None, (TARGET_INDEX, 12): None})
    hours = [p.hour for p in day_temperatures(hourly, TARGET)]
    assert 9 not in hours and 12 not in hours
    assert len(hours) == 7


def test_report_data_carries_the_temperature_curve() -> None:
    daily, _, _ = make_raw()
    data = build(daily, make_hourly(temp={(TARGET_INDEX, 15): 26.0}))
    assert len(data.temp_curve) == 9
    assert max(p.temp_c for p in data.temp_curve) == 26.0
    assert len(data.to_dict()["temp_curve"]) == 9


def test_rain_threshold_matches_the_backend_rule() -> None:
    from app.services.openmeteo import RAIN_VOTE_THRESHOLD_MM

    assert RAIN_THRESHOLD_MM == RAIN_VOTE_THRESHOLD_MM


def test_backend_keys_are_the_expected_ones() -> None:
    from app.services.daily_anchor import ECMWF_KEY, GFS_KEY

    assert (GFS_KEY, ECMWF_KEY) == (GFS, ECMWF)


# ---------------------------------------------------------------------------
# collect_reports with an injected fetcher (no network)
# ---------------------------------------------------------------------------


def run_collect(fetcher, cities=CITIES):
    return asyncio.run(collect_reports(cities, TARGET, fetcher))


def test_collects_every_city() -> None:
    async def fetcher(city: City):
        return make_raw()

    result = run_collect(fetcher)
    assert [r.city for r in result.reports] == list(CITIES)
    assert result.errors == ()


def test_a_failing_city_does_not_stop_the_others() -> None:
    async def fetcher(city: City):
        if city is CABA:
            raise DatosNoDisponibles("CABA sin datos")
        return make_raw()

    result = run_collect(fetcher)
    assert [r.city for r in result.reports] == [CORDOBA, RESISTENCIA]
    assert len(result.errors) == 1
    assert result.errors[0].city == CABA
    assert "CABA sin datos" in result.errors[0].message


def test_unexpected_errors_in_one_city_are_reported_not_hidden() -> None:
    async def fetcher(city: City):
        if city is RESISTENCIA:
            raise RuntimeError("boom")
        return make_raw()

    result = run_collect(fetcher)
    assert len(result.reports) == 2
    assert "boom" in result.errors[0].message
    assert "RuntimeError" in result.errors[0].message


def test_missing_daily_forecast_is_an_error_never_invented_data() -> None:
    async def fetcher(city: City):
        return None, make_hourly(), make_ecmwf_rain()

    result = run_collect(fetcher, cities=(CORDOBA,))
    assert result.reports == ()
    assert "diario" in result.errors[0].message


def test_missing_hourly_forecast_is_an_error_because_alerts_depend_on_it() -> None:
    async def fetcher(city: City):
        daily, _, rain = make_raw()
        return daily, None, rain

    result = run_collect(fetcher, cities=(CORDOBA,))
    assert result.reports == ()
    assert "horario" in result.errors[0].message


def test_the_default_fetcher_is_only_built_when_none_is_injected(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_live(city: City):
        calls.append(city.slug)
        return make_raw()

    class FakeClient:
        async def __aenter__(self) -> None:
            calls.append("open")

        async def __aexit__(self, *exc: object) -> None:
            calls.append("close")

    monkeypatch.setattr(fuente_datos, "fetch_openmeteo", fake_live)
    monkeypatch.setattr(fuente_datos, "shared_client", FakeClient)
    result = asyncio.run(collect_reports((CORDOBA,), TARGET, None))
    assert calls == ["open", "Cordoba", "close"]
    assert len(result.reports) == 1


# ---------------------------------------------------------------------------
# Rain of the 3 h slots: ECMWF hourly, the same model as the daily total
# ---------------------------------------------------------------------------

# The best_match series of Resistencia 7/10: 24.6 mm in 21-24 while the ECMWF day adds up to 1.8 mm.
BEST_MATCH_STORM_AT_NIGHT = make_hourly(
    rain={(TARGET_INDEX, 22): 10.0, (TARGET_INDEX, 23): 10.0, (TARGET_INDEX + 1, 0): 4.6}
)
RESISTENCIA_DAILY = make_daily_multi(
    gfs=make_daily(),
    ecmwf=make_daily(at={TARGET_INDEX: {"precip_sum": 1.8, "precip_prob_max": 70.0, "weather_codes": 61}}),
)
# ECMWF hourly coherent with its 1.8 mm: 0.6 (12-15), 0.9 (15-18), 0.3 (18-21).
COHERENT_ECMWF = make_ecmwf_rain(
    rain={
        **{(TARGET_INDEX, h): 0.2 for h in (13, 14, 15)},
        **{(TARGET_INDEX, h): 0.3 for h in (16, 17, 18)},
        **{(TARGET_INDEX, h): 0.1 for h in (19, 20, 21)},
    }
)


def resistencia(ecmwf_rain, daily=RESISTENCIA_DAILY):
    return build(daily, BEST_MATCH_STORM_AT_NIGHT, city=RESISTENCIA, ecmwf_rain=ecmwf_rain)


def test_slot_rain_comes_from_ecmwf_hourly_not_from_best_match() -> None:
    from reglas import assess, rain_window

    data = resistencia(COHERENT_ECMWF)
    by_start = {s.start_hour: s.precip_mm for s in data.slots}
    assert by_start[21] == 0.0  # best_match said 24.6 mm here
    assert by_start[15] == pytest.approx(0.9)
    assert by_start[12] == pytest.approx(0.6)
    assert rain_window(data.slots) == (12, 18)
    assert assess(data).rain is not None and assess(data).rain.window == "12:00 a 18:00 hs"
    assert data.precip_sum == 1.8
    assert data.avisos == ()


def test_the_other_slot_values_still_come_from_the_hourly_service() -> None:
    hourly = make_hourly(gust={(TARGET_INDEX, 8): 64.0})
    data = build(RESISTENCIA_DAILY, hourly, ecmwf_rain=COHERENT_ECMWF)
    slot = next(s for s in data.slots if s.start_hour == 6)
    assert slot.gust_kmh == 64.0
    assert slot.precip_prob == 20.0


def test_incoherent_ecmwf_hourly_rain_shows_the_bound_and_the_ecmwf_window() -> None:
    from reglas import assess, variante

    # The real Resistencia 7/10: the ECMWF hours add up to 25.2 mm against a 1.8 mm daily total.
    incoherent = make_ecmwf_rain(
        rain={
            **{(TARGET_INDEX, h): 0.25 for h in range(13, 19)},
            (TARGET_INDEX, 22): 7.9,
            (TARGET_INDEX, 23): 7.9,
            (TARGET_INDEX + 1, 0): 7.9,
        }
    )
    data = resistencia(incoherent)
    assert data.precip_sum == 1.8  # the web's daily total is kept as data
    assert data.precip_bound_mm == 25.2  # the figure the report shows ("hasta 25 mm")
    assert {s.start_hour: s.precip_mm for s in data.slots}[21] == pytest.approx(23.7)
    rain = assess(data).rain
    assert rain is not None
    assert (rain.mm, rain.bound, rain.window, rain.heavy) == (25.2, True, "21:00 a 00:00 hs", True)
    assert variante(data) == "Alerta"  # > 15 mm with the shown figure
    assert len(data.avisos) == 1 and "usando la cota horaria" in data.avisos[0]


def test_coherent_data_has_no_bound() -> None:
    assert resistencia(COHERENT_ECMWF).precip_bound_mm is None


def test_without_ecmwf_hourly_rain_there_is_no_window_and_never_best_match() -> None:
    from reglas import assess

    data = resistencia(None)
    assert all(s.precip_mm is None for s in data.slots)  # best_match's 24.6 mm is not used
    assert data.precip_bound_mm is None
    assert assess(data).rain is not None and assess(data).rain.window is None
    assert data.precip_sum == 1.8 and data.precip_prob == 70.0  # total and probability stay
    assert len(data.avisos) == 1 and "Resistencia" in data.avisos[0]


def test_with_a_gfs_anchor_the_ecmwf_slots_are_not_mixed_in() -> None:
    gfs_only = make_daily_multi(gfs=make_daily(at={TARGET_INDEX: {"precip_sum": 1.8}}))
    data = resistencia(COHERENT_ECMWF, daily=gfs_only)
    assert data.anchor_model == "gfs"
    assert all(s.precip_mm is None for s in data.slots)
    assert len(data.avisos) == 1


def test_avisos_are_serialised() -> None:
    assert resistencia(None).to_dict()["avisos"] == list(resistencia(None).avisos)


def test_the_fetcher_third_value_reaches_the_report() -> None:
    async def fetcher(city: City):
        return RESISTENCIA_DAILY, BEST_MATCH_STORM_AT_NIGHT, COHERENT_ECMWF

    result = run_collect(fetcher, cities=(RESISTENCIA,))
    assert {s.start_hour: s.precip_mm for s in result.reports[0].slots}[21] == 0.0


def test_the_live_fetch_makes_one_extra_ecmwf_call_per_city(monkeypatch: pytest.MonkeyPatch) -> None:
    """Daily and hourly services are faked; the ECMWF hourly request goes through respx (no network)."""
    from urllib.parse import parse_qs

    import httpx
    import respx

    from fuente_horaria_ecmwf import ECMWF_HOURLY_MODEL

    async def fake_daily(lat: float, lon: float, days: int = 7):
        return make_raw()[0]

    async def fake_hourly(lat: float, lon: float, days: int = 2):
        return make_hourly()

    monkeypatch.setattr(fuente_datos, "get_multi_model_daily", fake_daily)
    monkeypatch.setattr(fuente_datos, "get_hourly_forecast_ext", fake_hourly)
    rain = make_ecmwf_rain()
    answer = {"hourly": {"time": list(rain.times), "precipitation": list(rain.precip_mm)}}
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=answer)
        )
        result = asyncio.run(collect_reports(CITIES, TARGET, None))
    assert route.call_count == len(CITIES) == 3
    queries = [parse_qs(str(call.request.url.query, "ascii")) for call in route.calls]
    assert sorted(float(q["latitude"][0]) for q in queries) == sorted(c.lat for c in CITIES)
    assert all(q["models"] == [ECMWF_HOURLY_MODEL] for q in queries)
    assert len(result.reports) == 3
    assert all(r.avisos == () for r in result.reports)


def test_a_failed_ecmwf_hourly_fetch_does_not_stop_the_report(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import respx

    async def fake_daily(lat: float, lon: float, days: int = 7):
        return RESISTENCIA_DAILY

    async def fake_hourly(lat: float, lon: float, days: int = 2):
        return BEST_MATCH_STORM_AT_NIGHT

    monkeypatch.setattr(fuente_datos, "get_multi_model_daily", fake_daily)
    monkeypatch.setattr(fuente_datos, "get_hourly_forecast_ext", fake_hourly)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(503))
        result = asyncio.run(collect_reports((RESISTENCIA,), TARGET, None))
    assert route.call_count == 1
    assert result.errors == ()
    report = result.reports[0]
    assert all(s.precip_mm is None for s in report.slots)
    assert len(report.avisos) == 1
