"""Cálculo de fase lunar usando el algoritmo Meeus simplificado — sin I/O externo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import acos, asin, cos, degrees, floor, pi, radians, sin


@dataclass(frozen=True)
class MoonPhaseInfo:
    name: str          # Nombre en español
    illumination: float  # 0.0 - 1.0
    icon: str          # Nombre Meteocons sin extensión


# Epoch de referencia: Luna Nueva conocida — 2000-01-06 18:14 UTC
_NEW_MOON_EPOCH = datetime(2000, 1, 6, 18, 14, 0, tzinfo=timezone.utc)
_SYNODIC_MONTH = 29.530588853  # días

_PHASES = [
    (0.00, 0.06, "Nueva",              "moon-new"),
    (0.06, 0.19, "Creciente iluminante", "moon-waxing-crescent"),
    (0.19, 0.31, "Cuarto creciente",   "moon-first-quarter"),
    (0.31, 0.44, "Gibosa creciente",   "moon-waxing-gibbous"),
    (0.44, 0.56, "Llena",              "moon-full"),
    (0.56, 0.69, "Gibosa menguante",   "moon-waning-gibbous"),
    (0.69, 0.81, "Cuarto menguante",   "moon-last-quarter"),
    (0.81, 1.00, "Creciente menguante", "moon-waning-crescent"),
]


def compute_moon_phase(date: datetime) -> MoonPhaseInfo:
    """
    Calcula la fase lunar para una fecha dada.

    Algoritmo: Meeus simplificado.
    1. Días desde la luna nueva de referencia (2000-01-06 18:14 UTC).
    2. Mes sinódico = 29.530588853 días.
    3. phase_fraction = (días % sinódico) / sinódico   → [0, 1)
    4. illumination = (1 - cos(2π * phase_fraction)) / 2  → [0, 1]
    5. Mapeo a 8 fases con nombres en español + íconos Meteocons.
    """
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)

    days_since = (date - _NEW_MOON_EPOCH).total_seconds() / 86400.0
    phase_fraction = (days_since % _SYNODIC_MONTH) / _SYNODIC_MONTH

    illumination = (1 - cos(2 * pi * phase_fraction)) / 2

    for lo, hi, name, icon in _PHASES:
        if lo <= phase_fraction < hi:
            return MoonPhaseInfo(name=name, illumination=round(illumination, 4), icon=icon)

    # Cierre del último segmento (phase_fraction muy próximo a 1.0)
    return MoonPhaseInfo(name="Creciente menguante", illumination=round(illumination, 4), icon="moon-waning-crescent")


# ---------------------------------------------------------------------------
# Moon position — para dibujar el punto lunar en el arco del día
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MoonPositionInfo:
    position_pct: float | None       # 0.0 = moonrise, 1.0 = moonset (None si no calculable)
    moonrise_label: str | None       # "21:34" en hora local Argentina
    moonset_label: str | None        # "08:15" en hora local Argentina
    is_above_horizon: bool           # True si la luna está ahora sobre el horizonte


def _jd(dt: datetime) -> float:
    """Julian Day Number desde datetime UTC-aware."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + dt.minute / 60 + dt.second / 3600) / 24
    if m <= 2:
        y -= 1
        m += 12
    A = int(y / 100)
    B = 2 - A + int(A / 4)
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5


def _moon_ra_dec(jd: float) -> tuple[float, float]:
    """
    RA (horas) y Dec (grados) de la Luna — algoritmo Meeus simplificado.
    Precisión ~1°, suficiente para arco visual.
    """
    T = (jd - 2451545.0) / 36525.0

    # Longitud media de la Luna
    Lp = 218.3164477 + 481267.88123421 * T
    # Anomalía media de la Luna
    M = 134.9633964 + 477198.8675055 * T
    # Argumento de latitud de la Luna
    F = 93.2720950 + 483202.0175233 * T
    # Anomalía media del Sol
    Ms = 357.5291092 + 35999.0502909 * T

    # Longitud eclíptica (correcciones principales)
    lam = (Lp
           + 6.289 * sin(radians(M))
           - 1.274 * sin(radians(2 * F - M))
           + 0.658 * sin(radians(2 * F))
           - 0.214 * sin(radians(2 * M))
           - 0.186 * sin(radians(Ms))
           - 0.114 * sin(radians(2 * F))
           + 0.059 * sin(radians(2 * F - 2 * Ms))
           )
    lam = lam % 360

    # Latitud eclíptica
    beta = 5.128 * sin(radians(F))

    # Oblicuidad de la eclíptica
    eps = 23.4393 - 0.0000004 * T

    # Convertir eclíptica → ecuatorial
    lam_r = radians(lam)
    beta_r = radians(beta)
    eps_r = radians(eps)

    sin_dec = sin(beta_r) * cos(eps_r) + cos(beta_r) * sin(eps_r) * sin(lam_r)
    dec = degrees(asin(sin_dec))

    cos_ra = cos(lam_r) * cos(beta_r) / cos(radians(dec))
    sin_ra = (sin(lam_r) * cos(eps_r) * cos(beta_r) - sin(beta_r) * sin(eps_r))
    ra = degrees(acos(max(-1.0, min(1.0, cos_ra))))
    if sin_ra < 0:
        ra = 360 - ra
    ra_hours = ra / 15.0

    return ra_hours, dec


def _gmst(jd: float) -> float:
    """Greenwich Mean Sidereal Time en horas."""
    T = (jd - 2451545.0) / 36525.0
    gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T
    return (gmst % 360) / 15.0  # en horas


def compute_moon_position(now_utc: datetime, lat: float, lon: float) -> MoonPositionInfo:
    """
    Calcula posición de la Luna para la ubicación y momento dados.
    Retorna posición en arco (análogo a current_position_pct del sol),
    horas de salida/puesta en hora local Argentina, y si está sobre el horizonte.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    jd_now = _jd(now_utc)
    ra, dec = _moon_ra_dec(jd_now)

    gmst = _gmst(jd_now)
    lst = (gmst + lon / 15.0) % 24  # Local Sidereal Time en horas
    H = (lst - ra) * 15             # Hour angle en grados

    # Altitud actual
    lat_r = radians(lat)
    dec_r = radians(dec)
    H_r = radians(H)
    alt = degrees(asin(sin(lat_r) * sin(dec_r) + cos(lat_r) * cos(dec_r) * cos(H_r)))
    is_above = alt > -0.833  # umbral estándar de rise/set

    # Calcular hora de salida y puesta
    denom = cos(lat_r) * cos(dec_r)
    if denom == 0:
        return MoonPositionInfo(
            position_pct=None,
            moonrise_label=None,
            moonset_label=None,
            is_above_horizon=is_above,
        )

    cos_h0 = (sin(radians(-0.833)) - sin(lat_r) * sin(dec_r)) / denom
    if abs(cos_h0) > 1:
        # Luna siempre sobre o siempre bajo el horizonte
        return MoonPositionInfo(
            position_pct=None,
            moonrise_label=None,
            moonset_label=None,
            is_above_horizon=bool(cos_h0 < -1),
        )

    H0 = degrees(acos(cos_h0))  # semi-arco en grados

    # Tiempo de tránsito (luna en el meridiano) en UT
    transit_ut = (ra - lon / 15.0 - gmst + 24) % 24  # horas UT
    rise_ut = (transit_ut - H0 / 15.0) % 24
    set_ut = (transit_ut + H0 / 15.0) % 24

    # Convertir a hora Argentina (UTC-3)
    AR_OFFSET = -3
    rise_ar = (rise_ut + AR_OFFSET) % 24
    set_ar = (set_ut + AR_OFFSET) % 24

    def _fmt(h: float) -> str:
        hh = int(h)
        mm = int((h - hh) * 60)
        return f"{hh:02d}:{mm:02d}"

    moonrise_label = _fmt(rise_ar)
    moonset_label = _fmt(set_ar)

    # position_pct análogo al sol: 0=moonrise, 1=moonset
    duration_h = (set_ut - rise_ut) % 24
    if duration_h <= 0:
        duration_h += 24
    elapsed_h = (now_utc.hour + now_utc.minute / 60 + now_utc.second / 3600 - rise_ut) % 24
    position_pct = max(0.0, min(1.0, elapsed_h / duration_h)) if is_above else None

    return MoonPositionInfo(
        position_pct=position_pct,
        moonrise_label=moonrise_label,
        moonset_label=moonset_label,
        is_above_horizon=is_above,
    )
