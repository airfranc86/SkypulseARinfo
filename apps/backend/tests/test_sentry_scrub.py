"""Sentry never receives the URL of a push service (FRA-355, PR5c correction round).

The path of a push endpoint (`https://fcm.googleapis.com/fcm/send/<token>`) is a secret: whoever has it can post to that
person's browser. The default integrations of Sentry record every outgoing HTTP request as a breadcrumb and as a span,
URL included. `app.main` therefore installs three hooks (`before_breadcrumb`, `before_send`, `before_send_transaction`)
that drop or blank everything that mentions a push-service host, using the SAME host list as the subscription's anti-SSRF
check (`suscripcion.es_host_de_push`). The tokens below are made up: no real endpoint appears in this repository.
"""
from __future__ import annotations

import copy
import json
import logging
import time

import pytest

from app import main
from app.services.alertas import suscripcion as svc

pytestmark = pytest.mark.unit

TOKEN = "FAKE-TOKEN-0123456789:APA91bFAKE"
URL_FCM = f"https://fcm.googleapis.com/fcm/send/{TOKEN}"
URL_MOZILLA = f"https://updates.push.services.mozilla.com/wpush/v2/{TOKEN}"
URL_APPLE = f"https://web.push.apple.com/{TOKEN}"
URL_WINDOWS = f"https://wns2-par02p.notify.windows.com/?token={TOKEN}"
URL_OPEN_METEO = "https://api.open-meteo.com/v1/forecast?latitude=-31.4&longitude=-64.2"


def migaja(url: str, **extra) -> dict:
    return {"type": "http", "category": "httplib", "data": {"url": url, "method": "POST", "status_code": 201}, **extra}


# --- before_breadcrumb ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("url", [URL_FCM, URL_MOZILLA, URL_APPLE, URL_WINDOWS])
def test_a_breadcrumb_of_a_request_to_a_push_service_is_dropped(url: str) -> None:
    assert main._scrub_breadcrumb(migaja(url), {}) is None


def test_a_breadcrumb_that_mentions_a_push_host_anywhere_is_dropped() -> None:
    assert main._scrub_breadcrumb({"category": "log", "message": f"POST {URL_FCM} -> 201", "data": {}}, {}) is None
    assert main._scrub_breadcrumb({"category": "x", "data": {"anidado": [{"url": URL_MOZILLA}]}}, {}) is None


def test_a_breadcrumb_of_another_host_is_kept_untouched() -> None:
    original = migaja(URL_OPEN_METEO)
    assert main._scrub_breadcrumb(copy.deepcopy(original), {}) == original
    assert main._scrub_breadcrumb({"category": "query", "message": "SELECT 1"}, {}) == {
        "category": "query",
        "message": "SELECT 1",
    }


def test_a_lookalike_host_is_not_a_push_host() -> None:
    parecida = migaja("https://evilpush.apple.com/x")
    assert main._scrub_breadcrumb(copy.deepcopy(parecida), {}) == parecida


# --- before_send_transaction ---------------------------------------------------------------------------------------------


def transaccion() -> dict:
    return {
        "type": "transaction",
        "transaction": "POST /api/alertas/evaluar",
        "request": {"url": "https://skypulse-api.example/api/alertas/evaluar", "method": "POST"},
        "breadcrumbs": {"values": [migaja(URL_FCM), migaja(URL_OPEN_METEO)]},
        "spans": [
            {"op": "http.client", "description": f"POST {URL_FCM}", "data": {"url": URL_FCM, "http.query": TOKEN, "http.method": "POST"}},
            {"op": "http.client", "description": f"GET {URL_OPEN_METEO}", "data": {"url": URL_OPEN_METEO}},
            {"op": "db.redis", "description": "SET alertas:lock:evaluar"},
        ],
    }


def test_a_transaction_loses_every_trace_of_the_push_url_and_keeps_the_rest() -> None:
    limpia = main._scrub_transaction(transaccion(), {})
    assert limpia is not None
    texto = json.dumps(limpia)
    for rastro in (TOKEN, "fcm.googleapis.com", "/fcm/send"):
        assert rastro not in texto, rastro
    # the span is kept (its timing is useful) but blank; the others are untouched
    assert [s["op"] for s in limpia["spans"]] == ["http.client", "http.client", "db.redis"]
    assert limpia["spans"][1] == transaccion()["spans"][1] and limpia["spans"][2] == transaccion()["spans"][2]
    assert limpia["breadcrumbs"]["values"] == [migaja(URL_OPEN_METEO)]  # the push breadcrumb is gone
    assert limpia["request"] == transaccion()["request"] and limpia["transaction"] == "POST /api/alertas/evaluar"


@pytest.mark.parametrize("url", [URL_FCM, URL_MOZILLA, URL_APPLE, URL_WINDOWS])
def test_the_request_url_and_the_span_fields_are_removed_for_every_push_host(url: str) -> None:
    evento = transaccion()
    evento["request"]["url"] = url
    evento["spans"][0] = {"op": "http.client", "description": f"POST {url}", "data": {"url": url, "http.fragment": url}}
    limpio = json.dumps(main._scrub_transaction(evento, {}))
    assert TOKEN not in limpio


def test_the_scrubbing_does_not_mutate_the_event_it_receives_beyond_what_sentry_expects() -> None:
    evento = transaccion()
    resultado = main._scrub_transaction(evento, {})
    assert resultado is not None and resultado["type"] == "transaction"


# --- before_send (error events) --------------------------------------------------------------------------------------------


def test_an_error_event_loses_the_breadcrumbs_and_the_messages_that_carry_the_push_url() -> None:
    evento = {
        "level": "error",
        "message": "boom",
        "breadcrumbs": {"values": [migaja(URL_FCM), {"category": "log", "message": "hola"}]},
        "request": {"url": URL_FCM, "method": "POST"},
        "exception": {
            "values": [
                {
                    "type": "ConnectionError",
                    "value": f"HTTPSConnectionPool(host='fcm.googleapis.com', port=443): Max retries exceeded with url: /fcm/send/{TOKEN}",
                }
            ]
        },
    }
    limpio = main._scrub_event(evento, {})
    assert limpio is not None
    texto = json.dumps(limpio)
    assert TOKEN not in texto and "fcm.googleapis.com" not in texto
    assert limpio["breadcrumbs"]["values"] == [{"category": "log", "message": "hola"}]
    assert limpio["exception"]["values"][0]["type"] == "ConnectionError"  # the kind of error is still reported
    assert limpio["message"] == "boom"


def test_an_error_event_without_any_push_url_passes_unchanged() -> None:
    evento = {"level": "error", "message": "boom", "breadcrumbs": {"values": [migaja(URL_OPEN_METEO)]}}
    assert main._scrub_event(copy.deepcopy(evento), {}) == evento


# --- one host list for the anti-SSRF check and for Sentry -------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com", "wns2-par02p.notify.windows.com",
     "evilpush.apple.com", "api.open-meteo.com", "fcm.googleapis.com.evil.example"],
)
def test_the_scrubbing_uses_the_host_list_of_the_subscription_check(host: str) -> None:
    descartada = main._scrub_breadcrumb(migaja(f"https://{host}/x/{TOKEN}"), {}) is None
    # The match is a linear substring test (no regex): it may only OVER-filter. Every real push host is dropped; the
    # lookalike `fcm.googleapis.com.evil.example` contains a push host, so it is dropped too (it used to be kept).
    esperado = svc.es_host_de_push(host) or host == "fcm.googleapis.com.evil.example"
    assert descartada is esperado
    assert descartada is svc.menciona_host_de_push(f"https://{host}/x/{TOKEN}")


def test_the_scrubbing_follows_the_shared_list_not_a_copy_of_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_HOSTS_EXACTOS", frozenset({"solo-este.example"}))
    monkeypatch.setattr(svc, "_SUFIJOS", ())
    assert main._scrub_breadcrumb(migaja("https://solo-este.example/x"), {}) is None
    assert main._scrub_breadcrumb(migaja(URL_FCM), {}) is not None


# --- initialization --------------------------------------------------------------------------------------------------------


@pytest.fixture
def sdk_falso(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    llamadas: list[dict] = []
    monkeypatch.setattr(main.sentry_sdk, "init", lambda **kwargs: llamadas.append(kwargs))
    return llamadas


@pytest.mark.parametrize(("dsn", "entorno"), [(None, "prod"), ("", "prod"), ("https://k@o.ingest.sentry.io/1", "dev"), ("https://k@o.ingest.sentry.io/1", None)])
def test_sentry_is_not_initialized_without_a_dsn_or_outside_production(sdk_falso, dsn, entorno) -> None:
    assert main._init_sentry(dsn, entorno) is False
    assert sdk_falso == []


def test_in_this_environment_sentry_is_not_active() -> None:
    assert main.sentry_sdk.get_client().is_active() is False


def test_sentry_in_production_installs_the_three_hooks_and_keeps_the_privacy_options(sdk_falso) -> None:
    assert main._init_sentry("https://k@o.ingest.sentry.io/1", "prod") is True
    (opciones,) = sdk_falso
    assert opciones["before_breadcrumb"] is main._scrub_breadcrumb
    assert opciones["before_send"] is main._scrub_event
    assert opciones["before_send_transaction"] is main._scrub_transaction
    assert opciones["trace_propagation_targets"] == []  # no sentry-trace / baggage headers to any third party
    assert opciones["send_default_pii"] is False
    assert opciones["include_local_variables"] is False
    assert opciones["max_request_body_size"] == "never"
    assert opciones["environment"] == "prod" and opciones["dsn"] == "https://k@o.ingest.sentry.io/1"


# --- ReDoS: the hooks run on UNTRUNCATED text, so they must be linear ------------------------------------------------------

LIMITE_SEGUNDOS = 0.5  # generous: the old regex took ~4 s for 16 KB and ~40 s for 50 KB of a dotless path


def tarda_menos_de_medio_segundo(funcion, *args) -> None:
    inicio = time.perf_counter()
    funcion(*args)
    assert time.perf_counter() - inicio < LIMITE_SEGUNDOS


@pytest.mark.parametrize("largo", [20_000, 200_000], ids=["20KB", "200KB"])
def test_a_huge_dotless_string_does_not_block_any_hook(largo: int) -> None:
    ruta = "/" + "a" * largo  # what an unauthenticated `GET /aaaa...` puts in the path
    tarda_menos_de_medio_segundo(main._scrub_breadcrumb, {"category": "log", "message": f"GET {ruta}", "data": {"url": ruta}}, {})
    transaccion_larga = {
        "type": "transaction",
        "transaction": f"GET {ruta}",
        "request": {"url": f"https://skypulse.example{ruta}", "method": "GET"},
        "spans": [{"op": "http.server", "description": f"GET {ruta}", "data": {"url": ruta}}],
        "breadcrumbs": {"values": [{"category": "log", "message": f"GET {ruta}"}]},
    }
    tarda_menos_de_medio_segundo(main._scrub_transaction, transaccion_larga, {})
    evento_largo = {
        "message": ruta,
        "request": {"url": ruta},
        "exception": {"values": [{"type": "X", "value": ruta}]},
        "breadcrumbs": {"values": [{"category": "log", "message": ruta}]},
    }
    tarda_menos_de_medio_segundo(main._scrub_event, evento_largo, {})


def test_a_long_string_made_of_dots_and_labels_is_linear_too() -> None:
    raro = ("a." * 100_000) + "b"
    tarda_menos_de_medio_segundo(main._scrub_breadcrumb, {"message": raro}, {})
    tarda_menos_de_medio_segundo(main._scrub_event, {"message": raro}, {})


def test_the_match_function_of_the_subscription_module_is_linear_as_well() -> None:
    tarda_menos_de_medio_segundo(svc.menciona_host_de_push, "a" * 1_000_000)


@pytest.mark.parametrize(
    "texto",
    [
        "https://fcm.googleapis.com/fcm/send/X",
        "https://FCM.GOOGLEAPIS.COM/fcm/send/X",
        "https://fcm.googleapis.com:443/fcm/send/X",
        "https://fcm.googleapis.com./fcm/send/X",
        "https://fcm.googleapis.com@evil.example/x",
        "https://user:pw@updates.push.services.mozilla.com/wpush/v2/X",
        "WEB.PUSH.APPLE.COM",
        "host='wns2-par02p.notify.windows.com', port=443",
        "xx" * 5000 + "fcm.googleapis.com" + "yy" * 5000,
    ],
)
def test_no_spelling_of_a_push_host_gets_past_the_match(texto: str) -> None:
    assert svc.menciona_host_de_push(texto) is True
    assert main._scrub_breadcrumb({"message": texto}, {}) is None


@pytest.mark.parametrize("texto", ["", "api.open-meteo.com", "evilpush.apple.com", "GET /api/alertas/evaluar", "a" * 5000])
def test_other_text_is_not_flagged(texto: str) -> None:
    assert svc.menciona_host_de_push(texto) is False


# --- the breadcrumb hook is never allowed to fail (the SDK does not guard it) ----------------------------------------------


def test_a_failure_inside_the_breadcrumb_hook_drops_the_breadcrumb_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    def rompe(valor):
        raise RuntimeError("bug en el filtro")

    monkeypatch.setattr(main, "_menciona_host_de_push", rompe)
    assert main._scrub_breadcrumb({"message": "hola"}, {}) is None


# --- tuples are walked like lists ---------------------------------------------------------------------------------------------


def test_strings_inside_tuples_are_scrubbed_and_stay_tuples() -> None:
    limpio = main._sin_hosts_de_push(("ok", URL_FCM, {"u": (URL_MOZILLA, "bien")}))
    assert isinstance(limpio, tuple)
    texto = json.dumps(limpio)
    assert TOKEN not in texto and "fcm.googleapis.com" not in texto
    assert limpio[0] == "ok" and limpio[2]["u"][1] == "bien"


def test_a_push_url_inside_a_tuple_of_an_event_is_removed() -> None:
    evento = {"extra": {"args": (URL_FCM, 3)}}
    assert TOKEN not in json.dumps(main._scrub_event(evento, {}))


# --- httpx must not log the coordinates of the subscribed zones -------------------------------------------------------------


def test_setup_logging_keeps_httpx_quiet_below_warning() -> None:
    httpx_logger, raiz = logging.getLogger("httpx"), logging.getLogger()
    nivel_httpx, nivel_raiz, handlers = httpx_logger.level, raiz.level, list(raiz.handlers)
    try:
        httpx_logger.setLevel(logging.DEBUG)
        main.setup_logging()
        assert httpx_logger.level == logging.WARNING  # its INFO lines carry `latitude=...&longitude=...`
    finally:
        httpx_logger.setLevel(nivel_httpx)
        raiz.handlers[:] = handlers
        raiz.setLevel(nivel_raiz)
