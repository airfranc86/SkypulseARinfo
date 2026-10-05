"""Validate Open-Meteo hourly responses and merge date chunks into continuous series.

A series is keyed by ``(model_key, lead)`` with ``model_key`` in {"ecmwf", "gfs"} and
``lead`` 0 (current run) to 7 (``previous_day7``). Times are UTC.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping

from openmeteo_client import (
    LEADS,
    MODEL_IDS,
    OpenMeteoClient,
    OpenMeteoError,
    build_url,
    variable_name,
)
from stations import Station

Series = tuple[tuple[dt.datetime, float | None], ...]
SeriesKey = tuple[str, int]
StationSeries = Mapping[SeriesKey, Series]

_TIME_FORMAT = "%Y-%m-%dT%H:%M"


class ResponseError(OpenMeteoError):
    """The response does not have the expected shape, period or values."""


def split_range(
    start: dt.date, end: dt.date, chunk_days: int
) -> tuple[tuple[dt.date, dt.date], ...]:
    """Split ``start..end`` (inclusive) into contiguous chunks of at most ``chunk_days``."""
    if chunk_days < 1:
        raise ValueError(f"chunk_days must be >= 1, got {chunk_days}")
    if end < start:
        raise ValueError(f"start {start} is after end {end}")
    chunks = []
    cursor = start
    while cursor <= end:
        last = min(cursor + dt.timedelta(days=chunk_days - 1), end)
        chunks.append((cursor, last))
        cursor = last + dt.timedelta(days=1)
    return tuple(chunks)


def request_urls(
    station: Station, start: dt.date, end: dt.date, chunk_days: int
) -> tuple[str, ...]:
    """One request URL per chunk for a station (both models in each call)."""
    return tuple(
        build_url(station.lat, station.lon, a, b) for a, b in split_range(start, end, chunk_days)
    )


def _hourly_block(payload: Mapping[str, object]) -> Mapping[str, object]:
    if payload.get("error"):
        raise ResponseError(f"API error: {payload.get('reason', 'unknown reason')}")
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ResponseError("response has no 'hourly' block")
    offset = payload.get("utc_offset_seconds", 0)
    if offset != 0:
        raise ResponseError(f"timestamps are not UTC (utc_offset_seconds={offset})")
    return hourly


def _parse_times(hourly: Mapping[str, object], start: dt.date, end: dt.date) -> list[dt.datetime]:
    raw = hourly.get("time")
    if not isinstance(raw, list):
        raise ResponseError("hourly block has no 'time' list")
    try:
        times = [dt.datetime.strptime(str(t), _TIME_FORMAT).replace(tzinfo=dt.UTC) for t in raw]
    except ValueError as exc:
        raise ResponseError(f"invalid time value in response: {exc}") from None
    expected = ((end - start).days + 1) * 24
    first = dt.datetime.combine(start, dt.time(0), tzinfo=dt.UTC)
    if len(times) != expected or (times and times[0] != first):
        raise ResponseError(
            f"response period does not match the request: got {len(times)} hours starting "
            f"{times[0] if times else 'n/a'}, expected {expected} hours from {first}"
        )
    for i in range(1, len(times)):
        if times[i] - times[i - 1] != dt.timedelta(hours=1):
            raise ResponseError(f"time axis is not consecutive hourly at index {i}")
    return times


def _column(hourly: Mapping[str, object], name: str, length: int) -> list[float | None]:
    values = hourly.get(name)
    if not isinstance(values, list):
        raise ResponseError(f"missing column {name!r}; available: {sorted(hourly)}")
    if len(values) != length:
        raise ResponseError(f"column {name!r} has length {len(values)}, expected {length}")
    for value in values:
        if value is None:
            continue
        numeric = isinstance(value, int | float) and not isinstance(value, bool)
        if not numeric or not math.isfinite(value):
            raise ResponseError(f"column {name!r}: value must be numeric and finite, got {value!r}")
    return values


def parse_chunk(
    payload: Mapping[str, object],
    models: Mapping[str, str],
    start: dt.date,
    end: dt.date,
) -> dict[SeriesKey, Series]:
    """Validate one response and return its series by ``(model_key, lead)``.

    With several models the columns carry a ``_<model_id>`` suffix; with one they do not.
    Null values are kept as ``None``.
    """
    hourly = _hourly_block(payload)
    times = _parse_times(hourly, start, end)
    result: dict[SeriesKey, Series] = {}
    for key, model_id in models.items():
        for lead in LEADS:
            name = variable_name(lead) + (f"_{model_id}" if len(models) > 1 else "")
            values = _column(hourly, name, len(times))
            result[(key, lead)] = tuple(zip(times, values, strict=True))
    return result


def merge_chunks(chunks: list[dict[SeriesKey, Series]]) -> dict[SeriesKey, Series]:
    """Concatenate consecutive chunks per series, checking chronological order."""
    merged: dict[SeriesKey, Series] = {}
    for key in chunks[0]:
        series = tuple(item for chunk in chunks for item in chunk[key])
        stamps = [t for t, _ in series]
        if any(b <= a for a, b in zip(stamps, stamps[1:], strict=False)):
            raise ResponseError(f"merged series {key} is not strictly chronological")
        merged[key] = series
    return merged


def fetch_station_series(
    client: OpenMeteoClient,
    station: Station,
    start: dt.date,
    end: dt.date,
    chunk_days: int,
) -> dict[SeriesKey, Series]:
    """Download (or read from cache) and merge all chunks of one station."""
    parsed = []
    urls = request_urls(station, start, end, chunk_days)
    for url, (chunk_start, chunk_end) in zip(urls, split_range(start, end, chunk_days), strict=True):
        payload = client.get_json(url)
        try:
            parsed.append(parse_chunk(payload, MODEL_IDS, chunk_start, chunk_end))
        except ResponseError as exc:
            client.evict(url)
            raise ResponseError(f"{station.smn_name} {chunk_start}..{chunk_end}: {exc}") from exc
    return merge_chunks(parsed)
