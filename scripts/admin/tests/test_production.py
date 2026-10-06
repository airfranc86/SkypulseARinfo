from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import (
    PROD,
    FakeHttp,
    failure,
    json_result,
    make_alertas,
    make_dashboard,
    make_niebla,
    text_result,
)
from monitor_core.production import (
    CITIES,
    SLOW_SECONDS,
    classify_http,
    collect_production,
    fetch_alertas,
    fetch_dashboard,
    fetch_niebla,
    format_age,
    parse_city_list,
)
from monitor_core.status import Status

NOW = datetime(2026, 10, 5, 14, 23, tzinfo=UTC)
CORDOBA = CITIES["cordoba"]


# ------------------------------------------------------------------ classify_http


def test_ok_response_is_ok_without_flags() -> None:
    assert classify_http(200, 0.5) == (Status.OK, ())


def test_slow_threshold_is_strictly_above_three_seconds() -> None:
    assert SLOW_SECONDS == 3.0
    assert classify_http(200, 3.0) == (Status.OK, ())
    assert classify_http(200, 3.01) == (Status.WARN, ("lento",))


def test_429_is_critical_and_flagged() -> None:
    status, flags = classify_http(429, 0.4)
    assert status is Status.CRITICAL
    assert "429" in flags


def test_503_is_critical_and_flagged() -> None:
    status, flags = classify_http(503, 1.0)
    assert status is Status.CRITICAL
    assert "503" in flags


def test_other_http_errors_are_critical() -> None:
    status, flags = classify_http(500, 0.2)
    assert status is Status.CRITICAL
    assert flags == ("http_500",)


def test_no_response_is_critical() -> None:
    assert classify_http(None, 60.0) == (Status.CRITICAL, ("sin_respuesta",))


def test_slow_failure_keeps_both_flags() -> None:
    status, flags = classify_http(503, 12.0)
    assert status is Status.CRITICAL
    assert flags == ("503", "lento")


# ------------------------------------------------------------------ cities


def test_default_cities_and_coordinates() -> None:
    assert (CITIES["cordoba"].lat, CITIES["cordoba"].lon) == (-31.4135, -64.181)
    assert (CITIES["caba"].lat, CITIES["caba"].lon) == (-34.6037, -58.3816)
    assert (CITIES["resistencia"].lat, CITIES["resistencia"].lon) == (-27.46, -58.9867)


def test_parse_city_list_trims_lowercases_and_dedupes() -> None:
    cities = parse_city_list(" Cordoba , CABA,cordoba")
    assert [c.key for c in cities] == ["cordoba", "caba"]


def test_parse_city_list_rejects_unknown_with_valid_options() -> None:
    with pytest.raises(ValueError) as info:
        parse_city_list("cordoba,narnia")
    message = str(info.value)
    assert "narnia" in message and "resistencia" in message


def test_parse_city_list_rejects_empty() -> None:
    with pytest.raises(ValueError):
        parse_city_list(" , ")


# ------------------------------------------------------------------ format_age


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (0, "0 min"),
        (23.4, "23 min"),
        (59.6, "1 h 0 min"),
        (60, "1 h 0 min"),
        (135, "2 h 15 min"),
    ],
)
def test_format_age(minutes: float, expected: str) -> None:
    assert format_age(minutes) == expected


def test_format_age_unknown_and_future() -> None:
    assert format_age(None) == "s/d"
    assert format_age(-30) == "0 min"


# ------------------------------------------------------------------ dashboard


def _dashboard_http(payload=None, **result_kwargs) -> FakeHttp:
    return FakeHttp(
        [
            (
                "/api/weather/dashboard",
                json_result(payload or make_dashboard(), **result_kwargs),
            )
        ]
    )


def test_dashboard_url_uses_consensus_model_and_city_coordinates() -> None:
    http = _dashboard_http()
    fetch_dashboard(http, PROD, CORDOBA, NOW)
    url = http.calls[0].url
    assert (
        url == f"{PROD}/api/weather/dashboard?lat=-31.4135&lon=-64.181&model=consensus"
    )
    assert http.calls[0].timeout == 60.0


def test_dashboard_parses_metar_source_station_age_and_models() -> None:
    info, payload = fetch_dashboard(_dashboard_http(), PROD, CORDOBA, NOW)
    assert info.status is Status.OK
    assert info.http_status == 200
    assert info.source == "metar" and info.source_reason == "metar_ok"
    assert info.station_icao == "SACO" and info.station_distance_km == 9.4
    assert info.age_minutes == 23.0
    assert info.forecast_models == ("gfs", "ecmwf")
    assert payload is not None and "forecast_7d" in payload


def test_dashboard_without_metar_station_is_still_ok() -> None:
    payload = make_dashboard(source="openmeteo", reason="metar_too_far")
    info, _ = fetch_dashboard(_dashboard_http(payload), PROD, CORDOBA, NOW)
    assert info.status is Status.OK
    assert info.source == "openmeteo" and info.source_reason == "metar_too_far"
    assert info.station_icao is None and info.station_distance_km is None


def test_dashboard_naive_observed_at_is_taken_as_utc() -> None:
    payload = make_dashboard(observed_at="2026-10-05T14:00:00")
    info, _ = fetch_dashboard(_dashboard_http(payload), PROD, CORDOBA, NOW)
    assert info.age_minutes == 23.0


def test_dashboard_missing_observed_at_has_unknown_age() -> None:
    payload = make_dashboard(observed_at=None)
    info, _ = fetch_dashboard(_dashboard_http(payload), PROD, CORDOBA, NOW)
    assert info.age_minutes is None and info.status is Status.OK


def test_dashboard_missing_model_is_attention() -> None:
    payload = make_dashboard(forecast_models=("gfs",))
    info, _ = fetch_dashboard(_dashboard_http(payload), PROD, CORDOBA, NOW)
    assert info.status is Status.WARN
    assert "falta_modelo" in info.flags


def test_dashboard_stale_current_is_attention() -> None:
    info, _ = fetch_dashboard(
        _dashboard_http(make_dashboard(stale=True)), PROD, CORDOBA, NOW
    )
    assert info.status is Status.WARN
    assert "dato_viejo" in info.flags


def test_dashboard_slow_is_attention() -> None:
    info, _ = fetch_dashboard(_dashboard_http(elapsed=4.2), PROD, CORDOBA, NOW)
    assert info.status is Status.WARN and "lento" in info.flags
    assert info.latency_s == 4.2


@pytest.mark.parametrize("code", [429, 503])
def test_dashboard_rate_limit_and_unavailable_are_critical(code: int) -> None:
    http = _dashboard_http({"detail": "x"}, status=code)
    info, payload = fetch_dashboard(http, PROD, CORDOBA, NOW)
    assert info.status is Status.CRITICAL
    assert str(code) in info.flags
    assert payload is None


def test_dashboard_transport_failure_is_critical() -> None:
    http = FakeHttp([("/api/weather/dashboard", failure("TimeoutError", elapsed=60.0))])
    info, payload = fetch_dashboard(http, PROD, CORDOBA, NOW)
    assert info.status is Status.CRITICAL and "sin_respuesta" in info.flags
    assert info.http_status is None and payload is None


def test_dashboard_invalid_json_is_critical() -> None:
    http = FakeHttp([("/api/weather/dashboard", text_result("<html>"))])
    info, payload = fetch_dashboard(http, PROD, CORDOBA, NOW)
    assert info.status is Status.CRITICAL and "respuesta_invalida" in info.flags
    assert payload is None


# ------------------------------------------------------------------ niebla / alertas


def test_niebla_reports_source_and_station() -> None:
    http = FakeHttp([("/api/niebla", json_result(make_niebla()))])
    info = fetch_niebla(http, PROD, CORDOBA)
    assert http.calls[0].url == f"{PROD}/api/niebla?lat=-31.4135&lon=-64.181"
    assert info.status is Status.OK
    assert (info.source, info.station, info.distance_km) == ("metar", "SACO", 9.4)


def test_niebla_503_is_critical() -> None:
    http = FakeHttp([("/api/niebla", json_result({}, status=503))])
    info = fetch_niebla(http, PROD, CORDOBA)
    assert info.status is Status.CRITICAL and "503" in info.flags


def test_alertas_available_true() -> None:
    http = FakeHttp([("/api/alertas-smn", json_result(make_alertas(available=True)))])
    info = fetch_alertas(http, PROD)
    assert http.calls[0].url == f"{PROD}/api/alertas-smn"
    assert info.available is True and info.status is Status.OK


def test_alertas_unavailable_is_informational_known_down_source() -> None:
    http = FakeHttp([("/api/alertas-smn", json_result(make_alertas(available=False)))])
    info = fetch_alertas(http, PROD)
    assert info.available is False
    assert info.status is Status.OK  # the official SMN feed is a known-down source


def test_alertas_429_is_critical() -> None:
    http = FakeHttp([("/api/alertas-smn", json_result({}, status=429))])
    info = fetch_alertas(http, PROD)
    assert info.status is Status.CRITICAL and info.available is None


# ------------------------------------------------------------------ section


def _full_http(**overrides) -> FakeHttp:
    routes = [
        ("/api/weather/dashboard", json_result(make_dashboard())),
        ("/api/niebla", json_result(make_niebla())),
        ("/api/alertas-smn", json_result(make_alertas())),
    ]
    return FakeHttp(overrides.get("routes", routes))


def test_collect_production_makes_one_call_per_city_plus_two() -> None:
    http = _full_http()
    cities = parse_city_list("cordoba,caba,resistencia")
    section, payloads = collect_production(http, PROD, cities, NOW)
    assert len(http.calls) == 5
    assert http.unmatched == []
    assert section.status is Status.OK
    assert [d.city for d in section.dashboards] == [
        "Córdoba",
        "Buenos Aires",
        "Resistencia",
    ]
    assert set(payloads) == {"cordoba", "caba", "resistencia"}
    assert all(p is not None for p in payloads.values())


def test_collect_production_niebla_uses_the_first_city() -> None:
    http = _full_http()
    collect_production(http, PROD, parse_city_list("caba,cordoba"), NOW)
    niebla_url = http.urls_containing("/api/niebla")[0]
    assert "lat=-34.6037" in niebla_url


def test_collect_production_takes_the_worst_status() -> None:
    routes = [
        ("lat=-34.6037", json_result({}, status=503)),
        ("/api/weather/dashboard", json_result(make_dashboard())),
        ("/api/niebla", json_result(make_niebla(), elapsed=5.0)),
        ("/api/alertas-smn", json_result(make_alertas())),
    ]
    section, payloads = collect_production(
        FakeHttp(routes), PROD, parse_city_list("cordoba,caba"), NOW
    )
    assert section.status is Status.CRITICAL
    assert payloads["caba"] is None and payloads["cordoba"] is not None
    assert "503" in section.summary or "crític" in section.summary.lower()
