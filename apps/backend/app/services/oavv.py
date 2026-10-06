"""Servicio OAVV-SEGEMAR — detección de nivel de alerta volcánica.

SEGEMAR no expone una API JSON. El nivel de alerta se publica únicamente
como imagen PNG dinámica (show_alerta.php?id=X). Este módulo fetchea cada
imagen y analiza el color dominante de la franja central con Pillow para
determinar el nivel: verde → amarillo → naranja → rojo.

Si la imagen de un volcán no se puede descargar o interpretar, el volcán queda
en "sin_datos" — nunca en "verde" (FRA-343): un "estable" inventado es un falso
negativo en una alerta de seguridad.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from statistics import mean
from typing import Final

import httpx
from cachetools import TLRUCache
from PIL import Image

from app.core import usage_counter
from app.core.config import settings
from app.core.http_client import get_client
from app.schemas.volcanes import ALERT_HEX, AlertLevel, Volcan, VolcanesResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Catálogo estático
# ---------------------------------------------------------------------------

_CATALOG: Final[list[dict]] = [
    {"id": 1,  "name": "Lanín",            "province": "Argentina-Chile",      "lat": -39.633, "lon": -71.517, "slug": "lanin",           "ranking": None},
    {"id": 2,  "name": "Copahue",          "province": "Neuquén",              "lat": -37.862, "lon": -71.183, "slug": "copahue",         "ranking": 1},
    {"id": 3,  "name": "Planchón-Peteroa", "province": "Argentina-Chile",      "lat": -35.247, "lon": -70.568, "slug": "planchon-peteroa","ranking": None},
    {"id": 4,  "name": "Laguna del Maule", "province": "Argentina-Chile",      "lat": -36.083, "lon": -70.583, "slug": "laguna-del-maule","ranking": None},
    {"id": 5,  "name": "San José",         "province": "Argentina-Chile",      "lat": -33.783, "lon": -69.900, "slug": "san-jose",        "ranking": None},
    {"id": 6,  "name": "Tupungatito",      "province": "Argentina-Chile",      "lat": -33.367, "lon": -69.800, "slug": "tupungatito",     "ranking": None},
    {"id": 7,  "name": "Maipo",            "province": "Argentina-Chile",      "lat": -34.167, "lon": -69.833, "slug": "maipo",           "ranking": None},
    {"id": 8,  "name": "Tromen",           "province": "Neuquén",              "lat": -37.133, "lon": -70.050, "slug": "tromen",          "ranking": None},
    {"id": 15, "name": "Isla Decepción",   "province": "Antártida Argentina",  "lat": -62.967, "lon": -60.650, "slug": "isla-decepcion",  "ranking": None},
    {"id": 16, "name": "Domuyo",           "province": "Neuquén",              "lat": -36.633, "lon": -70.433, "slug": "domuyo",          "ranking": None},
]

_BASE_ALERT_URL = "https://oavv.segemar.gob.ar/scripts/show_alerta.php"
_BASE_SEGEMAR   = "https://oavv.segemar.gob.ar/monitoreo-volcanico"

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

# Un resultado con algún volcán "sin_datos" vive poco en caché: apenas OAVV
# vuelve, el próximo request lo vuelve a consultar en vez de esperar 2 horas.
PARTIAL_CACHE_TTL_SECONDS: Final = 60


def _now() -> float:
    """Reloj de la caché. Función de módulo para poder simularlo en tests."""
    return time.monotonic()


def _cache_ttu(_key: str, response: VolcanesResponse, now: float) -> float:
    """Vencimiento por entrada: TTL corto si hubo fallos, normal si está completo.

    ``TTLCache`` solo admite un TTL fijo para toda la caché; ``TLRUCache`` (del
    mismo paquete cachetools) calcula el vencimiento de cada entrada con esta
    función, así que la caché sigue siendo una sola y con el mismo lock.
    """
    ttl = settings.cache_ttl_volcanes_seconds if response.available else PARTIAL_CACHE_TTL_SECONDS
    return now + ttl


_cache_lock = asyncio.Lock()
# El timer se resuelve en cada llamada (lambda) para que los tests puedan reemplazar _now.
_volcanes_cache: TLRUCache = TLRUCache(maxsize=1, ttu=_cache_ttu, timer=lambda: _now())
_CACHE_KEY: Final = "oavv_volcanes"

# ---------------------------------------------------------------------------
# Detección de color
# ---------------------------------------------------------------------------

# Cuánto tiene que superar G a R y a B para reconocer la banda verde
# (real: R≈148 G≈205 B≈126 → margen ~57). El gris neutro del fondo no lo cumple.
_GREEN_MARGIN: Final = 30


def _detect_alert_level(image_bytes: bytes) -> AlertLevel:
    """Samplea la franja superior (10-25 % de alto) del PNG y clasifica el color.

    Las imágenes SEGEMAR (~754×287 px) tienen la banda de color de alerta en el
    tercio superior; la mitad y la parte inferior son fondo gris neutro.

    Umbrales calibrados con datos reales (2026-05):
      verde   → R≈148  G≈205  B≈126  (G dominante)
      amarillo → R≈255  G≈230  B≈103  (R y G altos, B bajo)
      naranja  → R≈220+ G<150  B<90   (R alto, G/B moderados-bajos)
      rojo     → R≈250+ G<80          (R muy alto, G/B muy bajos)

    El verde también se reconoce por color (G claramente dominante). Una imagen
    ilegible, demasiado chica para samplear o sin una banda reconocible (p. ej.
    el fondo gris) devuelve "sin_datos": no se puede afirmar que esté estable.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if w == 0 or h == 0:
            return "sin_datos"

        # Sampleo de 4 filas en el tercio superior (10 – 25 % de altura)
        row_ys = [int(h * pct) for pct in (0.10, 0.15, 0.20, 0.25)]
        samples = [
            img.getpixel((x, row_y))
            for row_y in row_ys
            for x in range(w // 4, 3 * w // 4, 20)
        ]
        if not samples:
            return "sin_datos"

        r = mean(s[0] for s in samples)
        g = mean(s[1] for s in samples)
        b = mean(s[2] for s in samples)

        if r > 220 and g < 80:
            return "rojo"
        if r > 200 and g < 150 and b < 90:
            return "naranja"
        if r > 200 and g > 180 and b < 130:
            return "amarillo"
        if g > 150 and g > r + _GREEN_MARGIN and g > b + _GREEN_MARGIN:
            return "verde"
        logger.warning("OAVV: color sin banda reconocible R=%.0f G=%.0f B=%.0f", r, g, b)
        return "sin_datos"
    except Exception as exc:
        logger.warning("OAVV: error detectando color de imagen: %s", exc)
        return "sin_datos"

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

async def _fetch_alert_image(client: httpx.AsyncClient, volcan_id: int) -> bytes:
    """Descarga la imagen PNG del nivel de alerta para un volcán dado."""
    usage_counter.record("oavv")
    resp = await client.get(
        _BASE_ALERT_URL,
        params={"id": volcan_id, "h": 0},
        timeout=settings.http_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.content


async def _fetch_all_volcanes() -> list[Volcan]:
    """Fetchea y analiza el nivel de alerta de todos los volcanes en paralelo."""
    client = get_client()
    tasks = [_fetch_alert_image(client, v["id"]) for v in _CATALOG]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    volcanes: list[Volcan] = []
    for entry, result in zip(_CATALOG, results):
        if isinstance(result, Exception):
            logger.warning("OAVV: error fetching id=%s: %s", entry["id"], result)
            alert_level: AlertLevel = "sin_datos"   # sin imagen no hay nivel: nunca "verde"
        else:
            alert_level = _detect_alert_level(result)

        volcanes.append(
            Volcan(
                id=entry["id"],
                name=entry["name"],
                province=entry["province"],
                alert_level=alert_level,
                alert_color_hex=ALERT_HEX[alert_level],
                lat=entry["lat"],
                lon=entry["lon"],
                segemar_url=f"{_BASE_SEGEMAR}/{entry['slug']}/",
                ranking=entry["ranking"],
            )
        )
    return volcanes

# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------

async def get_volcanes() -> VolcanesResponse:
    """Retorna el estado de alerta de todos los volcanes monitoreados por OAVV.

    Nunca lanza 503: ante error individual el volcán queda en "sin_datos" y
    ``available`` pasa a False (basta un volcán sin dato: la lista ya no es
    completa y el frontend avisa). ``total`` y ``has_active_alert`` cuentan solo
    los volcanes con dato. Un resultado con fallos se cachea
    ``PARTIAL_CACHE_TTL_SECONDS``; uno completo, ``cache_ttl_volcanes_seconds``.
    """
    async with _cache_lock:
        if _CACHE_KEY in _volcanes_cache:
            return _volcanes_cache[_CACHE_KEY]
        volcanes = await _fetch_all_volcanes()
        with_data = [v for v in volcanes if v.alert_level != "sin_datos"]
        has_active = any(v.alert_level in ("naranja", "rojo") for v in with_data)
        response = VolcanesResponse(
            total=len(with_data),
            has_active_alert=has_active,
            volcanes=volcanes,
            available=len(with_data) == len(volcanes),
        )
        _volcanes_cache[_CACHE_KEY] = response
        return response
