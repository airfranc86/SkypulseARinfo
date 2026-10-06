from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import monitor
import pytest
from fakes import (
    ALL_SECRETS,
    OTHER_SECRET,
    PROD,
    TEST_TOKEN,
    TEST_UPSTASH_URL,
    FakeHttp,
    happy_routes,
    json_result,
    make_dashboard,
    make_day,
    make_week,
    upstash_counter,
)
from monitor_core.production import parse_city_list
from monitor_core.render import Painter
from monitor_core.report import to_jsonable
from monitor_core.runner import Options, build_report
from monitor_core.upstash import UpstashCredentials
from monitor_core.views import render_report

NOW = datetime(2026, 10, 5, 14, 23, tzinfo=UTC)
ESC = "\x1b"


class FakeTty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _env_file(tmp_path: Path, *, token: bool = True) -> Path:
    path = tmp_path / "creds.env"
    lines = [
        f"UPSTASH_REDIS_REST_URL={TEST_UPSTASH_URL}",
        f"OTHER_SECRET={OTHER_SECRET}",
    ]
    if token:
        lines.append(f'UPSTASH_REDIS_REST_TOKEN="{TEST_TOKEN}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _routes(**overrides: Any) -> list:
    """happy_routes with some needles replaced (placed first so they win)."""
    return list(overrides.items()) + happy_routes()


def run(
    argv: list[str],
    *,
    routes: list | None = None,
    environ: dict[str, str] | None = None,
    tty: bool = False,
) -> tuple[int, str, str, FakeHttp]:
    http = FakeHttp(routes if routes is not None else happy_routes())
    out: io.StringIO = FakeTty() if tty else io.StringIO()
    err = io.StringIO()
    code = monitor.main(
        argv, http=http, stdout=out, stderr=err, environ=environ or {}, now=NOW
    )
    return code, out.getvalue(), err.getvalue(), http


@pytest.fixture
def env_path(tmp_path: Path) -> str:
    return str(_env_file(tmp_path))


# ------------------------------------------------------------------ exit codes


def test_everything_ok_exits_zero_and_prints_all_sections(env_path: str) -> None:
    code, out, err, http = run(["--env-file", env_path])
    assert code == 0, out
    assert err == ""
    for title in (
        "Cupos del día",
        "Estado de producción",
        "Fuentes externas",
        "Comparación de modelos",
        "Resumen",
    ):
        assert title in out
    assert "Estado general: OK" in out
    assert http.unmatched == []


def test_checkwx_over_seventy_percent_exits_one(env_path: str) -> None:
    code, out, _, _ = run(
        ["--env-file", env_path],
        routes=_routes(**{"/get/skypulse:checkwx": upstash_counter("150")}),
    )
    assert code == 1
    assert "ATENCIÓN" in out


def test_open_meteo_over_ninety_percent_exits_two(env_path: str) -> None:
    routes = _routes(**{"/get/skypulse:open_meteo": upstash_counter("9500")})
    code, out, _, _ = run(["--env-file", env_path], routes=routes)
    assert code == 2
    assert "CRÍTICO" in out
    assert "95 %" in out


def test_production_503_exits_two(env_path: str) -> None:
    routes = _routes(**{"dashboard?lat=-34.6037": json_result({}, status=503)})
    code, out, _, _ = run(["--env-file", env_path], routes=routes)
    assert code == 2
    assert "503" in out


def test_production_429_is_marked(env_path: str) -> None:
    routes = _routes(**{"dashboard?lat=-27.46": json_result({}, status=429)})
    code, out, _, _ = run(["--env-file", env_path], routes=routes)
    assert code == 2 and "429" in out


def test_slow_dashboard_exits_one(env_path: str) -> None:
    routes = _routes(
        **{"dashboard?lat=-31.4135": json_result(make_dashboard(), elapsed=4.5)}
    )
    code, out, _, _ = run(["--env-file", env_path], routes=routes)
    assert code == 1
    assert "lento" in out.lower()


def test_external_source_failing_exits_one(env_path: str) -> None:
    routes = _routes(**{"api.open-meteo.com": json_result({}, status=429)})
    code, out, _, _ = run(["--env-file", env_path], routes=routes)
    assert code == 1
    assert "IP de esta PC" in out


def test_upstash_down_is_reported_and_does_not_break_the_rest(env_path: str) -> None:
    routes = _routes(**{"/get/": RuntimeError(f"boom {TEST_TOKEN}")})
    code, out, _, _ = run(["--env-file", env_path], routes=routes)
    assert code == 1
    assert "Upstash" in out and "sin respuesta" in out
    assert "Estado de producción" in out and "Fuentes externas" in out


# ------------------------------------------------------------------ usage / config errors


def test_missing_env_file_is_a_usage_error(tmp_path: Path) -> None:
    code, out, err, http = run(["--env-file", str(tmp_path / "nope.env")])
    assert code == 3
    assert out == "" and "nope.env" in err
    assert http.calls == []


def test_env_file_without_upstash_credentials_is_a_config_error(tmp_path: Path) -> None:
    code, _, err, http = run(["--env-file", str(_env_file(tmp_path, token=False))])
    assert code == 3
    assert "UPSTASH_REDIS_REST_TOKEN" in err
    assert (
        "2 variables" in err
    )  # a hint that the file was read, without naming anything else
    assert http.calls == []
    assert not any(secret in err for secret in ALL_SECRETS)


def test_unknown_city_is_a_usage_error(env_path: str) -> None:
    code, _, err, http = run(["--env-file", env_path, "--ciudades", "cordoba,narnia"])
    assert code == 3 and "narnia" in err
    assert http.calls == []


def test_unknown_flag_is_exit_three_not_argparse_default_two() -> None:
    code, _, err, _ = run(["--bogus"])
    assert code == 3
    assert err != ""


# ------------------------------------------------------------------ options


def test_without_env_file_quotas_are_skipped_with_a_clear_notice() -> None:
    code, out, _, http = run([])
    assert code == 0
    assert "--env-file" in out and "omitida" in out.lower()
    assert http.urls_containing("upstash") == []


def test_sin_fuentes_skips_external_sources(env_path: str) -> None:
    _, out, _, http = run(["--env-file", env_path, "--sin-fuentes"])
    assert http.urls_containing("aviationweather") == []
    assert http.urls_containing("api.open-meteo.com") == []
    assert "Fuentes externas" in out and "omitida" in out.lower()


def test_no_modelos_skips_comparison(env_path: str) -> None:
    _, out, _, _ = run(["--env-file", env_path, "--no-modelos"])
    assert "ECMWF mm" not in out
    assert "omitida" in out.lower()


def test_ciudades_limits_the_calls(env_path: str) -> None:
    _, _, _, http = run(
        ["--env-file", env_path, "--ciudades", "cordoba", "--sin-fuentes"]
    )
    assert len(http.urls_containing("/api/weather/dashboard")) == 1
    assert len(http.calls) == 4 + 1 + 2  # upstash + dashboard + niebla + alertas


def test_default_run_stays_within_the_call_budget(env_path: str) -> None:
    _, _, _, http = run(["--env-file", env_path])
    assert len(http.calls) <= 15
    assert http.unmatched == []


def test_upstash_is_only_ever_read_with_get(env_path: str) -> None:
    _, _, _, http = run(["--env-file", env_path])
    upstash_urls = http.urls_containing("upstash.io")
    assert len(upstash_urls) == 4
    assert all(u.startswith(f"{TEST_UPSTASH_URL}/get/") for u in upstash_urls)
    assert http.urls_containing("incr") == [] and http.urls_containing("/set/") == []


def test_production_calls_target_the_render_backend_and_consensus(
    env_path: str,
) -> None:
    _, _, _, http = run(["--env-file", env_path])
    dashboards = http.urls_containing("/api/weather/dashboard")
    assert len(dashboards) == 3
    assert all(u.startswith(PROD) and u.endswith("model=consensus") for u in dashboards)


# ------------------------------------------------------------------ models output


def test_rain_disagreement_days_are_flagged_and_counted(env_path: str) -> None:
    week = make_week()
    week[1] = make_day(1, gfs_mm=0.0, ecmwf_mm=3.2)
    week[3] = make_day(3, gfs_mm=2.0, ecmwf_mm=0.0)
    routes = _routes(
        **{"/api/weather/dashboard": json_result(make_dashboard(days=week))}
    )
    _, out, _, _ = run(["--env-file", env_path, "--ciudades", "cordoba"], routes=routes)
    assert out.count("DESACUERDO") >= 2
    assert "2 de 7" in out


def test_missing_model_is_stated(env_path: str) -> None:
    dash = make_dashboard(days=make_week(ecmwf_mm=None), forecast_models=("gfs",))
    routes = _routes(**{"/api/weather/dashboard": json_result(dash)})
    code, out, _, _ = run(
        ["--env-file", env_path, "--ciudades", "cordoba"], routes=routes
    )
    assert "Falta" in out and "ECMWF" in out
    assert code == 1


# ------------------------------------------------------------------ color / json


def test_no_ansi_when_stdout_is_not_a_terminal(env_path: str) -> None:
    _, out, _, _ = run(["--env-file", env_path])
    assert ESC not in out


def test_ansi_on_a_terminal_by_default(env_path: str) -> None:
    _, out, _, _ = run(["--env-file", env_path], tty=True)
    assert ESC in out


def test_no_color_env_disables_ansi_on_a_terminal(env_path: str) -> None:
    _, out, _, _ = run(["--env-file", env_path], tty=True, environ={"NO_COLOR": "1"})
    assert ESC not in out


def test_json_output_mirrors_the_report_without_colors(env_path: str) -> None:
    code, out, _, _ = run(["--env-file", env_path, "--json"], tty=True)
    assert ESC not in out
    data = json.loads(out)
    assert data["exit_code"] == code == 0
    assert data["overall"] == "ok"
    assert set(data["sections"]) == {"quotas", "production", "sources", "models"}
    quotas = {row["service"]: row for row in data["sections"]["quotas"]["rows"]}
    assert quotas["open_meteo"]["count"] == 2500 and quotas["open_meteo"]["pct"] == 25.0
    assert quotas["checkwx"]["limit"] == 198
    assert len(data["sections"]["production"]["dashboards"]) == 3
    assert data["sections"]["models"]["cities"][0]["days"]


def test_json_marks_skipped_sections() -> None:
    _, out, _, _ = run(["--json", "--sin-fuentes", "--no-modelos"])
    sections = json.loads(out)["sections"]
    assert sections["quotas"]["skipped"] is True
    assert sections["sources"]["skipped"] is True
    assert sections["models"]["skipped"] is True
    assert sections["production"]["skipped"] is False


def test_json_exit_code_follows_the_worst_status(env_path: str) -> None:
    routes = _routes(**{"/get/skypulse:open_meteo": upstash_counter("9900")})
    code, out, _, _ = run(["--env-file", env_path, "--json"], routes=routes)
    data = json.loads(out)
    assert code == 2 and data["exit_code"] == 2 and data["overall"] == "critical"


# ------------------------------------------------------------------ secrets never leak


LEAK_SCENARIOS = pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"/get/": json_result({"error": f"bad {TEST_TOKEN}"}, status=401)},
        {"/get/": RuntimeError(f"boom {TEST_TOKEN} {TEST_UPSTASH_URL} {OTHER_SECRET}")},
        {"/api/weather/dashboard": RuntimeError(f"boom {TEST_TOKEN}")},
        {"aviationweather.gov": RuntimeError(f"boom {OTHER_SECRET}")},
    ],
    ids=["happy", "upstash-401", "upstash-raises", "prod-raises", "source-raises"],
)


@LEAK_SCENARIOS
def test_secrets_never_reach_the_report_even_before_the_final_redaction(
    overrides: dict[str, Any],
) -> None:
    """The last-line redaction must be a safety net, not the only defence."""
    options = Options(
        parse_city_list("cordoba"), UpstashCredentials(TEST_UPSTASH_URL, TEST_TOKEN)
    )
    report = build_report(FakeHttp(_routes(**overrides)), options, NOW)
    text = render_report(report, Painter(False)) + json.dumps(to_jsonable(report))
    for secret in ALL_SECRETS:
        assert secret not in text, secret


@pytest.mark.parametrize("flags", [[], ["--json"]])
@LEAK_SCENARIOS
def test_no_secret_value_appears_in_any_output(
    env_path: str, flags: list[str], overrides: dict[str, Any]
) -> None:
    code, out, err, _ = run(
        ["--env-file", env_path, *flags], routes=_routes(**overrides)
    )
    assert code in (0, 1, 2)
    combined = out + err
    for secret in ALL_SECRETS:
        assert secret not in combined, secret


# ------------------------------------------------------------------ help / progress


def test_help_exits_zero_and_documents_the_exit_codes() -> None:
    code, out, err, http = run(["--help"])
    assert code == 0 and err == ""
    assert "--env-file" in out and "--sin-fuentes" in out and "--no-modelos" in out
    assert "código" in out.lower() or "codigo" in out.lower()
    assert http.calls == []


def test_progress_goes_to_stderr_only_when_it_is_a_terminal() -> None:
    http = FakeHttp(happy_routes())
    out, err = io.StringIO(), FakeTty()
    monitor.main(
        ["--sin-fuentes"], http=http, stdout=out, stderr=err, environ={}, now=NOW
    )
    lines = [line for line in err.getvalue().splitlines() if line]
    assert lines
    assert all(
        line.startswith("  …") for line in lines
    )  # progress only, never the report
    assert "Estado general" not in err.getvalue()
    assert ESC not in out.getvalue()


def test_json_mode_prints_no_progress_even_on_a_terminal() -> None:
    out, err = io.StringIO(), FakeTty()
    monitor.main(
        ["--json", "--sin-fuentes"],
        http=FakeHttp(happy_routes()),
        stdout=out,
        stderr=err,
        environ={},
        now=NOW,
    )
    assert err.getvalue() == ""
    json.loads(out.getvalue())


def test_no_secret_in_usage_error_output(tmp_path: Path) -> None:
    _, out, err, _ = run(["--env-file", str(_env_file(tmp_path, token=False))])
    assert not any(secret in out + err for secret in ALL_SECRETS)


# ------------------------------------------------------------------ --web (FRA-364)


def _run_web(argv: list[str], routes: list | None = None) -> tuple[int, dict, str]:
    """main(--web ...) with an injected `serve` that records what it was given."""
    http = FakeHttp(routes if routes is not None else happy_routes())
    seen: dict[str, Any] = {}

    def fake_serve(collect, secrets, *, port, out):
        seen.update(collect=collect, secrets=tuple(secrets), port=port)
        return 0

    err = io.StringIO()
    code = monitor.main(
        argv,
        http=http,
        stdout=io.StringIO(),
        stderr=err,
        environ={},
        now=NOW,
        serve=fake_serve,
    )
    return code, seen, err.getvalue()


def test_web_mode_hands_a_collector_and_the_default_port_to_serve() -> None:
    code, seen, _ = _run_web(["--web"])
    assert code == 0
    assert seen["port"] == 8765
    report = seen["collect"]()
    assert report.generated_at == NOW
    assert [s.key for s in report.sections] == ["quotas", "production", "sources", "models"]


def test_web_mode_passes_the_secrets_so_the_page_can_redact_them(tmp_path: Path) -> None:
    code, seen, _ = _run_web(["--web", "--puerto", "9000", "--env-file", str(_env_file(tmp_path))])
    assert code == 0
    assert seen["port"] == 9000
    assert TEST_TOKEN in seen["secrets"] and TEST_UPSTASH_URL in seen["secrets"]


def test_web_mode_does_not_collect_until_serve_asks_for_it() -> None:
    http = FakeHttp(happy_routes())
    monitor.main(
        ["--web"],
        http=http,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
        environ={},
        now=NOW,
        serve=lambda *a, **k: 0,
    )
    assert http.calls == []


def test_web_mode_rejects_json_and_bad_ports() -> None:
    for argv in (["--web", "--json"], ["--web", "--puerto", "80"], ["--web", "--puerto", "70000"]):
        code, seen, err = _run_web(argv)
        assert code == 3, argv
        assert seen == {}
        assert "error" in err


def test_puerto_without_web_is_a_usage_error() -> None:
    code, _, err = _run_web(["--puerto", "9000"])
    assert code == 3
    assert "--web" in err


def test_web_mode_reports_a_busy_port_as_a_usage_error() -> None:
    def busy(collect, secrets, *, port, out):
        raise OSError(98, "Address already in use")

    err = io.StringIO()
    code = monitor.main(
        ["--web"], http=FakeHttp([]), stdout=io.StringIO(), stderr=err, environ={}, now=NOW, serve=busy
    )
    assert code == 3
    assert "8765" in err.getvalue()
