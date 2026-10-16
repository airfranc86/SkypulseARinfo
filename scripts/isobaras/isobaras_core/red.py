"""The only module that talks to the network (standard library only, no dependency)."""

from __future__ import annotations

import time
import urllib.error
import urllib.request

TIMEOUT_S = 30
INTENTOS = 3
ESPERA_S = 2  # base wait between attempts; multiplied by the attempt number
MAX_SIN_RANGO = 5_000_000  # an `.idx` is ~40 KB: anything bigger than this without a range is not what we asked for
MAX_RANGO_ABIERTO = 50_000_000
_USER_AGENT = "skypulse-isobaras (+https://github.com/airfranc86/SkypulseARinfo)"
_TRANSITORIOS = {429, 500, 502, 503, 504}


class ErrorDeRed(OSError):
    """A request failed in a way that retrying will not fix (or ran out of attempts)."""


def _transitorio(e: Exception) -> bool:
    if isinstance(e, urllib.error.HTTPError):
        return e.code in _TRANSITORIOS
    return isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError))


def _con_reintentos(url: str, accion):
    ultimo: Exception | None = None
    for intento in range(INTENTOS):
        try:
            return accion()
        except ErrorDeRed:
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if not _transitorio(e):
                raise ErrorDeRed(f"{url}: {e}") from e
            ultimo = e
            if intento < INTENTOS - 1:
                time.sleep(ESPERA_S * (intento + 1))
    raise ErrorDeRed(f"{url}: sin respuesta tras {INTENTOS} intentos ({ultimo})") from ultimo


def existe(url: str) -> bool:
    """True when a HEAD request answers 200; False on 403/404 (S3 answers 403 for a missing key)."""

    def pedir() -> bool:
        pedido = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(pedido, timeout=TIMEOUT_S) as respuesta:
                return respuesta.status == 200
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return False
            raise

    return _con_reintentos(url, pedir)


def fetch(url: str, rango: tuple[int, int | None] | None = None) -> bytes:
    """GET `url`, or only the bytes `rango = (first, last)` (last None = to the end).

    With a range the server must answer 206 and exactly the bytes asked; otherwise nothing is read, so a
    server that ignores `Range` cannot make us load a ~500 MB file. Without a range the body is capped.
    Transient failures (5xx, timeouts) are retried; a 4xx or a protocol mismatch is not.
    """
    cabeceras = {"User-Agent": _USER_AGENT}
    if rango is not None:
        inicio, fin = rango
        cabeceras["Range"] = f"bytes={inicio}-{'' if fin is None else fin}"
        tope = (fin - inicio + 1) if fin is not None else MAX_RANGO_ABIERTO
    else:
        tope = MAX_SIN_RANGO

    def pedir() -> bytes:
        with urllib.request.urlopen(urllib.request.Request(url, headers=cabeceras), timeout=TIMEOUT_S) as r:
            if rango is not None and r.status != 206:
                raise ErrorDeRed(f"{url}: se esperaba 206 con el rango pedido y llegó {r.status}")
            datos = r.read(tope + 1)
        if len(datos) > tope:
            raise ErrorDeRed(f"{url}: la respuesta supera el tope de {tope} bytes")
        if rango is not None and rango[1] is not None and len(datos) != tope:
            raise ErrorDeRed(f"{url}: llegaron {len(datos)} bytes y se pidieron {tope}")
        return datos

    return _con_reintentos(url, pedir)
