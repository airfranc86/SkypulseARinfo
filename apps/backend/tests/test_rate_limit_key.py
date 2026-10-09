"""Unit tests for the rate-limit key (`client_key`): spoof-resistant client identification."""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.core import rate_limit
from app.core.config import Settings, settings
from app.core.rate_limit import client_key, reset_diagnostics

# Documentation-range addresses (RFC 5737 / RFC 3849): never real clients.
FAKE = "6.6.6.6"            # value forged by the client (leftmost X-Forwarded-For entry)
REAL = "203.0.113.9"        # the real client, as seen by Cloudflare
CF_EDGE = "162.158.0.1"     # Cloudflare edge address
INTERNAL = "10.0.0.5"       # Render internal hop
CLIENT_HOST = "198.51.100.7"  # what ASGI reports as request.client.host
CHAIN = f"{FAKE}, {REAL}, {CF_EDGE}, {INTERNAL}"
UNVERIFIED = "unverified"  # shared key when forwarding headers exist but none is usable (fail closed)

LOGGER_NAME = "skypulse.rate_limit"


def make_request(
    headers: list[tuple[str, str]] | dict[str, str] | None = None,
    client: tuple[str, int] | None = (CLIENT_HOST, 5555),
) -> Request:
    items = list(headers.items()) if isinstance(headers, dict) else list(headers or [])
    raw = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in items]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": raw,
        "client": client,
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_cf_header", True)
    monkeypatch.setattr(settings, "rate_limit_xff_hops", 3)
    reset_diagnostics()
    yield
    reset_diagnostics()


# ---------------------------------------------------------------------------
# Step 1: CF-Connecting-IP
# ---------------------------------------------------------------------------


def test_cf_header_wins_over_forged_xff():
    request = make_request({"CF-Connecting-IP": REAL, "X-Forwarded-For": CHAIN})
    assert client_key(request) == REAL


def test_cf_header_ipv6_is_keyed_by_its_slash_64_prefix():
    request = make_request({"CF-Connecting-IP": "2001:0DB8:0:1:0:0:0:1"})
    assert client_key(request) == "2001:db8:0:1::/64"


def test_cf_header_ipv4_mapped_ipv6_normalizes_to_ipv4():
    request = make_request({"CF-Connecting-IP": "::ffff:203.0.113.9"})
    assert client_key(request) == REAL


def test_cf_header_whitespace_is_trimmed():
    request = make_request({"CF-Connecting-IP": f"   {REAL}\t "})
    assert client_key(request) == REAL


def test_cf_header_name_is_case_insensitive():
    request = make_request({"cf-connecting-ip": REAL})
    assert client_key(request) == REAL


@pytest.mark.parametrize(
    "value",
    [
        "garbage",
        "",
        "   ",
        "1.1.1.1, 2.2.2.2",       # comma list
        "1.1.1.1 2.2.2.2",        # inner whitespace
        "example.com",            # hostname
        "999.1.1.1",              # out-of-range octet
        "1.1.1.1:8080",           # with port
        "fe80::1%eth0",           # scope id
        "1.1.1.1\x00",            # control character
        "a" * 300,
    ],
)
def test_invalid_cf_header_falls_through_to_xff(value):
    request = make_request({"CF-Connecting-IP": value, "X-Forwarded-For": CHAIN})
    assert client_key(request) == REAL


@pytest.mark.parametrize("value", ["garbage", "1.1.1.1, 2.2.2.2", "example.com", ""])
def test_invalid_cf_header_without_xff_fails_closed_to_the_shared_key(value):
    request = make_request({"CF-Connecting-IP": value})
    assert client_key(request) == UNVERIFIED


def test_cf_header_over_length_is_ignored_even_if_padding_is_whitespace():
    padded = REAL + " " * (257 - len(REAL))
    assert len(padded) == 257
    request = make_request({"CF-Connecting-IP": padded, "X-Forwarded-For": CHAIN})
    # Ignored before parsing: the key comes from the XFF hop, not from the padded value.
    assert client_key(request) == REAL
    request = make_request({"CF-Connecting-IP": padded})
    assert client_key(request) == UNVERIFIED


def test_cf_header_exactly_at_the_length_cap_is_accepted():
    padded = REAL + " " * (256 - len(REAL))
    assert len(padded) == 256
    assert client_key(make_request({"CF-Connecting-IP": padded})) == REAL


def test_repeated_cf_header_lines_are_ambiguous_and_ignored():
    request = make_request(
        [("CF-Connecting-IP", FAKE), ("CF-Connecting-IP", REAL), ("X-Forwarded-For", CHAIN)]
    )
    assert client_key(request) == REAL  # from the XFF hop, not from either CF line


def test_trust_flag_off_ignores_cf_header(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_cf_header", False)
    request = make_request({"CF-Connecting-IP": FAKE, "X-Forwarded-For": CHAIN})
    assert client_key(request) == REAL


def test_trust_flag_off_without_xff_uses_client_host(monkeypatch):
    # An ignored CF header is not a usable forwarding header: behave as if it were absent.
    monkeypatch.setattr(settings, "rate_limit_trust_cf_header", False)
    request = make_request({"CF-Connecting-IP": FAKE})
    assert client_key(request) == CLIENT_HOST


# ---------------------------------------------------------------------------
# Step 2: X-Forwarded-For counted from the right
# ---------------------------------------------------------------------------


def test_forged_xff_alone_with_default_hops_yields_the_real_client():
    request = make_request({"X-Forwarded-For": CHAIN})
    assert client_key(request) == REAL


@pytest.mark.parametrize(
    ("hops", "expected"),
    [(1, INTERNAL), (2, CF_EDGE), (3, REAL), (4, FAKE)],
)
def test_hops_are_counted_from_the_right(monkeypatch, hops, expected):
    monkeypatch.setattr(settings, "rate_limit_xff_hops", hops)
    request = make_request({"X-Forwarded-For": CHAIN})
    assert client_key(request) == expected


def test_chain_shorter_than_hops_fails_closed_to_the_shared_key():
    request = make_request({"X-Forwarded-For": f"{FAKE}, {REAL}"})
    assert client_key(request) == UNVERIFIED


def test_forged_short_chain_never_becomes_the_key_even_if_client_host_mirrors_it():
    # uvicorn with a wildcard for forwarded-allow-ips reports the forged leftmost entry as client.host.
    request = make_request({"X-Forwarded-For": FAKE}, client=(FAKE, 1))
    assert client_key(request) == UNVERIFIED


def test_unusable_headers_share_one_key_whatever_the_forged_values():
    keys = {
        client_key(make_request({"X-Forwarded-For": f"9.9.9.{i}"}, client=(f"9.9.9.{i}", 1)))
        for i in range(1, 6)
    }
    assert keys == {UNVERIFIED}


def test_request_client_host_is_not_trusted_ahead_of_the_chain():
    # uvicorn with --forwarded-allow-ips='*' reports the forged leftmost entry as client.host.
    request = make_request({"X-Forwarded-For": CHAIN}, client=(FAKE, 1))
    assert client_key(request) == REAL


def test_xff_whitespace_is_trimmed():
    request = make_request({"X-Forwarded-For": f" {FAKE} ,  {REAL}\t,{CF_EDGE} ,   {INTERNAL}  "})
    assert client_key(request) == REAL


def test_xff_selected_entry_ipv6_is_keyed_by_its_slash_64_prefix():
    request = make_request({"X-Forwarded-For": f"{FAKE}, 2001:0DB8:0:7::0001, {CF_EDGE}, {INTERNAL}"})
    assert client_key(request) == "2001:db8:0:7::/64"


@pytest.mark.parametrize(
    "selected",
    ["garbage", "", "example.com", "999.1.1.1", "1.1.1.1:80", "a" * 300, "1.1.1.1 2.2.2.2"],
)
def test_invalid_selected_xff_entry_fails_closed_to_the_shared_key(selected):
    request = make_request({"X-Forwarded-For": f"{FAKE}, {selected}, {CF_EDGE}, {INTERNAL}"})
    assert client_key(request) == UNVERIFIED


def test_xff_padding_on_the_left_does_not_disable_the_hop_lookup():
    # A client cannot force the fallback to client.host (a forgeable value) by padding the header.
    padding = "x" * 20_000
    request = make_request({"X-Forwarded-For": f"{padding}, {REAL}, {CF_EDGE}, {INTERNAL}"}, client=(FAKE, 1))
    assert client_key(request) == REAL


def test_repeated_xff_header_lines_are_combined_in_order():
    request = make_request(
        [("X-Forwarded-For", f"{FAKE}, {REAL}"), ("X-Forwarded-For", f"{CF_EDGE}, {INTERNAL}")]
    )
    assert client_key(request) == REAL


# ---------------------------------------------------------------------------
# IPv6 is keyed by /64 so rotating addresses inside one prefix cannot dodge the limit
# ---------------------------------------------------------------------------


def test_addresses_in_the_same_slash_64_share_a_key():
    a = client_key(make_request({"CF-Connecting-IP": "2001:db8:0:1::1"}))
    b = client_key(make_request({"CF-Connecting-IP": "2001:db8:0:1:ffff:ffff:ffff:ffff"}))
    assert a == b == "2001:db8:0:1::/64"


def test_addresses_in_different_slash_64_prefixes_get_different_keys():
    a = client_key(make_request({"CF-Connecting-IP": "2001:db8:0:1::1"}))
    b = client_key(make_request({"CF-Connecting-IP": "2001:db8:0:2::1"}))
    assert a != b


def test_xff_hop_in_the_same_slash_64_shares_a_key():
    chain_a = f"{FAKE}, 2001:db8:0:9::1, {CF_EDGE}, {INTERNAL}"
    chain_b = f"{FAKE}, 2001:db8:0:9::dead:beef, {CF_EDGE}, {INTERNAL}"
    assert client_key(make_request({"X-Forwarded-For": chain_a})) == client_key(
        make_request({"X-Forwarded-For": chain_b})
    )


def test_ipv4_mapped_ipv6_keeps_the_plain_ipv4_key():
    assert client_key(make_request({"CF-Connecting-IP": "::ffff:203.0.113.9"})) == REAL


def test_an_ipv6_key_can_never_collide_with_an_ipv4_key():
    v6 = client_key(make_request({"CF-Connecting-IP": "2001:db8::1"}))
    v4 = client_key(make_request({"CF-Connecting-IP": REAL}))
    assert v6.endswith("/64")
    assert "/" not in v4
    assert v6 != v4


def test_ipv6_client_host_fallback_is_keyed_by_slash_64():
    request = make_request(client=("2001:db8:0:5::77", 1))
    assert client_key(request) == "2001:db8:0:5::/64"


def test_non_ip_client_host_is_kept_as_is():
    assert client_key(make_request(client=("testclient", 1))) == "testclient"


# ---------------------------------------------------------------------------
# Step 3: last resort and robustness
# ---------------------------------------------------------------------------


def test_no_headers_uses_client_host():
    assert client_key(make_request()) == CLIENT_HOST


def test_no_client_and_no_headers_yields_unknown():
    assert client_key(make_request(client=None)) == "unknown"


def test_returns_a_string_for_every_path():
    for request in (
        make_request({"CF-Connecting-IP": REAL}),
        make_request({"X-Forwarded-For": CHAIN}),
        make_request(),
        make_request(client=None),
    ):
        assert isinstance(client_key(request), str)


class _BrokenHeaders:
    client = SimpleNamespace(host=CLIENT_HOST, port=1)

    @property
    def headers(self):
        raise RuntimeError("boom")


class _Broken:
    @property
    def headers(self):
        raise RuntimeError("boom")

    @property
    def client(self):
        raise RuntimeError("boom")


def test_exception_while_reading_headers_fails_closed():
    # Unreadable headers might hide forwarding headers: never fall back to the forgeable client host.
    assert client_key(_BrokenHeaders()) == UNVERIFIED  # type: ignore[arg-type]


def test_exception_everywhere_still_returns_a_string():
    assert client_key(_Broken()) == UNVERIFIED  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_defaults():
    fresh = Settings(_env_file=None)
    assert fresh.rate_limit_trust_cf_header is True
    assert fresh.rate_limit_xff_hops == 3


@pytest.mark.parametrize("bad", [0, -1])
def test_settings_reject_hops_below_one(bad):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rate_limit_xff_hops=bad)


@pytest.mark.parametrize(("value", "valid"), [(1, True), (16, True), (17, False)])
def test_settings_hops_upper_bound(value, valid):
    if valid:
        assert Settings(_env_file=None, rate_limit_xff_hops=value).rate_limit_xff_hops == value
    else:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, rate_limit_xff_hops=value)


def test_settings_read_the_environment(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_XFF_HOPS", "2")
    monkeypatch.setenv("RATE_LIMIT_TRUST_CF_HEADER", "false")
    fresh = Settings(_env_file=None)
    assert fresh.rate_limit_xff_hops == 2
    assert fresh.rate_limit_trust_cf_header is False


# ---------------------------------------------------------------------------
# One-time diagnostic log (never an IP) and throttled warning
# ---------------------------------------------------------------------------

ALL_SECRETS = (REAL, FAKE, CF_EDGE, INTERNAL, CLIENT_HOST)


def _records(caplog, level=None):
    return [
        r for r in caplog.records
        if r.name == LOGGER_NAME and (level is None or r.levelno == level)
    ]


def _assert_no_ip(records):
    for record in records:
        text = record.getMessage() + " " + str(record.args)
        for secret in ALL_SECRETS:
            assert secret not in text


def test_diagnostic_is_logged_once_and_contains_no_ip(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    request = make_request({"CF-Connecting-IP": REAL, "X-Forwarded-For": CHAIN})
    for _ in range(5):
        client_key(request)
    info = _records(caplog, logging.INFO)
    assert len(info) == 1
    message = info[0].getMessage()
    assert "rate_limit_key" in message
    assert "cf_header=yes" in message
    assert "xff_entries=4" in message
    assert "step=cf" in message
    _assert_no_ip(info)


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"X-Forwarded-For": CHAIN}, ("cf_header=no", "xff_entries=4", "step=xff")),
        ({}, ("cf_header=no", "xff_entries=0", "step=client")),
    ],
)
def test_diagnostic_reports_which_step_produced_the_key(caplog, headers, expected):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    client_key(make_request(headers))
    message = _records(caplog, logging.INFO)[0].getMessage()
    for fragment in expected:
        assert fragment in message
    _assert_no_ip(_records(caplog))


def test_header_less_request_does_not_consume_the_diagnostic_of_a_real_one(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    client_key(make_request())  # a health check: no forwarding headers
    client_key(make_request({"CF-Connecting-IP": REAL, "X-Forwarded-For": CHAIN}))
    messages = [r.getMessage() for r in _records(caplog, logging.INFO)]
    assert len(messages) == 2
    assert "step=client" in messages[0]
    assert "step=cf" in messages[1] and "xff_entries=4" in messages[1]
    _assert_no_ip(_records(caplog))


def test_each_distinct_combination_is_logged_once(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    requests = [
        make_request(),
        make_request({"CF-Connecting-IP": REAL}),
        make_request({"CF-Connecting-IP": REAL}),                # same combination as above
        make_request({"CF-Connecting-IP": FAKE}),                # same combination again
        make_request({"X-Forwarded-For": CHAIN}),
        make_request({"X-Forwarded-For": f"{FAKE}, {REAL}"}),    # unverified
    ]
    for request in requests:
        client_key(request)
    messages = [r.getMessage() for r in _records(caplog, logging.INFO)]
    assert len(messages) == 4
    assert any("step=unverified" in m and "xff_entries=2" in m for m in messages)


def test_diagnostic_combinations_are_capped_per_process(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    for entries in range(1, 16):  # 15 distinct xff_entries values -> 15 distinct combinations
        client_key(make_request({"X-Forwarded-For": ", ".join(["9.9.9.9"] * entries)}))
    assert len(_records(caplog, logging.INFO)) == 10


def test_diagnostic_can_be_reset_for_tests(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    request = make_request({"CF-Connecting-IP": REAL})
    client_key(request)
    reset_diagnostics()
    client_key(request)
    assert len(_records(caplog, logging.INFO)) == 2


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_warning_is_throttled_when_headers_are_invalid(caplog, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(rate_limit, "_monotonic", clock)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    bad = make_request({"CF-Connecting-IP": "garbage", "X-Forwarded-For": "nonsense"})
    for _ in range(10):
        assert client_key(bad) == UNVERIFIED
    assert len(_records(caplog, logging.WARNING)) == 1
    clock.now += 30
    client_key(bad)
    assert len(_records(caplog, logging.WARNING)) == 1
    clock.now += 31  # 61 s after the first warning
    client_key(bad)
    assert len(_records(caplog, logging.WARNING)) == 2
    _assert_no_ip(_records(caplog))


def test_warning_when_xff_is_present_but_too_short(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    client_key(make_request({"X-Forwarded-For": f"{FAKE}, {REAL}"}))
    warnings = _records(caplog, logging.WARNING)
    assert len(warnings) == 1
    _assert_no_ip(warnings)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"CF-Connecting-IP": REAL},
        {"X-Forwarded-For": CHAIN},
        {"CF-Connecting-IP": REAL, "X-Forwarded-For": "garbage"},  # key came from the CF header
    ],
)
def test_no_warning_when_a_valid_step_produced_the_key_or_no_headers_exist(caplog, headers):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    client_key(make_request(headers))
    assert _records(caplog, logging.WARNING) == []


def test_no_warning_for_a_cf_header_that_is_ignored_on_purpose(caplog, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_trust_cf_header", False)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    client_key(make_request({"CF-Connecting-IP": "garbage"}))
    assert _records(caplog, logging.WARNING) == []


def test_same_header_shape_with_a_different_outcome_is_logged_separately(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    client_key(make_request({"X-Forwarded-For": CHAIN}))                                        # step=xff
    client_key(make_request({"X-Forwarded-For": f"{FAKE}, garbage, {CF_EDGE}, {INTERNAL}"}))    # step=unverified
    steps = [r.getMessage().rsplit("step=", 1)[1] for r in _records(caplog, logging.INFO)]
    assert steps == ["xff", "unverified"]


# ---------------------------------------------------------------------------
# The shared fail-closed key is public (the Open-Meteo budget gives it a larger share)
# ---------------------------------------------------------------------------

def test_the_shared_key_is_a_public_constant_with_the_value_client_key_returns():
    from app.core.rate_limit import UNVERIFIED_CLIENT_KEY

    assert UNVERIFIED_CLIENT_KEY == UNVERIFIED == "unverified"
    assert client_key(make_request({"CF-Connecting-IP": "garbage"})) == UNVERIFIED_CLIENT_KEY


def test_a_request_without_client_info_keeps_the_ordinary_unknown_key():
    from app.core.rate_limit import UNVERIFIED_CLIENT_KEY

    key = client_key(make_request(client=None))

    assert key == "unknown"
    assert key != UNVERIFIED_CLIENT_KEY
