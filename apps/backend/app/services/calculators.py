"""Calculadores meteorológicos puros — sin I/O externo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.tools import ToolResult


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

ScoreLabel = Literal["Excelente", "Bueno", "Regular", "No apto"]
ScoreColor = Literal["green", "yellow", "red"]


def _label_and_color(score: int) -> tuple[ScoreLabel, ScoreColor]:
    if score >= 75:
        return "Excelente", "green"
    if score >= 50:
        return "Bueno", "yellow"
    if score >= 30:
        return "Regular", "red"
    return "No apto", "red"


# ---------------------------------------------------------------------------
# Sensación térmica
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeelsLikeResult:
    formula: Literal["heat_index", "wind_chill", "none"]
    feels_like_c: float
    temp_c: float
    humidity: float | None
    wind_speed_kmh: float | None


def compute_sensacion_termica(
    temp_c: float,
    humidity: float | None,
    wind_speed_kmh: float | None,
) -> FeelsLikeResult:
    """
    Calcula la sensación térmica usando Heat Index (calor) o Wind Chill (frío).
    Condición Heat Index: temp > 26 AND humidity > 40.
    Condición Wind Chill: temp < 10 AND wind > 5.
    Si ninguna aplica, retorna la temperatura real.
    """
    if temp_c > 26 and humidity is not None and humidity > 40:
        T = temp_c * 9 / 5 + 32
        R = humidity
        hi_f = (
            -42.379
            + 2.04901523 * T
            + 10.14333127 * R
            - 0.22475541 * T * R
            - 0.00683783 * T * T
            - 0.05481717 * R * R
            + 0.00122874 * T * T * R
            + 0.00085282 * T * R * R
            - 0.00000199 * T * T * R * R
        )
        feels_like_c = (hi_f - 32) * 5 / 9
        return FeelsLikeResult(
            formula="heat_index",
            feels_like_c=round(feels_like_c, 1),
            temp_c=temp_c,
            humidity=humidity,
            wind_speed_kmh=wind_speed_kmh,
        )

    if temp_c < 10 and wind_speed_kmh is not None and wind_speed_kmh > 5:
        v = wind_speed_kmh
        wc = (
            13.12
            + 0.6215 * temp_c
            - 11.37 * (v ** 0.16)
            + 0.3965 * temp_c * (v ** 0.16)
        )
        return FeelsLikeResult(
            formula="wind_chill",
            feels_like_c=round(wc, 1),
            temp_c=temp_c,
            humidity=humidity,
            wind_speed_kmh=wind_speed_kmh,
        )

    return FeelsLikeResult(
        formula="none",
        feels_like_c=temp_c,
        temp_c=temp_c,
        humidity=humidity,
        wind_speed_kmh=wind_speed_kmh,
    )


# ---------------------------------------------------------------------------
# Cota de nieve
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnowLevelResult:
    alcaide_m: float
    gradiente_m: float
    m850_hpa_m: float | None
    average_m: float
    temp_c: float
    station_altitude_m: float


def compute_cota_de_nieve(
    temp_c: float,
    station_altitude_m: float,
    temp_850_hpa: float | None,
) -> SnowLevelResult:
    """
    Estima la cota de nieve usando tres métodos:
    1. Alcaide: fórmula empírica española.
    2. Gradiente: lapse rate estándar 6.5 °C/km.
    3. 850 hPa: desde el nivel de presión estándar (~1500 m).
    Los valores negativos se clampean a 0.
    """
    alcaide_raw = 150.0 * (temp_c - 0.5) + station_altitude_m
    alcaide_m = max(0.0, alcaide_raw)

    gradiente_raw = station_altitude_m + (temp_c / 6.5) * 1000.0
    gradiente_m = max(0.0, gradiente_raw)

    m850_hpa_m: float | None = None
    if temp_850_hpa is not None:
        m850_raw = 1500.0 + (temp_850_hpa / 6.5) * 1000.0
        m850_hpa_m = max(0.0, m850_raw)

    values = [v for v in [alcaide_m, gradiente_m, m850_hpa_m] if v is not None]
    average_m = sum(values) / len(values)

    return SnowLevelResult(
        alcaide_m=round(alcaide_m, 2),
        gradiente_m=round(gradiente_m, 2),
        m850_hpa_m=round(m850_hpa_m, 2) if m850_hpa_m is not None else None,
        average_m=round(average_m, 2),
        temp_c=temp_c,
        station_altitude_m=station_altitude_m,
    )


# ---------------------------------------------------------------------------
# TenderRopa
# ---------------------------------------------------------------------------

# Wind direction multipliers: dry/southerly winds favor drying
_WIND_DIR_MULTIPLIER: dict[str, float] = {
    "S": 1.0, "SE": 1.0, "SSE": 1.0, "SSO": 1.0,
    "N": 0.85, "NE": 0.85, "NNE": 0.85, "E": 0.85, "ENE": 0.85, "ESE": 0.85,
    "O": 0.70, "NO": 0.70, "ONO": 0.70, "OSO": 0.70,
    "NNO": 0.75,
}


def score_tender_ropa(
    temp_c: float | None,
    humidity: float | None,
    wind_speed_kmh: float | None,
    precip_mm: float | None = None,
    wind_dir_cardinal: str | None = None,
    precip_prob_pct: float | None = None,
    dew_point_c: float | None = None,
    # Legacy alias: used when precip_mm is not provided
    precip_next_6h: float | None = None,
) -> ToolResult:
    """
    Calcula la aptitud para tender ropa al aire libre.
    Fórmula continua con bonus por punto de rocío; máximo efectivo 105 → clampeado a 100.

    Pesos:
      Humedad      35 pts
      Temperatura  20 pts
      Viento       25 pts (× multiplicador por dirección)
      Precipitación 20 pts
      Rocío bonus    5 pts
    """
    # Normalise legacy param
    if precip_mm is None:
        precip_mm = precip_next_6h

    # ------------------------------------------------------------------
    # A) Humedad (35 pts) — curva continua
    # ------------------------------------------------------------------
    if humidity is None:
        hum_score = 17.5
    elif humidity <= 50:
        hum_score = 35.0
    elif humidity <= 65:
        hum_score = 35.0 * (65.0 - humidity) / 15.0
    elif humidity <= 70:
        hum_score = 5.0
    else:
        hum_score = 0.0

    # ------------------------------------------------------------------
    # B) Temperatura (20 pts) — umbral 12 °C
    # ------------------------------------------------------------------
    if temp_c is None:
        temp_score = 10.0
    elif temp_c >= 20:
        temp_score = 20.0
    elif temp_c >= 12:
        temp_score = 20.0 * (temp_c - 12.0) / 8.0
    elif temp_c >= 5:
        temp_score = 5.0
    else:
        temp_score = 0.0

    # ------------------------------------------------------------------
    # C) Viento (25 pts) — velocidad + dirección
    # ------------------------------------------------------------------
    if wind_speed_kmh is None:
        wind_score = 12.5
    elif 5 <= wind_speed_kmh <= 20:
        wind_score = 25.0
    elif wind_speed_kmh < 5:
        wind_score = 10.0
    elif wind_speed_kmh <= 35:
        wind_score = 25.0 - 20.0 * (wind_speed_kmh - 20.0) / 15.0
    else:
        wind_score = 0.0

    if wind_speed_kmh is not None and wind_speed_kmh > 3:
        dir_upper = (wind_dir_cardinal or "").strip().upper()
        mult = _WIND_DIR_MULTIPLIER.get(dir_upper, 0.90)
        wind_score *= mult

    # ------------------------------------------------------------------
    # D) Precipitación (20 pts) — umbral combinado
    # ------------------------------------------------------------------
    high_prob = precip_prob_pct is not None and precip_prob_pct >= 70

    if precip_mm is not None and precip_mm > 1.0 and high_prob:
        # No apto directo — forzar score bajo antes de bonus
        raw_score = 5.0
        score = max(0, min(100, round(raw_score)))
        label, color = _label_and_color(score)
        return ToolResult(
            tool="tender-ropa",
            score=score,
            label=label,
            color=color,
            headline="No apto para tender ropa",
            reason="Lluvia significativa con alta probabilidad.",
            temp=temp_c,
            humidity=humidity,
            wind_speed=wind_speed_kmh,
            precip=precip_mm,
        )

    if precip_mm is not None and precip_mm > 1.0:
        precip_score = 5.0
    elif precip_mm is not None and precip_mm > 0:
        precip_score = 10.0 if high_prob else 15.0
    elif precip_mm == 0:
        precip_score = 20.0
    else:
        precip_score = 10.0  # sin datos

    # ------------------------------------------------------------------
    # E) Punto de rocío — bonus (5 pts)
    # ------------------------------------------------------------------
    if dew_point_c is None and temp_c is not None and humidity is not None and humidity > 0:
        dew_point_c = temp_c - (100.0 - humidity) / 5.0

    if dew_point_c is not None and temp_c is not None:
        spread = temp_c - dew_point_c
        if spread > 15:
            bonus = 5.0
        elif spread > 10:
            bonus = 3.0
        else:
            bonus = 0.0
    else:
        bonus = 0.0

    raw_score = hum_score + temp_score + wind_score + precip_score + bonus
    score = max(0, min(100, round(raw_score)))

    label, color = _label_and_color(score)

    if score >= 75:
        headline = "Día ideal para tender"
    elif score >= 50:
        headline = "Buenas condiciones para tender"
    elif score >= 30:
        headline = "No es el mejor momento"
    else:
        headline = "No apto para tender ropa"

    factors: list[str] = []
    if humidity is not None and humidity <= 65:
        factors.append(f"humedad {humidity:.0f}%")
    if temp_c is not None and temp_c >= 12:
        factors.append(f"{temp_c:.0f}°C")
    if wind_speed_kmh is not None and wind_speed_kmh <= 20:
        dir_str = f" del {wind_dir_cardinal}" if wind_dir_cardinal else ""
        factors.append(f"viento {wind_speed_kmh:.0f} km/h{dir_str}")
    if precip_mm == 0:
        factors.append("sin lluvia")

    reason = f"Factores favorables: {', '.join(factors)}." if factors else "Condiciones desfavorables."

    return ToolResult(
        tool="tender-ropa",
        score=score,
        label=label,
        color=color,
        headline=headline,
        reason=reason,
        temp=temp_c,
        humidity=humidity,
        wind_speed=wind_speed_kmh,
        precip=precip_mm,
    )


# ---------------------------------------------------------------------------
# HacerDeporte
# ---------------------------------------------------------------------------

def score_hacer_deporte(
    temp_c: float | None,
    humidity: float | None,
    precip: float | None,
    wind_speed_kmh: float | None,
) -> ToolResult:
    """
    Calcula la aptitud para hacer deporte al aire libre.
    Temperatura ideal: 10-25 °C. Sin lluvia. Humedad baja. Viento moderado.
    """
    score = 0
    factors: list[str] = []

    if temp_c is not None and 10 <= temp_c <= 25:
        score += 30
        factors.append("temperatura óptima")

    if humidity is not None and humidity < 70:
        score += 25
        factors.append("humedad tolerable")

    if precip is not None and precip == 0:
        score += 25
        factors.append("sin lluvia")

    if wind_speed_kmh is not None and wind_speed_kmh < 20:
        score += 20
        factors.append("viento suave")

    label, color = _label_and_color(score)

    if score >= 70:
        headline = "Excelentes condiciones para salir"
    elif score >= 40:
        headline = "Condiciones aceptables para deporte"
    elif score >= 20:
        headline = "Condiciones regulares, tomá precauciones"
    else:
        headline = "No es recomendable hacer deporte hoy"

    reason = f"Factores favorables: {', '.join(factors)}." if factors else "Condiciones desfavorables para deporte."

    return ToolResult(
        tool="hacer-deporte",
        score=score,
        label=label,
        color=color,
        headline=headline,
        reason=reason,
        temp=temp_c,
        humidity=humidity,
        wind_speed=wind_speed_kmh,
        precip=precip,
    )


# ---------------------------------------------------------------------------
# LavarCoche
# ---------------------------------------------------------------------------

def score_lavar_coche(
    temp_max_c: float | None,
    precip_mm: float | None,
    wind_speed_kmh: float | None,
    humidity: float | None,
) -> ToolResult:
    """
    Calcula la aptitud para lavar el coche al aire libre (pronóstico diario).
    La precipitación es el factor más determinante.
    """
    score = 100

    # Precipitación — factor más importante
    p = precip_mm or 0.0
    if p > 5:
        score = max(0, score - 60)
    elif p > 1:
        score = max(0, score - 35)
    elif p > 0:
        score = max(0, score - 15)

    # Temperatura (5–30 °C ideal)
    t = temp_max_c
    if t is None or t < 5 or t > 35:
        score = max(0, score - 30)
    elif t < 10 or t > 30:
        score = max(0, score - 15)

    # Viento
    w = wind_speed_kmh or 0.0
    if w > 35:
        score = max(0, score - 25)
    elif w > 20:
        score = max(0, score - 12)

    # Humedad
    h = humidity or 50.0
    if h > 80:
        score = max(0, score - 15)
    elif h > 65:
        score = max(0, score - 7)

    label, color = _label_and_color(score)

    if p > 5:
        headline = "Lluvia intensa esperada"
    elif p > 0:
        headline = "Precipitación posible"
    elif score >= 75:
        headline = "Ideal para lavar"
    elif score >= 50:
        headline = "Condiciones aceptables"
    else:
        headline = "No recomendado"

    if t is not None:
        reason = f"{p:.0f}mm lluvia · {t:.0f}°C máx · {w:.0f} km/h viento"
    else:
        reason = "Datos insuficientes"

    return ToolResult(
        tool="lavar-coche",
        score=score,
        label=label,
        color=color,
        headline=headline,
        reason=reason,
        temp=temp_max_c,
        humidity=humidity,
        wind_speed=wind_speed_kmh,
        precip=precip_mm,
    )
