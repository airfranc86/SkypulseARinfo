"""Las herramientas de decisión (tender, deporte, lavar el auto) tal como las ve Mora.

Mora tiene que decir lo mismo que la página de cada herramienta, así que acá no hay cuentas propias: `tender_ropa`,
`hacer_deporte` y `lavar_coche_dias` son las de `services/herramientas.py` (las mismas que usa el router) y la serie es la
MISMA que pide esa página: best_match de 7 días, SIN la mezcla con ECMWF que usa Previsión (por eso no sale de
`_serie_del_dashboard` de `fuentes_cache.py`).

Funciones puras: reciben la serie ya leída de la caché y la hora; no hacen red. Una serie que ya terminó (todas sus horas
quedaron atrás) no se usa: describiría un tiempo que pasó. Lo que no se puede armar no se inventa: esa herramienta queda
fuera y la hoja la marca "sin dato".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.params import SOURCE_OPENMETEO_FORECAST
from app.schemas.tools import CarWashDay, ToolResult
from app.services import herramientas
from app.services.openmeteo import HourlyForecastExt

_AR = timezone(timedelta(hours=-3))  # Argentina no tiene horario de verano; el mismo huso que usa `regla.py`

BLOQUES_DE_HERRAMIENTA = ("herramienta:tender", "herramienta:deporte", "herramienta:lavar_auto")


def serie_utilizable(serie: HourlyForecastExt | None, ahora_utc: datetime) -> bool:
    """¿La serie sirve para hablar de ahora? Tiene horas, sabemos cuándo se pidió y todavía no terminó."""
    return (
        serie is not None
        and bool(serie.timestamps)
        and serie.fetched_at is not None
        and serie.timestamps[-1] >= ahora_utc.timestamp()
    )


def _motivo_del_dia(dia: CarWashDay) -> str:
    """Lo que explica el puntaje del día, con los números que ve el usuario en la tarjeta (sin símbolos: se lee en voz alta)."""
    lluvia = "sin lluvia" if dia.precip_mm < 0.05 else f"lluvia de {dia.precip_mm:.1f} mm".replace(".", ",")
    return f"Máxima de {round(dia.temp_max_c)} grados, {lluvia} y viento de hasta {round(dia.wind_speed_kmh)} km/h."


def lavar_auto(serie: HourlyForecastExt, ahora_utc: datetime) -> ToolResult | None:
    """El puntaje de lavar el auto HOY, con el mejor día de los que siguen si es otro.

    La página de lavar el auto muestra cinco días (no hay un "hoy"); Mora responde por hoy: el día argentino de `ahora_utc`.
    Si la serie no lo tiene (una copia vieja que ya pasó de largo) no se inventa: `None`.
    """
    hoy = ahora_utc.astimezone(_AR).date().isoformat()
    dias = [d for d in herramientas.lavar_coche_dias(serie) if d.date >= hoy]  # la copia puede arrancar ayer
    if not dias or dias[0].date != hoy:
        return None
    actual = dias[0]
    mejor = max(dias, key=lambda d: d.score)  # el primero entre iguales
    return ToolResult(
        tool="lavar-coche",
        score=actual.score,
        label=actual.label,
        color=actual.color,
        headline=actual.headline,
        reason=_motivo_del_dia(actual),
        best_window=f"Mejor día: {mejor.day_label}" if mejor.date != hoy else None,  # `max` toma el primero: hoy gana los empates
        temp=actual.temp_max_c,
        humidity=actual.humidity,
        wind_speed=actual.wind_speed_kmh,
        precip=actual.precip_mm,
        source=SOURCE_OPENMETEO_FORECAST,
    )


def armar_herramientas(
    serie: HourlyForecastExt | None, ahora_utc: datetime, pedidos: set[str] | frozenset[str],
) -> dict[str, ToolResult]:
    """Las herramientas pedidas (por clave: `tender`, `deporte`, `lavar_auto`) que se pueden armar con esta serie."""
    if not serie_utilizable(serie, ahora_utc):
        return {}
    assert serie is not None
    armadas: dict[str, ToolResult | None] = {}
    if "herramienta:tender" in pedidos:
        armadas["tender"] = herramientas.tender_ropa(serie, ahora_utc)
    if "herramienta:deporte" in pedidos:
        armadas["deporte"] = herramientas.hacer_deporte(serie, ahora_utc)
    if "herramienta:lavar_auto" in pedidos:
        armadas["lavar_auto"] = lavar_auto(serie, ahora_utc)
    return {clave: resultado for clave, resultado in armadas.items() if resultado is not None}
