"""HTML page of the local monitor (FRA-364): same information as the terminal, escaped and script-free."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fakes import (
    ALL_SECRETS,
    PROD,
    TEST_TOKEN,
    TEST_UPSTASH_URL,
    FakeHttp,
    happy_routes,
    json_result,
    make_dashboard,
    make_day,
    make_week,
)
from monitor_core.html_view import render_page
from monitor_core.production import parse_city_list
from monitor_core.report import Report
from monitor_core.runner import Options, build_report
from monitor_core.upstash import UpstashCredentials

NOW = datetime(2026, 10, 5, 14, 23, tzinfo=UTC)


def _report(routes: list | None = None, *, creds: bool = True, **opts: Any) -> Report:
    http = FakeHttp(routes if routes is not None else happy_routes())
    credentials = UpstashCredentials(TEST_UPSTASH_URL, TEST_TOKEN) if creds else None
    options = Options(
        cities=parse_city_list("cordoba,caba"), credentials=credentials, **opts
    )
    return build_report(http, options, NOW)


def _page(report: Report | None = None, **kwargs: Any) -> str:
    return render_page(report if report is not None else _report(), **kwargs)


def _text(html_text: str) -> str:
    """Visible text only, to assert on what the owner reads."""
    no_style = re.sub(r"<style.*?</style>", "", html_text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", no_style))


# ------------------------------------------------------------------ structure


def test_page_is_a_complete_spanish_document_with_the_report_time() -> None:
    page = _page()
    assert page.startswith("<!doctype html>")
    assert '<html lang="es">' in page
    assert "<title>SkyPulse · monitor local</title>" in page
    assert "2026-10-05 14:23 UTC" in _text(page)


def test_page_has_the_four_sections_and_the_summary() -> None:
    text = _text(_page())
    for title in (
        "Cupos del día",
        "Estado de producción",
        "Fuentes externas",
        "Comparación de modelos",
        "Resumen",
    ):
        assert title in text


def test_overall_status_and_exit_code_are_shown() -> None:
    text = _text(_page())
    assert "Estado general" in text
    assert "código de salida 0" in text


def test_page_has_no_scripts_and_loads_nothing_from_outside() -> None:
    page = _page()
    for forbidden in ("<script", "<link", "<img", "<iframe", " src=", "@import", "url("):
        assert forbidden not in page, forbidden
    assert not re.search(r'href="https?://', page)


# ------------------------------------------------------------------ content


def test_quotas_show_counts_limits_and_usage_with_es_ar_numbers() -> None:
    text = _text(_page())
    assert "Open-Meteo" in text
    assert "2.500" in text  # open_meteo counter from happy_routes
    assert "10.000" in text  # its daily limit
    assert "25 %" in text


def test_a_usage_bar_exposes_its_percentage_as_a_number() -> None:
    page = _page()
    assert re.search(r'<div class="bar [a-z]+"[^>]*role="meter"[^>]*aria-valuenow="25', page)


def test_status_is_written_not_only_coloured() -> None:
    page = _page(_report([("/get/skypulse:checkwx:counter:", json_result({"result": "190"}))] + happy_routes()))
    assert re.search(r'class="badge crit">CRÍTICO<', page)
    assert re.search(r'class="badge ok">OK<', page)


def test_production_rows_show_source_station_and_models() -> None:
    text = _text(_page())
    assert "Córdoba" in text and "Buenos Aires" in text
    assert "metar (metar_ok)" in text
    assert "SACO a 9,4 km" in text
    assert "GFS+ECMWF" in text
    assert "available: no" in text  # SMN alerts: known down


def test_sources_show_the_known_down_endpoint_apart_from_failures() -> None:
    text = _text(_page())
    assert "caído conocido" in text
    assert "Consultas directas desde esta PC: la IP no es la de Render." in text


def test_rain_disagreement_days_are_flagged_and_counted() -> None:
    days = make_week()
    days[2] = make_day(2, gfs_mm=0.0, ecmwf_mm=3.0)
    routes = [(f"{PROD}/api/weather/dashboard", json_result(make_dashboard(days=days)))]
    text = _text(_page(_report(routes + happy_routes())))
    assert "DESACUERDO (solo ECMWF)" in text
    assert "1 de 7 días con desacuerdo de lluvia" in text
    assert "Total: 2 días con desacuerdo de lluvia." in text  # both cities share the payload


def test_a_missing_model_is_stated() -> None:
    days = make_week(gfs_mm=None)
    routes = [(f"{PROD}/api/weather/dashboard", json_result(make_dashboard(days=days)))]
    assert "Falta el modelo GFS en todo el pronóstico." in _text(_page(_report(routes + happy_routes())))


def test_skipped_sections_say_why() -> None:
    text = _text(_page(_report(creds=False, skip_sources=True, skip_models=True)))
    assert "Omitida: falta --env-file" in text
    assert "Omitida: se omitió con --sin-fuentes" in text
    assert "Omitida: se omitió con --no-modelos" in text


# ------------------------------------------------------------------ safety


def test_untrusted_text_from_the_backend_is_escaped() -> None:
    evil = "<script>alert(1)</script>"
    dash = make_dashboard(reason=evil, station_name=evil)
    routes = [(f"{PROD}/api/weather/dashboard", json_result(dash))]
    page = _page(_report(routes + happy_routes()))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_no_secret_reaches_the_page() -> None:
    page = _page()
    for secret in ALL_SECRETS:
        assert secret not in page


# ------------------------------------------------------------------ states


def test_updating_adds_a_notice_and_an_automatic_refresh() -> None:
    page = _page(updating=True)
    assert '<meta http-equiv="refresh" content="3">' in page
    assert "Actualizando…" in _text(page)
    assert "disabled" in page  # the button cannot be pressed meanwhile


def test_idle_page_does_not_refresh_by_itself() -> None:
    page = _page()
    assert "http-equiv" not in page
    assert '<form method="post" action="/actualizar">' in page


def test_the_button_says_how_long_until_it_works_again() -> None:
    text = _text(_page(seconds_until_refresh=42))
    assert "Podés actualizar en 42 s" in text


def test_first_load_without_a_report_waits_and_refreshes() -> None:
    page = render_page(None, updating=True)
    assert "Actualizando…" in _text(page)
    assert '<meta http-equiv="refresh" content="3">' in page
    assert "Estado general" not in _text(page)


def test_a_failed_run_shows_an_escaped_message_and_keeps_the_last_report() -> None:
    page = _page(error="falló <b>algo</b>")
    assert "&lt;b&gt;algo&lt;/b&gt;" in page
    assert "<b>algo</b>" not in page
    assert "Estado general" in _text(page)
