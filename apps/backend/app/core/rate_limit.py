"""Shared slowapi Limiter, keyed by a client address that a caller cannot forge.

uvicorn runs behind the Render proxies with ``--forwarded-allow-ips='*'``, so ``request.client.host`` can
be the LEFTMOST ``X-Forwarded-For`` entry, which the caller controls. ``client_key`` therefore only trusts
``request.client.host`` when the request carries no forwarding header at all:

1. ``CF-Connecting-IP`` (written by Cloudflare with the real client address) when it is a valid IP.
2. The ``X-Forwarded-For`` entry ``rate_limit_xff_hops`` positions from the RIGHT, when it is a valid IP.
3. Forwarding headers exist but neither step produced a valid IP: ONE shared key (``"unverified"``).
   This fails CLOSED: every such request shares a single bucket instead of letting a caller pick its key.
4. No forwarding headers at all (health checks, direct hits, tests): ``request.client.host``.

Price of failing closed: ``RATE_LIMIT_XFF_HOPS`` must match the real proxy chain (confirm it with the
one-time ``rate_limit_key`` diagnostic after each infrastructure change). If the chain is shorter than
configured and ``CF-Connecting-IP`` is absent, all callers fall into the shared bucket and throttle each
other; the throttled WARNING and the ``step=unverified`` diagnostic show it.

IPv6 clients are keyed by their /64 prefix (``2001:db8:0:1::/64``): a single subscriber owns a whole /64,
so keying on the full address would let it rotate addresses to dodge the limit. IPv4-mapped IPv6 addresses
are keyed as the plain IPv4 address. The ``/64`` marker means an IPv6 key can never equal an IPv4 key.

The function never raises and never logs an address or a header value.
"""
from __future__ import annotations

import ipaddress
import logging
import threading
import time
from dataclasses import dataclass

from slowapi import Limiter
from starlette.requests import Request

from .config import settings

logger = logging.getLogger("skypulse.rate_limit")

_MAX_VALUE_LENGTH = 256          # longest header value / chain entry that is parsed at all
_WARNING_INTERVAL_SECONDS = 60.0  # at most one "invalid headers" warning per interval per process
_UNKNOWN = "unknown"
_UNVERIFIED = "unverified"        # shared key used when forwarding headers exist but are unusable
_IPV6_PREFIX_LENGTH = 64
_MAX_DIAGNOSTICS = 10             # distinct (cf_present, xff_entries, step) lines logged per process

_STEP_CF = "cf"
_STEP_XFF = "xff"
_STEP_CLIENT = "client"
_STEP_UNVERIFIED = "unverified"

_monotonic = time.monotonic  # indirection so tests can drive the warning throttle
_state_lock = threading.Lock()
_diagnostics_seen: set[tuple[bool, int, str]] = set()
_last_warning_at: float | None = None


@dataclass(frozen=True)
class _Resolution:
    key: str
    step: str
    cf_present: bool
    cf_invalid: bool
    xff_entries: int


def reset_diagnostics() -> None:
    """Forget the diagnostics already logged and the warning throttle (used by tests)."""
    global _last_warning_at
    with _state_lock:
        _diagnostics_seen.clear()
        _last_warning_at = None


def _address_key(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Key for an address: plain IPv4, IPv4-mapped IPv6 as IPv4, any other IPv6 as its /64 network."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network((address, _IPV6_PREFIX_LENGTH), strict=False))
    return str(address)


def _parse_ip(raw: str) -> str | None:
    """Return the key for ``raw`` or None if it is not exactly one valid IPv4/IPv6 address."""
    if len(raw) > _MAX_VALUE_LENGTH:
        return None
    candidate = raw.strip()
    if not candidate or "%" in candidate:  # empty, or an IPv6 scope id
        return None
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return _address_key(address)


def _client_host(request: Request) -> str:
    try:
        client = request.client
        host = client.host if client is not None else None
    except Exception:  # noqa: BLE001 - the key function must never raise
        return _UNKNOWN
    if not host:
        return _UNKNOWN
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host  # not an IP literal (for example a test client): keep it as is
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is None:
        return _address_key(address)
    return host


def _cf_candidate(request: Request) -> tuple[bool, str | None]:
    """Return (header present, valid IP or None). Repeated header lines are ambiguous, hence invalid."""
    values = request.headers.getlist("cf-connecting-ip")
    if not values:
        return False, None
    if len(values) != 1:
        return True, None
    return True, _parse_ip(values[0])


def _xff_candidate(request: Request, hops: int) -> tuple[int, str | None]:
    """Return (entry count, IP ``hops`` positions from the right or None).

    Only the last ``hops`` entries are split off, so padding the left of the header (client-controlled)
    can neither disable the lookup nor push the key back to the forgeable ``request.client.host``.
    """
    values = request.headers.getlist("x-forwarded-for")
    if not values:
        return 0, None
    chain = ",".join(values)
    entries = chain.count(",") + 1
    parts = chain.rsplit(",", hops)
    if len(parts) < hops:  # the chain has fewer entries than the configured hops
        return entries, None
    return entries, _parse_ip(parts[-hops])


def _resolve(request: Request) -> _Resolution:
    trust_cf = settings.rate_limit_trust_cf_header
    hops = settings.rate_limit_xff_hops
    cf_present, cf_ip = _cf_candidate(request) if trust_cf else (False, None)
    xff_entries, xff_ip = _xff_candidate(request, hops)
    if cf_ip is not None:
        return _Resolution(cf_ip, _STEP_CF, cf_present, False, xff_entries)
    if xff_ip is not None:
        return _Resolution(xff_ip, _STEP_XFF, cf_present, cf_present, xff_entries)
    if cf_present or xff_entries > 0:  # forwarding headers exist but none is usable: fail closed
        return _Resolution(_UNVERIFIED, _STEP_UNVERIFIED, cf_present, cf_present, xff_entries)
    return _Resolution(_client_host(request), _STEP_CLIENT, False, False, 0)


def _report(resolution: _Resolution) -> None:
    """Log the diagnostic (once per distinct combination, capped) and the throttled warning.

    Never includes an address or a header value.
    """
    global _last_warning_at
    combination = (resolution.cf_present, resolution.xff_entries, resolution.step)
    with _state_lock:
        first = combination not in _diagnostics_seen and len(_diagnostics_seen) < _MAX_DIAGNOSTICS
        if first:
            _diagnostics_seen.add(combination)
        warn = False
        if resolution.step == _STEP_UNVERIFIED:
            now = _monotonic()
            if _last_warning_at is None or now - _last_warning_at >= _WARNING_INTERVAL_SECONDS:
                _last_warning_at = now
                warn = True
    if first:
        logger.info(
            "rate_limit_key cf_header=%s xff_entries=%d step=%s",
            "yes" if resolution.cf_present else "no",
            resolution.xff_entries,
            resolution.step,
        )
    if warn:
        logger.warning(
            "rate_limit_key using the shared unverified key: forwarding headers present but unusable "
            "(cf_header_invalid=%s xff_entries=%d hops=%d)",
            "yes" if resolution.cf_invalid else "no",
            resolution.xff_entries,
            settings.rate_limit_xff_hops,
        )


def client_key(request: Request) -> str:
    """Key the rate limit by the real client address; see the module docstring for the order."""
    try:
        resolution = _resolve(request)
    except Exception:  # noqa: BLE001 - never a 500; unreadable headers may hide forwarding ones: fail closed
        return _UNVERIFIED
    try:
        _report(resolution)
    except Exception:  # noqa: BLE001 - logging must never break a request
        pass
    return resolution.key


limiter = Limiter(key_func=client_key)
