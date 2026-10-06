from __future__ import annotations

from datetime import UTC, datetime

from fakes import FakeHttp, failure, happy_routes, json_result, text_result
from monitor_core.httpio import USER_AGENT
from monitor_core.sources import collect_sources
from monitor_core.status import Status

NOW = datetime(2026, 10, 5, 14, 23, tzinfo=UTC)


def _probes(section):
    return {p.key: p for p in section.probes}


def _external_routes(**replace):
    routes = dict(happy_routes())
    routes.update(replace)
    return list(routes.items())


def test_happy_path_makes_exactly_four_calls_one_per_source() -> None:
    http = FakeHttp(happy_routes())
    section = collect_sources(http, NOW)
    assert len(http.calls) == 4
    assert http.unmatched == []
    assert len(http.urls_containing("api.open-meteo.com")) == 1
    assert section.status is Status.OK


def test_urls_are_the_documented_ones() -> None:
    http = FakeHttp(happy_routes())
    collect_sources(http, NOW)
    urls = {c.url for c in http.calls}
    assert "https://aviationweather.gov/api/data/metar?ids=SACO&format=json" in urls
    assert "https://ssl.smn.gob.ar/CAP/AR.php" in urls
    assert "https://ws.smn.gob.ar/alerts/type/AL" in urls
    assert any(u.startswith("https://api.open-meteo.com/v1/forecast?") for u in urls)
    assert any("current=temperature_2m" in u for u in urls)


def test_calls_use_a_bounded_timeout() -> None:
    # The User-Agent is added by UrllibGetter (covered in test_httpio); here only the timeout.
    http = FakeHttp(happy_routes())
    collect_sources(http, NOW)
    assert all(0 < c.timeout <= 60 for c in http.calls)


def test_user_agent_identifies_the_tool() -> None:
    assert "SkyPulse" in USER_AGENT


def test_awc_metar_detail_has_station_and_observation_age() -> None:
    probes = _probes(collect_sources(FakeHttp(happy_routes()), NOW))
    detail = probes["awc_metar"].detail
    assert "SACO" in detail and "23 min" in detail


def test_cap_feed_counts_items_and_reports_headers() -> None:
    probes = _probes(collect_sources(FakeHttp(happy_routes()), NOW))
    cap = probes["smn_cap"]
    assert cap.state == "ok"
    assert "3" in cap.detail and "xml" in cap.detail.lower()


def test_old_smn_alerts_404_is_a_known_down_source_and_does_not_alarm() -> None:
    section = collect_sources(FakeHttp(happy_routes()), NOW)
    old = _probes(section)["smn_old_alerts"]
    assert old.state == "known_down"
    assert old.status is Status.OK
    assert section.status is Status.OK


def test_old_smn_alerts_503_is_also_known_down() -> None:
    routes = _external_routes(
        **{"ws.smn.gob.ar/alerts/type/AL": text_result("x", status=503)}
    )
    old = _probes(collect_sources(FakeHttp(routes), NOW))["smn_old_alerts"]
    assert old.state == "known_down" and old.status is Status.OK


def test_old_smn_alerts_coming_back_is_reported_as_news() -> None:
    routes = _external_routes(**{"ws.smn.gob.ar/alerts/type/AL": json_result([])})
    old = _probes(collect_sources(FakeHttp(routes), NOW))["smn_old_alerts"]
    assert old.state == "ok" and "volvió" in old.detail.lower()


def test_old_smn_alerts_unexpected_error_is_attention() -> None:
    routes = _external_routes(
        **{"ws.smn.gob.ar/alerts/type/AL": text_result("x", status=500)}
    )
    old = _probes(collect_sources(FakeHttp(routes), NOW))["smn_old_alerts"]
    assert old.state == "error" and old.status is Status.WARN


def test_open_meteo_reports_value_and_warns_about_the_pc_quota() -> None:
    probe = _probes(collect_sources(FakeHttp(happy_routes()), NOW))["open_meteo"]
    assert "18,3" in probe.detail
    assert probe.note is not None and "cupo" in probe.note and "PC" in probe.note


def test_open_meteo_429_is_attention_not_critical() -> None:
    routes = _external_routes(**{"api.open-meteo.com": json_result({}, status=429)})
    section = collect_sources(FakeHttp(routes), NOW)
    probe = _probes(section)["open_meteo"]
    assert probe.state == "error" and probe.status is Status.WARN
    assert "429" in probe.detail
    assert section.status is Status.WARN


def test_awc_timeout_is_attention_and_does_not_raise() -> None:
    routes = _external_routes(**{"aviationweather.gov": failure("TimeoutError")})
    section = collect_sources(FakeHttp(routes), NOW)
    probe = _probes(section)["awc_metar"]
    assert probe.state == "error" and probe.status is Status.WARN
    assert "sin respuesta" in probe.detail


def test_awc_empty_list_is_attention() -> None:
    routes = _external_routes(**{"aviationweather.gov": json_result([])})
    probe = _probes(collect_sources(FakeHttp(routes), NOW))["awc_metar"]
    assert probe.status is Status.WARN


def test_cap_without_items_is_ok_and_says_zero() -> None:
    routes = _external_routes(**{"ssl.smn.gob.ar/CAP": text_result("<rss></rss>")})
    probe = _probes(collect_sources(FakeHttp(routes), NOW))["smn_cap"]
    assert probe.state == "ok" and "0" in probe.detail


def test_client_exception_is_contained_per_probe() -> None:
    routes = _external_routes(
        **{"aviationweather.gov": RuntimeError("secret-ish message")}
    )
    section = collect_sources(FakeHttp(routes), NOW)
    probe = _probes(section)["awc_metar"]
    assert probe.status is Status.WARN
    assert "secret-ish" not in probe.detail
    assert "RuntimeError" in probe.detail
