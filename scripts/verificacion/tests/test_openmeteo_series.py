"""Tests for response validation, chunking and chunk merging."""

from __future__ import annotations

import copy
import datetime as dt
import math
from pathlib import Path

import pytest

from fakeworld import FakeOpenMeteo, build_payload, forecast_value
from openmeteo_client import MODEL_IDS, ClientConfig, OpenMeteoClient, OpenMeteoError
from openmeteo_series import (
    ResponseError,
    fetch_station_series,
    parse_chunk,
    request_urls,
    split_range,
)
from stations import STATIONS_BY_NAME

D = dt.date
BOTH = tuple(MODEL_IDS.values())
EZEIZA = STATIONS_BY_NAME["EZEIZA AERO"]


def payload(start: dt.date = D(2026, 1, 1), end: dt.date = D(2026, 1, 2)) -> dict:
    return build_payload(EZEIZA.lat, start, end, BOTH)


# --- split_range ----------------------------------------------------------------------------


def test_split_range_chunks_are_contiguous_and_cover_everything() -> None:
    chunks = split_range(D(2025, 10, 4), D(2026, 10, 4), 92)

    assert chunks[0][0] == D(2025, 10, 4) and chunks[-1][1] == D(2026, 10, 4)
    assert [(b - a).days + 1 for a, b in chunks] == [92, 92, 92, 90]
    for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:], strict=False):
        assert next_start == prev_end + dt.timedelta(days=1)
    assert sum((b - a).days + 1 for a, b in chunks) == 366
    assert all((b - a).days + 1 <= 92 for a, b in chunks)
    assert len(chunks) == 4


def test_split_range_single_day() -> None:
    assert split_range(D(2026, 1, 1), D(2026, 1, 1), 30) == ((D(2026, 1, 1), D(2026, 1, 1)),)


@pytest.mark.parametrize("chunk_days", [0, -5])
def test_split_range_rejects_bad_chunk(chunk_days: int) -> None:
    with pytest.raises(ValueError, match="chunk_days"):
        split_range(D(2026, 1, 1), D(2026, 1, 5), chunk_days)


def test_split_range_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="start"):
        split_range(D(2026, 1, 5), D(2026, 1, 1), 10)


# --- parse_chunk ----------------------------------------------------------------------------


def test_parse_chunk_multi_model_columns_have_model_suffix() -> None:
    parsed = parse_chunk(payload(), MODEL_IDS, D(2026, 1, 1), D(2026, 1, 2))

    assert set(parsed) == {(m, lead) for m in ("ecmwf", "gfs") for lead in range(8)}
    series = parsed[("gfs", 3)]
    assert len(series) == 48
    assert series[0][0] == dt.datetime(2026, 1, 1, 0, tzinfo=dt.UTC)
    assert series[-1][0] == dt.datetime(2026, 1, 2, 23, tzinfo=dt.UTC)
    assert series[5][1] == pytest.approx(
        forecast_value("gfs", 3, EZEIZA.lat, dt.datetime(2026, 1, 1, 5, tzinfo=dt.UTC))
    )


def test_parse_chunk_single_model_columns_have_no_suffix() -> None:
    one = build_payload(EZEIZA.lat, D(2026, 1, 1), D(2026, 1, 1), ("ecmwf_ifs025",))

    parsed = parse_chunk(one, {"ecmwf": "ecmwf_ifs025"}, D(2026, 1, 1), D(2026, 1, 1))

    assert set(parsed) == {("ecmwf", lead) for lead in range(8)}
    assert "temperature_2m_previous_day1" in one["hourly"]


def test_parse_chunk_keeps_null_values() -> None:
    data = payload()
    data["hourly"]["temperature_2m_gfs_global"][4] = None

    parsed = parse_chunk(data, MODEL_IDS, D(2026, 1, 1), D(2026, 1, 2))

    assert parsed[("gfs", 0)][4][1] is None


def test_parse_chunk_api_error_payload() -> None:
    with pytest.raises(ResponseError, match="Hourly API request limit"):
        parse_chunk(
            {"error": True, "reason": "Hourly API request limit exceeded"},
            MODEL_IDS,
            D(2026, 1, 1),
            D(2026, 1, 2),
        )


def test_parse_chunk_is_an_open_meteo_error() -> None:
    assert issubclass(ResponseError, OpenMeteoError)


def mutate(change) -> dict:
    data = copy.deepcopy(payload())
    change(data)
    return data


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.pop("hourly"), "hourly"),
        (lambda d: d["hourly"].pop("time"), "time"),
        (lambda d: d["hourly"].pop("temperature_2m_previous_day4_gfs_global"), "previous_day4"),
        (lambda d: d["hourly"].__setitem__("temperature_2m_ecmwf_ifs025", [1.0] * 10), "length"),
        (lambda d: d["hourly"]["temperature_2m_gfs_global"].__setitem__(3, "warm"), "numeric"),
        (lambda d: d["hourly"]["temperature_2m_gfs_global"].__setitem__(3, math.nan), "numeric"),
        (lambda d: d["hourly"]["time"].__setitem__(0, "01/01/2026"), "time"),
        (lambda d: d.__setitem__("utc_offset_seconds", 3600), "UTC"),
    ],
)
def test_parse_chunk_rejects_malformed_payloads(change, message: str) -> None:
    with pytest.raises(ResponseError, match=message):
        parse_chunk(mutate(change), MODEL_IDS, D(2026, 1, 1), D(2026, 1, 2))


def test_parse_chunk_rejects_wrong_period() -> None:
    with pytest.raises(ResponseError, match="period"):
        parse_chunk(payload(), MODEL_IDS, D(2026, 1, 2), D(2026, 1, 3))


def test_parse_chunk_rejects_gaps_in_time() -> None:
    def drop_hour(d: dict) -> None:
        for values in d["hourly"].values():
            del values[10]
        d["hourly"]["time"].append("2026-01-03T00:00")  # keep length, break continuity
        for name, values in d["hourly"].items():
            if name != "time":
                values.append(1.0)

    with pytest.raises(ResponseError, match="hourly"):
        parse_chunk(mutate(drop_hour), MODEL_IDS, D(2026, 1, 1), D(2026, 1, 2))


# --- fetch_station_series ------------------------------------------------------------------


def make_client(tmp_path: Path, http: FakeOpenMeteo) -> OpenMeteoClient:
    config = ClientConfig(cache_dir=tmp_path, max_calls=50, pause_seconds=0.0)
    return OpenMeteoClient(config, http_get=http, sleep=lambda _s: None)


def test_request_urls_one_per_chunk() -> None:
    urls = request_urls(EZEIZA, D(2026, 1, 1), D(2026, 3, 31), 30)

    assert len(urls) == 3
    assert len(set(urls)) == 3
    assert "start_date=2026-01-01" in urls[0] and "end_date=2026-03-31" in urls[-1]


def test_fetch_station_series_merges_chunks_into_one_continuous_series(tmp_path: Path) -> None:
    http = FakeOpenMeteo()
    client = make_client(tmp_path, http)

    series = fetch_station_series(client, EZEIZA, D(2026, 1, 1), D(2026, 3, 31), 30)

    assert len(http.urls) == 3
    ecmwf_day2 = series[("ecmwf", 2)]
    assert len(ecmwf_day2) == 90 * 24
    stamps = [t for t, _ in ecmwf_day2]
    assert stamps == sorted(set(stamps))
    assert stamps[-1] - stamps[0] == dt.timedelta(hours=90 * 24 - 1)


def test_fetch_station_series_evicts_cache_of_an_invalid_response(tmp_path: Path) -> None:
    class Broken(FakeOpenMeteo):
        def __call__(self, url, headers, timeout):  # type: ignore[no-untyped-def]
            response = super().__call__(url, headers, timeout)
            body = response.body.replace('"temperature_2m_gfs_global"', '"renamed"')
            return type(response)(200, body, {})

    client = make_client(tmp_path, Broken())

    with pytest.raises(ResponseError):
        fetch_station_series(client, EZEIZA, D(2026, 1, 1), D(2026, 1, 5), 30)

    (url,) = request_urls(EZEIZA, D(2026, 1, 1), D(2026, 1, 5), 30)
    assert not client.is_cached(url)
