"""Tests for the ECMWF overlay on the dashboard hourly series (FRA-363).

Source policy: the Previsión dashboard takes rain, wind (speed, gusts, direction), weather code and
CAPE from ECMWF (`ecmwf_ifs025`) and everything else from `best_match`. The tools keep using the
unmerged `get_hourly_forecast_ext`.

Covers:
- `merge_hourly_ecmwf` (pure): per-field, per-index, per-timestamp rules and immutability.
- `get_hourly_forecast_ecmwf`: request shape, parsing, failure -> None, separate cache key.
- Dashboard router: merged values reach the strip, the rain headline and the convective risk; any
  ECMWF failure leaves the dashboard exactly as before; the tools endpoints stay unmerged.
"""
from __future__ import annotations

import copy
import dataclasses
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from httpx import AsyncClient

from app.services.calculators import compute_convective_risk
from app.services.hourly_slots import three_hour_slots
from app.services.openmeteo import (
    HourlyForecastExt,
    get_hourly_forecast_ecmwf,
    get_hourly_forecast_ext,
    merge_hourly_ecmwf,
)
from tests.hourly_fixtures import AR, make_hourly, make_uniform_hourly
from tests.test_dashboard import _make_current_response, _make_multi_model

OM_URL = "https://api.open-meteo.com/v1/forecast"
LAT, LON = -31.4135, -64.181   # Córdoba


def _all_hours(hours: int, value) -> dict[int, object]:
    """Override dict that sets `value` on every hour index (for `make_hourly`)."""
    return {i: value for i in range(hours)}


# ---------------------------------------------------------------------------
# merge_hourly_ecmwf (pure)
# ---------------------------------------------------------------------------

class TestMergeHourlyEcmwf:

    def test_replaces_the_six_ecmwf_fields_and_keeps_the_rest(self):
        base = make_hourly(6)
        ecmwf = make_hourly(
            6,
            precipitations=_all_hours(6, 2.5),
            wind_gusts_kmh=_all_hours(6, 55.0),
            wind_speeds=_all_hours(6, 33.0),
            wind_dirs_deg=_all_hours(6, 90.0),
            weather_codes=_all_hours(6, 95),
            cape_j_kg=_all_hours(6, 2600.0),
            # Fields that must NOT come from ECMWF even if the series carries them.
            temps_c=_all_hours(6, 99.0),
            precip_probs=_all_hours(6, 77.0),
            humidities=_all_hours(6, 11.0),
            cloud_covers=_all_hours(6, 22.0),
            temps_850_c=_all_hours(6, -9.0),
            freezing_level_heights_m=_all_hours(6, 1.0),
        )

        merged = merge_hourly_ecmwf(base, ecmwf)

        assert merged.precipitations == [2.5] * 6
        assert merged.wind_gusts_kmh == [55.0] * 6
        assert merged.wind_speeds == [33.0] * 6
        assert merged.wind_dirs_deg == [90.0] * 6
        assert merged.weather_codes == [95] * 6
        assert merged.cape_j_kg == [2600.0] * 6
        # Everything else is the base series.
        assert merged.temps_c == base.temps_c
        assert merged.precip_probs == base.precip_probs
        assert merged.humidities == base.humidities
        assert merged.cloud_covers == base.cloud_covers
        assert merged.temps_850_c == base.temps_850_c
        assert merged.freezing_level_heights_m == base.freezing_level_heights_m
        assert merged.is_day == base.is_day
        assert merged.timestamps == base.timestamps
        assert merged.hour_labels == base.hour_labels
        assert merged.dates == base.dates
        assert merged.elevation_m == base.elevation_m

    def test_a_null_ecmwf_value_keeps_the_best_match_value_at_that_index_only(self):
        base = make_hourly(4, precipitations={0: 0.1, 1: 0.2, 2: 0.3, 3: 0.4})
        ecmwf = make_hourly(4, precipitations={0: 5.0, 1: None, 2: 7.0, 3: None})

        merged = merge_hourly_ecmwf(base, ecmwf)

        assert merged.precipitations == [5.0, 0.2, 7.0, 0.4]

    def test_null_handling_is_independent_per_field(self):
        base = make_hourly(3, wind_gusts_kmh=_all_hours(3, 25.0), cape_j_kg=_all_hours(3, 100.0))
        ecmwf = make_hourly(
            3,
            precipitations=_all_hours(3, 3.0),
            wind_gusts_kmh={0: 40.0, 1: None, 2: 60.0},
            cape_j_kg={0: None, 1: 900.0, 2: None},
            weather_codes={0: 61, 1: 61, 2: None},
        )

        merged = merge_hourly_ecmwf(base, ecmwf)

        assert merged.precipitations == [3.0, 3.0, 3.0]
        assert merged.wind_gusts_kmh == [40.0, 25.0, 60.0]
        assert merged.cape_j_kg == [100.0, 900.0, 100.0]
        assert merged.weather_codes == [61, 61, 0]

    def test_a_shorter_ecmwf_series_replaces_only_the_common_instants(self):
        base = make_hourly(8)
        ecmwf = make_hourly(3, precipitations=_all_hours(3, 4.0))

        merged = merge_hourly_ecmwf(base, ecmwf)

        assert merged.precipitations == [4.0, 4.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        assert len(merged.timestamps) == 8

    def test_series_are_matched_by_timestamp_not_by_position(self):
        # ECMWF starts 3 hours later than base: its index 0 is base index 3.
        base = make_hourly(6)
        later = make_hourly(
            6,
            start=datetime(2026, 9, 19, 3, 0, tzinfo=AR),
            precipitations={0: 1.0, 1: 2.0, 2: 3.0, 3: 4.0, 4: 5.0, 5: 6.0},
        )

        merged = merge_hourly_ecmwf(base, later)

        # base instants 0..2 have no ECMWF value -> best_match; 3..5 take ECMWF index 0..2.
        assert merged.precipitations == [0.0, 0.0, 0.0, 1.0, 2.0, 3.0]

    def test_ecmwf_with_no_common_instant_leaves_the_base_content_unchanged(self):
        base = make_hourly(4)
        far = make_hourly(4, start=datetime(2026, 10, 1, 0, 0, tzinfo=AR),
                          precipitations=_all_hours(4, 9.0))

        merged = merge_hourly_ecmwf(base, far)

        assert merged == base

    def test_an_empty_base_series_for_an_ecmwf_field_is_filled_only_at_common_instants(self):
        base = dataclasses.replace(make_hourly(4), wind_gusts_kmh=[])
        ecmwf = make_hourly(2, wind_gusts_kmh={0: 40.0, 1: 50.0})

        merged = merge_hourly_ecmwf(base, ecmwf)

        assert merged.wind_gusts_kmh == [40.0, 50.0, None, None]

    def test_an_empty_ecmwf_field_leaves_the_base_field_untouched(self):
        base = make_hourly(3, wind_gusts_kmh={0: 21.0})
        ecmwf = dataclasses.replace(make_hourly(3), wind_gusts_kmh=[])

        merged = merge_hourly_ecmwf(base, ecmwf)

        assert merged.wind_gusts_kmh == base.wind_gusts_kmh

    def test_does_not_mutate_its_inputs(self):
        base = make_hourly(5)
        ecmwf = make_hourly(5, precipitations=_all_hours(5, 8.0), cape_j_kg={2: None})
        base_before = copy.deepcopy(base)
        ecmwf_before = copy.deepcopy(ecmwf)

        merged = merge_hourly_ecmwf(base, ecmwf)

        assert base == base_before
        assert ecmwf == ecmwf_before
        assert merged is not base
        # The result owns its lists: editing it cannot leak into the inputs.
        merged.precipitations.append(1.0)
        merged.temps_c.append(1.0)
        assert base == base_before

    def test_without_ecmwf_the_base_series_is_returned_as_is(self):
        base = make_hourly(3)

        assert merge_hourly_ecmwf(base, None) == base

    def test_the_merged_series_keeps_working_with_the_slot_builder(self):
        base = make_hourly(24, precipitations={9: 0.5})
        ecmwf = make_hourly(24, precipitations={9: 0.7})

        merged = merge_hourly_ecmwf(base, ecmwf)

        slot_9h = next(s for s in three_hour_slots(merged) if s.hour_label == "09:00")
        assert slot_9h.precip_mm == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# get_hourly_forecast_ecmwf
# ---------------------------------------------------------------------------

def _ecmwf_payload(n: int = 3, start_hour: int = 9) -> dict:
    return {
        "elevation": 430.0,
        "hourly": {
            "time": [f"2026-10-07T{start_hour + i:02d}:00" for i in range(n)],
            "precipitation": [0.7, 3.7, 5.9][:n],
            "wind_gusts_10m": [50.0, 54.0, None][:n],
            "wind_speed_10m": [30.0, 32.5, 28.0][:n],
            "wind_direction_10m": [350, 10, 20][:n],
            "weather_code": [61, 95, 80][:n],
            "cape": [900, 2600.5, 1200][:n],
        },
    }


class TestGetHourlyForecastEcmwf:

    @pytest.mark.asyncio
    async def test_asks_ecmwf_for_the_six_fields_in_kmh_and_argentine_time(self):
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json=_ecmwf_payload())

        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(side_effect=handler)
            await get_hourly_forecast_ecmwf(LAT, LON, days=7)

        (request,) = requests
        params = request.url.params
        assert params["models"] == "ecmwf_ifs025"
        assert params["forecast_days"] == "7"
        assert params["timezone"] == "America/Argentina/Buenos_Aires"
        assert params["wind_speed_unit"] == "kmh"
        assert set(params["hourly"].split(",")) == {
            "precipitation", "wind_gusts_10m", "wind_speed_10m",
            "wind_direction_10m", "weather_code", "cape",
        }

    @pytest.mark.asyncio
    async def test_parses_into_the_hourly_shape_with_real_instants(self):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_ecmwf_payload()))
            result = await get_hourly_forecast_ecmwf(LAT, LON, days=7)

        assert isinstance(result, HourlyForecastExt)
        first = int(datetime(2026, 10, 7, 9, 0, tzinfo=AR).timestamp())
        assert result.timestamps == [first, first + 3600, first + 7200]
        assert result.hour_labels == ["09:00", "10:00", "11:00"]
        assert result.dates == ["2026-10-07"] * 3
        assert result.precipitations == [0.7, 3.7, 5.9]
        assert result.wind_gusts_kmh == [50.0, 54.0, None]
        assert result.wind_speeds == [30.0, 32.5, 28.0]
        assert result.wind_dirs_deg == [350.0, 10.0, 20.0]
        assert result.weather_codes == [61, 95, 80]
        assert result.cape_j_kg == [900.0, 2600.5, 1200.0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(500, json={"error": True}),
            httpx.Response(429, json={"error": True}),
            httpx.Response(200, content=b"<html>not json</html>"),
            httpx.Response(200, json={"unexpected": 1}),
            httpx.Response(200, json={"hourly": None}),
        ],
        ids=["500", "429", "malformed-json", "no-hourly", "null-hourly"],
    )
    async def test_returns_none_on_http_error_or_bad_payload(self, response):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=response)
            result = await get_hourly_forecast_ecmwf(LAT, LON, days=7)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(side_effect=httpx.ReadTimeout("slow"))
            result = await get_hourly_forecast_ecmwf(LAT, LON, days=7)

        assert result is None

    @pytest.mark.asyncio
    async def test_caches_by_model_and_does_not_share_the_best_match_key(self):
        """One request each, however many times either is asked: different keys, no cross-talk."""
        best_match_payload = {
            "hourly": {
                "time": ["2026-10-07T09:00"],
                "temperature_2m": [20.0],
                "precipitation": [0.1],
                "is_day": [1],
            }
        }

        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.params.get("models") == "ecmwf_ifs025":
                return httpx.Response(200, json=_ecmwf_payload())
            return httpx.Response(200, json=best_match_payload)

        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(side_effect=handler)
            ecmwf_1 = await get_hourly_forecast_ecmwf(LAT, LON, days=7)
            best_1 = await get_hourly_forecast_ext(LAT, LON, days=7)
            ecmwf_2 = await get_hourly_forecast_ecmwf(LAT, LON, days=7)
            best_2 = await get_hourly_forecast_ext(LAT, LON, days=7)

        assert len(requests) == 2
        assert sum(1 for r in requests if r.url.params.get("models") == "ecmwf_ifs025") == 1
        assert sum(1 for r in requests if "models" not in r.url.params) == 1
        assert ecmwf_1 is ecmwf_2
        assert best_1 is best_2
        assert ecmwf_1.precipitations == [0.7, 3.7, 5.9]
        assert best_1.precipitations == [0.1]

    @pytest.mark.asyncio
    async def test_best_match_request_is_unchanged(self):
        """The tools' request keeps asking for the blend, with no `models` parameter."""
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"hourly": {"time": ["2026-10-07T09:00"], "is_day": [1]}})

        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(side_effect=handler)
            await get_hourly_forecast_ext(LAT, LON, days=7)

        (request,) = requests
        assert "models" not in request.url.params
        assert "wind_direction_10m" in request.url.params["hourly"].split(",")


# ---------------------------------------------------------------------------
# Córdoba 2026-10-07: slot sums follow ECMWF, not the blend
# ---------------------------------------------------------------------------

# Hourly ECMWF rain of the day. 3-hour blocks (the hours that END at 06/09/12/15/18 h):
#   06h 0.2 | 09h 0.7 | 12h 3.7 | 15h 5.9 | 18h 2.1  -> day total 12.6 mm
_CORDOBA_ECMWF_RAIN = {
    5: 0.2,
    7: 0.3, 8: 0.2, 9: 0.2,
    10: 1.0, 11: 1.2, 12: 1.5,
    13: 2.0, 14: 2.1, 15: 1.8,
    16: 1.0, 17: 0.6, 18: 0.5,
}
# best_match blend for the same day: 7.2 mm.
_CORDOBA_BLEND_RAIN = {9: 0.5, 12: 2.0, 14: 3.0, 17: 1.7}


def _cordoba_payload() -> dict:
    n = 48
    times = [f"2026-10-{7 + i // 24:02d}T{i % 24:02d}:00" for i in range(n)]
    return {
        "hourly": {
            "time": times,
            "precipitation": [_CORDOBA_ECMWF_RAIN.get(i, 0.0) for i in range(n)],
            "wind_gusts_10m": [52.0 if 12 <= i <= 15 else 20.0 for i in range(n)],
            "wind_speed_10m": [25.0] * n,
            "wind_direction_10m": [180] * n,
            "weather_code": [95 if 12 <= i <= 15 else 3 for i in range(n)],
            "cape": [2700.0 if 12 <= i <= 15 else 100.0 for i in range(n)],
        }
    }


class TestCordobaSlotSums:

    @pytest.mark.asyncio
    async def test_three_hour_slots_of_the_day_add_up_to_the_ecmwf_total(self):
        day0 = datetime(2026, 10, 7, 0, 0, tzinfo=AR)
        base = make_hourly(
            48, start=day0,
            precipitations=dict(_CORDOBA_BLEND_RAIN),
            wind_gusts_kmh=_all_hours(48, 25.0),
        )
        with respx.mock(assert_all_called=False) as mock:
            mock.get(OM_URL).mock(return_value=httpx.Response(200, json=_cordoba_payload()))
            ecmwf = await get_hourly_forecast_ecmwf(LAT, LON, days=2)

        merged = merge_hourly_ecmwf(base, ecmwf)

        def day_slots(series: HourlyForecastExt):
            return {s.hour_label: s for s in three_hour_slots(series) if s.date == "2026-10-07"}

        merged_slots = day_slots(merged)
        assert merged_slots["09:00"].precip_mm == pytest.approx(0.7)
        assert merged_slots["12:00"].precip_mm == pytest.approx(3.7)
        assert merged_slots["15:00"].precip_mm == pytest.approx(5.9)
        assert merged_slots["18:00"].precip_mm == pytest.approx(2.1)
        assert sum(s.precip_mm or 0.0 for s in merged_slots.values()) == pytest.approx(12.6, abs=0.01)

        # The blend alone (what the dashboard used to show) adds up to 7.2 mm: the inconsistency.
        base_total = sum(s.precip_mm or 0.0 for s in day_slots(base).values())
        assert base_total == pytest.approx(7.2, abs=0.01)

        assert merged_slots["15:00"].wind_gust_kmh == 52.0
        assert day_slots(base)["15:00"].wind_gust_kmh == 25.0
        assert merged_slots["15:00"].weather_code == 95


# ---------------------------------------------------------------------------
# Dashboard router
# ---------------------------------------------------------------------------

ECMWF_FN = "app.routers.weather.get_hourly_forecast_ecmwf"
HOURLY_FN = "app.routers.weather.get_hourly_forecast_ext"
DASHBOARD_URL = "/api/weather/dashboard?lat=-31.4&lon=-64.2"


def _today_midnight() -> datetime:
    return datetime.now(AR).replace(hour=0, minute=0, second=0, microsecond=0)


def _base_hourly() -> HourlyForecastExt:
    """best_match-like: dry, calm, quiet CAPE, 40 % probability, 20 °C."""
    return make_hourly(48, start=_today_midnight(), precip_probs=_all_hours(48, 40.0))


def _ecmwf_hourly() -> HourlyForecastExt:
    """ECMWF-like: raining, gusty, unstable. Its temperature/probability are garbage on purpose."""
    return make_hourly(
        48,
        start=_today_midnight(),
        precipitations=_all_hours(48, 2.0),
        wind_gusts_kmh=_all_hours(48, 60.0),
        wind_speeds=_all_hours(48, 40.0),
        weather_codes=_all_hours(48, 95),
        cape_j_kg=_all_hours(48, 2600.0),
        temps_c=_all_hours(48, 99.0),
        precip_probs=_all_hours(48, 0.0),
    )


async def _get_dashboard(client: AsyncClient, *, base, ecmwf):
    daily = _make_multi_model(start=datetime.now(AR).date())   # dates must match the hourly series
    with (
        patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
        patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock, return_value=daily),
        patch(HOURLY_FN, new_callable=AsyncMock, return_value=base),
        patch(ECMWF_FN, new_callable=AsyncMock, **ecmwf),
    ):
        return await client.get(DASHBOARD_URL)


def _stable_view(body: dict) -> dict:
    """The parts of the response that depend on the hourly series."""
    return {k: body[k] for k in ("hourly", "rain_today", "forecast_7d", "snow_level_m")}


@pytest.mark.integration
class TestDashboardUsesTheMergedSeries:

    @pytest.mark.asyncio
    async def test_strip_rain_gusts_code_and_convective_risk_come_from_ecmwf(self, async_client: AsyncClient):
        response = await _get_dashboard(
            async_client, base=_base_hourly(), ecmwf={"return_value": _ecmwf_hourly()}
        )

        assert response.status_code == 200
        entries = response.json()["hourly"]["entries"]
        slot = next(e for e in entries if e["hour_label"] == "12:00")
        assert slot["precip_mm"] == pytest.approx(6.0)               # 3 h x 2.0 mm
        assert slot["wind_gusts_kmh"] == 60.0
        assert slot["weather_code"] == 95
        assert slot["convective_risk"] == compute_convective_risk(2600.0)
        assert slot["convective_risk"] != compute_convective_risk(0.0)
        # Not from ECMWF: temperature and precipitation probability stay on best_match.
        assert slot["temp_c"] == 20.0
        assert slot["precip_prob"] == 40.0

    @pytest.mark.asyncio
    async def test_rain_headline_and_daily_convective_risk_follow_ecmwf(self, async_client: AsyncClient):
        response = await _get_dashboard(
            async_client, base=_base_hourly(), ecmwf={"return_value": _ecmwf_hourly()}
        )

        body = response.json()
        assert body["rain_today"]["has_rain_today"] is True
        assert body["forecast_7d"][0]["convective_risk"] == compute_convective_risk(2600.0)

    @pytest.mark.asyncio
    async def test_response_schema_has_no_new_field_and_names_no_model(self, async_client: AsyncClient):
        merged = await _get_dashboard(
            async_client, base=_base_hourly(), ecmwf={"return_value": _ecmwf_hourly()}
        )
        plain = await _get_dashboard(async_client, base=_base_hourly(), ecmwf={"return_value": None})

        assert set(merged.json()) == set(plain.json())
        entry_merged = merged.json()["hourly"]["entries"][0]
        entry_plain = plain.json()["hourly"]["entries"][0]
        assert set(entry_merged) == set(entry_plain)
        assert "ecmwf_ifs025" not in merged.text


@pytest.mark.integration
class TestDashboardFallsBackToBestMatch:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "ecmwf",
        [
            {"return_value": None},
            {"side_effect": RuntimeError("boom")},
        ],
        ids=["none", "exception"],
    )
    async def test_ecmwf_failure_leaves_the_dashboard_as_it_was(self, async_client: AsyncClient, ecmwf):
        baseline = await _get_dashboard(async_client, base=_base_hourly(), ecmwf={"return_value": None})
        failed = await _get_dashboard(async_client, base=_base_hourly(), ecmwf=ecmwf)

        assert failed.status_code == 200
        assert _stable_view(failed.json()) == _stable_view(baseline.json())
        # best_match values are what the strip shows (dry, gust 10, CAPE 0)
        slot = next(e for e in failed.json()["hourly"]["entries"] if e["hour_label"] == "12:00")
        assert slot["precip_mm"] == 0.0
        assert slot["wind_gusts_kmh"] == 10.0

    @pytest.mark.asyncio
    async def test_the_pure_merge_failing_also_falls_back(self, async_client: AsyncClient):
        baseline = await _get_dashboard(async_client, base=_base_hourly(), ecmwf={"return_value": None})
        with patch("app.routers.weather.merge_hourly_ecmwf", side_effect=ValueError("bad series")):
            failed = await _get_dashboard(
                async_client, base=_base_hourly(), ecmwf={"return_value": _ecmwf_hourly()}
            )

        assert failed.status_code == 200
        assert _stable_view(failed.json()) == _stable_view(baseline.json())

    @pytest.mark.asyncio
    async def test_without_best_match_there_is_no_hourly_series_even_if_ecmwf_answers(
        self, async_client: AsyncClient
    ):
        response = await _get_dashboard(async_client, base=None, ecmwf={"return_value": _ecmwf_hourly()})

        assert response.status_code == 200
        assert response.json()["hourly"]["entries"] == []

    @pytest.mark.asyncio
    async def test_the_fallback_is_logged_and_counted(self, async_client: AsyncClient, caplog):
        with (
            caplog.at_level("INFO", logger="app.routers.weather"),
            patch("app.routers.weather.usage_counter.record") as record,
        ):
            await _get_dashboard(async_client, base=_base_hourly(), ecmwf={"return_value": None})

        assert any("hourly_ecmwf_fallback" in r.getMessage() for r in caplog.records)
        record.assert_called_once()
        assert record.call_args.args[0] == "open_meteo_hourly_ecmwf_fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_is_logged_or_counted_when_ecmwf_is_present(self, async_client: AsyncClient, caplog):
        with (
            caplog.at_level("INFO", logger="app.routers.weather"),
            patch("app.routers.weather.usage_counter.record") as record,
        ):
            await _get_dashboard(async_client, base=_base_hourly(), ecmwf={"return_value": _ecmwf_hourly()})

        assert not any("hourly_ecmwf_fallback" in r.getMessage() for r in caplog.records)
        record.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.live_hourly_ecmwf
    async def test_a_real_ecmwf_http_failure_is_absorbed(self, async_client: AsyncClient):
        """Same path with the real fetch: Open-Meteo answers 500 to the ECMWF request only."""
        baseline = await _get_dashboard(async_client, base=_base_hourly(), ecmwf={"return_value": None})
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(500, json={"error": True})

        with (
            respx.mock(assert_all_called=False) as mock,
            patch("app.routers.weather.aggregate_current", new_callable=AsyncMock, return_value=_make_current_response()),
            patch("app.routers.weather.get_multi_model_daily", new_callable=AsyncMock,
                  return_value=_make_multi_model(start=datetime.now(AR).date())),
            patch(HOURLY_FN, new_callable=AsyncMock, return_value=_base_hourly()),
        ):
            mock.get(OM_URL).mock(side_effect=handler)
            failed = await async_client.get(DASHBOARD_URL)

        assert requests, "the dashboard must have asked Open-Meteo for the ECMWF series"
        assert all(r.url.params.get("models") == "ecmwf_ifs025" for r in requests)
        assert failed.status_code == 200
        assert _stable_view(failed.json()) == _stable_view(baseline.json())


# ---------------------------------------------------------------------------
# Tools stay on the unmerged series
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestToolsAreNotAffected:

    @pytest.mark.asyncio
    async def test_tools_never_ask_for_the_ecmwf_series(self, async_client: AsyncClient):
        ecmwf_spy = AsyncMock(return_value=_ecmwf_hourly())
        with (
            patch("app.routers.tools.get_hourly_forecast_ext", new_callable=AsyncMock,
                  return_value=make_uniform_hourly(temp_c=25.0, humidity=50.0, wind=15.0, wind_dir=180.0, precip=0.0)),
            patch("app.services.openmeteo.get_hourly_forecast_ecmwf", ecmwf_spy),
            patch(ECMWF_FN, ecmwf_spy),
        ):
            response = await async_client.get("/api/tools/tender-ropa/forecast?lat=-34.6&lon=-58.4")

        assert response.status_code == 200
        ecmwf_spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_tools_series_is_not_modified_by_a_dashboard_call(self, async_client: AsyncClient):
        """The dashboard overlays on a copy: the cached best_match object the tools share is intact."""
        base = _base_hourly()
        before = copy.deepcopy(base)

        await _get_dashboard(async_client, base=base, ecmwf={"return_value": _ecmwf_hourly()})

        assert base == before
