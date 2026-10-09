"""Códec JSON explícito de las dataclasses de Open-Meteo (último dato bueno en Redis).

Sin pickle: solo los tipos registrados se pueden reconstruir y todo valor se valida contra los type
hints de la dataclass. Un valor que no encaje es un `CodecError`, nunca un objeto a medias.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.core.dataclass_codec import CodecError, DataclassCodec
from app.services.openmeteo import (
    DailyForecastDataExt,
    HourlyForecastExt,
    MultiModelDailyData,
    OpenMeteoCurrent,
)

_CODEC = DataclassCodec(OpenMeteoCurrent, DailyForecastDataExt, HourlyForecastExt, MultiModelDailyData)


def _roundtrip(value):
    type_name, data = _CODEC.encode(value)
    # Lo que se guarda tiene que sobrevivir a un viaje por texto JSON.
    return _CODEC.decode(type_name, json.loads(json.dumps(data)))


def _current(**overrides) -> OpenMeteoCurrent:
    base = dict(
        temp_c=23.5, feels_like_c=22.1, humidity=52.0, wind_speed_kmh=18.0, wind_dir_deg=270.0,
        pressure_hpa=1014.2, precip_1h_mm=0.0, cloud_cover=10.0, weather_code=0, description=None,
        fetched_at=datetime(2026, 10, 8, 15, 30, 12, 345000, tzinfo=timezone.utc),
        observed_at=datetime(2026, 10, 8, 15, 15, tzinfo=timezone.utc), wind_gust_kmh=31.0,
    )
    base.update(overrides)
    return OpenMeteoCurrent(**base)


def _daily(**overrides) -> DailyForecastDataExt:
    base = dict(
        dates=["2026-10-08", "2026-10-09"], day_labels=["jueves", "viernes"],
        temp_max=[30.0, None], temp_min=[18.0, 17.5], precip_sum=[0.0, 4.2],
        precip_prob_max=[10.0, None], wind_speed_max=[25.0, 30.0], wind_gusts_max=[40.0, None],
        humidity_mean=[50.0, 60.0], uv_max=[8.0, 7.0], weather_codes=[0, None],
        sunrise=["2026-10-08T06:30", "2026-10-09T06:29"], sunset=["2026-10-08T20:00", "2026-10-09T20:01"],
        daylight_seconds=[48600.0, None], wind_dir_dominant=[270.0, 180.0], cloud_cover_mean=[10.0, None],
    )
    base.update(overrides)
    return DailyForecastDataExt(**base)


def _hourly(**overrides) -> HourlyForecastExt:
    base = dict(
        timestamps=[1791000000, 1791003600], hour_labels=["14:00", "15:00"],
        dates=["2026-10-08", "2026-10-08"], temps_c=[20.0, None], precipitations=[0.0, 0.2],
        precip_probs=[10.0, 20.0], wind_speeds=[12.0, 14.0], weather_codes=[1, None],
        is_day=[True, False], freezing_level_heights_m=[3000.0, None], wind_gusts_kmh=[30.0, 35.0],
        cape_j_kg=[0.0, 120.0], temps_850_c=[8.0, None], humidities=[55.0, 60.0],
        cloud_covers=[20.0, 30.0], wind_dirs_deg=[90.0, 100.0], elevation_m=25.0,
    )
    base.update(overrides)
    return HourlyForecastExt(**base)


def test_current_roundtrip_keeps_datetimes_and_nones() -> None:
    value = _current(observed_at=None, weather_code=None, wind_gust_kmh=None)
    assert _roundtrip(value) == value


def test_current_roundtrip_keeps_tz_aware_instants() -> None:
    ar = timezone(timedelta(hours=-3))
    value = _current(fetched_at=datetime(2026, 10, 8, 12, 0, tzinfo=ar))
    restored = _roundtrip(value)
    assert restored == value
    assert restored.fetched_at.utcoffset() == timedelta(hours=-3)


def test_naive_datetime_stays_naive() -> None:
    value = _current(fetched_at=datetime(2026, 10, 8, 12, 0))
    assert _roundtrip(value).fetched_at.tzinfo is None


def test_daily_roundtrip_with_none_holes() -> None:
    value = _daily()
    assert _roundtrip(value) == value


def test_hourly_roundtrip_keeps_booleans_and_optional_scalars() -> None:
    value = _hourly()
    restored = _roundtrip(value)
    assert restored == value
    assert all(isinstance(x, bool) for x in restored.is_day)
    assert _roundtrip(_hourly(elevation_m=None)).elevation_m is None


def test_multi_model_roundtrip_rebuilds_nested_dataclasses() -> None:
    value = MultiModelDailyData(
        models={"gfs_seamless": _daily(), "ecmwf_ifs025": _daily(temp_max=[29.0, 28.0])},
        consensus_pct_per_day=[100.0, 50.0],
        rain_consensus_per_day=["all_agree_dry", "split"],
    )
    restored = _roundtrip(value)
    assert restored == value
    assert isinstance(restored.models["ecmwf_ifs025"], DailyForecastDataExt)


def test_raw_json_dict_roundtrip_for_the_niebla_payload() -> None:
    raw = {"current": {"visibility": 9000.0, "weather_code": 2}, "hourly": {"time": ["a"], "visibility": [None]}}
    assert _roundtrip(raw) == raw


def test_integers_are_accepted_where_floats_are_expected() -> None:
    type_name, data = _CODEC.encode(_current())
    data["temp_c"] = 23  # un float entero puede salir de JSON como int
    restored = _CODEC.decode(type_name, data)
    assert restored.temp_c == 23.0 and isinstance(restored.temp_c, float)


def test_missing_optional_field_uses_the_dataclass_default() -> None:
    type_name, data = _CODEC.encode(_daily())
    del data["cloud_cover_mean"]
    assert _CODEC.decode(type_name, data).cloud_cover_mean == []


def test_encoding_an_unregistered_dataclass_is_refused() -> None:
    @dataclass(frozen=True)
    class Intruso:
        x: int

    with pytest.raises(CodecError):
        _CODEC.encode(Intruso(1))


def test_encoding_an_arbitrary_object_is_refused() -> None:
    with pytest.raises(CodecError):
        _CODEC.encode(object())


@pytest.mark.parametrize("type_name", ["os.system", "Intruso", "", "__main__.OpenMeteoCurrent"])
def test_decoding_an_unknown_type_name_is_refused(type_name: str) -> None:
    _registered, valid_data = _CODEC.encode(_current())   # datos válidos: solo el nombre del tipo está mal
    with pytest.raises(CodecError):
        _CODEC.decode(type_name, valid_data)


def _tampered(mutate) -> tuple[str, dict]:
    type_name, data = _CODEC.encode(_current())
    mutate(data)
    return type_name, data


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(temp_c="caluroso"),       # string donde va un número
        lambda d: d.update(temp_c=True),             # bool no es número
        lambda d: d.update(weather_code=1.5),        # float donde va un int
        lambda d: d.update(fetched_at="no es fecha"),  # datetime ilegible
        lambda d: d.update(fetched_at=None),         # campo obligatorio nulo
        lambda d: d.update(fetched_at=1790000000),   # datetime como número
        lambda d: d.update(intruso=1),               # campo que no existe
        lambda d: d.pop("fetched_at"),               # falta un campo obligatorio
        lambda d: d.update(description=["x"]),       # lista donde va un string
    ],
    ids=["str-for-float", "bool-for-float", "float-for-int", "bad-datetime", "null-required",
         "number-for-datetime", "unknown-field", "missing-required", "list-for-str"],
)
def test_malformed_payloads_raise_codec_error(mutate) -> None:
    type_name, data = _tampered(mutate)
    with pytest.raises(CodecError):
        _CODEC.decode(type_name, data)


def test_a_non_object_payload_is_refused() -> None:
    with pytest.raises(CodecError):
        _CODEC.decode("OpenMeteoCurrent", ["no", "es", "objeto"])


def test_list_items_are_validated() -> None:
    type_name, data = _CODEC.encode(_daily())
    data["temp_max"] = [30.0, "x"]
    with pytest.raises(CodecError):
        _CODEC.decode(type_name, data)
    type_name, data = _CODEC.encode(_daily())
    data["dates"] = "2026-10-08"
    with pytest.raises(CodecError):
        _CODEC.decode(type_name, data)


def test_codec_errors_never_echo_the_value() -> None:
    type_name, data = _tampered(lambda d: d.update(temp_c="SECRETO-123"))
    with pytest.raises(CodecError) as raised:
        _CODEC.decode(type_name, data)
    assert "SECRETO" not in str(raised.value)


def test_encoded_data_is_plain_json_types_only() -> None:
    _type_name, data = _CODEC.encode(_current())
    assert isinstance(json.dumps(data), str)
    assert isinstance(data["fetched_at"], str)
