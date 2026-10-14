"""Credentials from the process environment and a minimal Upstash REST client (POST, command in the body).

`monitor_core` is deliberately GET-only; this tool has to write, so it has its own small client. It is the
only place in this tool that touches the network. Errors are reduced to fixed codes: exception messages
(urllib) often embed the full URL, and the URL host is a secret here.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from alertas_vaciar_core.limpieza import UpstashError

URL_VAR = "UPSTASH_REDIS_REST_URL"
TOKEN_VAR = "UPSTASH_REDIS_REST_TOKEN"
TIMEOUT_S = 20.0
MAX_RESPONSE_BYTES = 4_000_000
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class CredentialsError(ValueError):
    """Missing or malformed credentials. The message names the variables, never their values."""


@dataclass(frozen=True)
class Credentials:
    url: str = field(repr=False)
    token: str = field(repr=False)


def credentials_from_env(environ: Mapping[str, str]) -> Credentials:
    """Read the two Upstash variables from `environ` (the process environment; no file is ever opened)."""
    url = (environ.get(URL_VAR) or "").strip()
    token = (environ.get(TOKEN_VAR) or "").strip()
    missing = [
        name for name, value in ((URL_VAR, url), (TOKEN_VAR, token)) if not value
    ]
    if missing:
        raise CredentialsError(
            f"faltan variables de entorno: {', '.join(missing)} "
            "(se leen del entorno del proceso, no de un archivo .env)"
        )
    parts = urlparse(url)
    host = parts.hostname
    secure = parts.scheme == "https"
    local_http = parts.scheme == "http" and host in _LOOPBACK_HOSTS
    if not host or not (secure or local_http):
        raise CredentialsError(f"{URL_VAR} no es una URL https válida")
    return Credentials(url=url, token=token)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: it could carry the Authorization header to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _error_name(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, BaseException):
        return type(exc.reason).__name__
    return type(exc).__name__


class UrllibCommander:
    """`POST {url}/` with the command as a JSON array in the body. Failures raise `UpstashError` with a fixed code."""

    def __init__(self, credentials: Credentials, timeout: float = TIMEOUT_S) -> None:
        self._endpoint = credentials.url.rstrip("/") + "/"
        self._token = credentials.token
        self._timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    def __repr__(self) -> str:
        return "UrllibCommander(url=<hidden>, token=<hidden>)"

    def run(self, *command: str) -> Any:
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(list(command)).encode("utf-8"),
            method="POST",
        )
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as exc:
            raise UpstashError(f"HTTP {exc.code}") from None
        except Exception as exc:  # noqa: BLE001 (any transport failure becomes a fixed code)
            raise UpstashError(f"sin respuesta ({_error_name(exc)})") from None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise UpstashError("respuesta no es JSON") from None
        if (
            not isinstance(payload, dict)
            or "error" in payload
            or "result" not in payload
        ):
            raise UpstashError("respuesta inesperada")
        return payload["result"]
