"""Tests for the regtemp fixed-width parser."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from regtemp import (
    DailyObs,
    RegtempParseError,
    group_by_station,
    load_regtemp,
    parse_regtemp,
)


def test_parses_all_rows_of_the_sample(regtemp_sample: str) -> None:
    obs = parse_regtemp(regtemp_sample)

    assert len(obs) == 6
    assert all(o.date == dt.date(2026, 10, 4) for o in obs)
    assert [o.station_name for o in obs] == [
        "AEROPARQUE AERO",
        "BAHIA BLANCA AERO",
        "BARILOCHE AERO",
        "BASE BELGANO II",
        "BENITO JUAREZ AERO",
        "BOLIVAR AERO",
    ]


def test_regular_row_values(regtemp_sample: str) -> None:
    first = parse_regtemp(regtemp_sample)[0]

    assert first == DailyObs(dt.date(2026, 10, 4), "AEROPARQUE AERO", 22.6, 12.2)


def test_negative_values(regtemp_sample: str) -> None:
    belgrano = parse_regtemp(regtemp_sample)[3]

    assert belgrano.tmax == -13.5
    assert belgrano.tmin == -22.3


def test_both_columns_empty_become_none(regtemp_sample: str) -> None:
    benito = parse_regtemp(regtemp_sample)[4]

    assert benito.tmax is None
    assert benito.tmin is None
    assert benito.station_name == "BENITO JUAREZ AERO"


def test_only_tmax_empty_becomes_none(regtemp_sample: str) -> None:
    bolivar = parse_regtemp(regtemp_sample)[5]

    assert bolivar.tmax is None
    assert bolivar.tmin == 4.5


def test_blank_lines_and_crlf_are_ignored(regtemp_sample: str) -> None:
    text = "\r\n" + regtemp_sample.replace("\n", "\r\n") + "\r\n\r\n"

    assert parse_regtemp(text) == parse_regtemp(regtemp_sample)


def test_rows_without_header_use_default_columns() -> None:
    text = "04102026  22.6  12.2 AEROPARQUE AERO\n"

    assert parse_regtemp(text)[0].tmax == 22.6


def test_empty_text_returns_empty_tuple() -> None:
    assert parse_regtemp("") == ()


def test_invalid_date_raises_with_line_number() -> None:
    text = "FECHA    TMAX  TMIN  NOMBRE\n--------\n99992026  22.6  12.2 X AERO\n"

    with pytest.raises(RegtempParseError, match="line 3"):
        parse_regtemp(text)


def test_malformed_temperature_raises() -> None:
    text = "04102026  2x.6  12.2 AEROPARQUE AERO\n"

    with pytest.raises(RegtempParseError, match="temperature"):
        parse_regtemp(text)


def test_missing_station_name_raises() -> None:
    text = "04102026  22.6  12.2\n"

    with pytest.raises(RegtempParseError, match="station"):
        parse_regtemp(text)


def test_non_finite_temperature_raises() -> None:
    text = "04102026   nan  12.2 AEROPARQUE AERO\n"

    with pytest.raises(RegtempParseError):
        parse_regtemp(text)


def test_parse_error_is_a_value_error() -> None:
    assert issubclass(RegtempParseError, ValueError)


def test_daily_obs_is_frozen() -> None:
    obs = DailyObs(dt.date(2026, 10, 4), "X", 1.0, 0.0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.tmax = 5.0  # type: ignore[misc]


def test_load_regtemp_reads_latin1(tmp_path, regtemp_sample: str) -> None:
    text = regtemp_sample + "04102026  10.0   2.0 PEÑA AERO\n"
    path = tmp_path / "regtemp.txt"
    path.write_bytes(text.encode("latin-1"))

    obs = load_regtemp(path)

    assert obs[-1].station_name == "PEÑA AERO"
    assert len(obs) == 7


def test_group_by_station(regtemp_sample: str) -> None:
    extra = regtemp_sample + "05102026  20.0  10.0 AEROPARQUE AERO\n"

    grouped = group_by_station(parse_regtemp(extra))

    assert len(grouped["AEROPARQUE AERO"]) == 2
    assert len(grouped["BOLIVAR AERO"]) == 1
    assert isinstance(grouped["AEROPARQUE AERO"], tuple)
