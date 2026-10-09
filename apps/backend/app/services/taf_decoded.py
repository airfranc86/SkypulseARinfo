"""TAF decodificado por períodos a partir del JSON de AWC (FRA-365).

Función pura: recibe una entrada de `aviationweather.gov/api/data/taf?format=json` y devuelve un
`TafDecoded`, o `None` si no hay nada utilizable. No hace red; el pedido vive en `services/metar.py`.

Supuestos sobre AWC, verificados con el TAF real de SACO (tests/fixtures/awc_taf/):
- `fcstChange` es None (grupo base), "BECMG", "TEMPO" (también para "PROB40 TEMPO", con
  `probability`). "FM" y "PROB" no aparecen en la muestra: se mapean por nombre.
- Un grupo que no declara viento, visibilidad o nubes los deja nulos o vacíos: en el TAF significa
  "sin cambios", así que se completan con lo vigente (ver `inherited`). Las nubes vacías se tratan
  como "sin cambios"; "NSC"/"CLR" llegan como una capa con ese `cover`.
- TX/TN: se usa el `validTime` de AWC. El texto crudo puede traer un día fuera de la vigencia
  (en SACO, `TX28/0719Z` con vigencia hasta 07/18Z) y AWC lo normaliza.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.schemas.taf import (
    TafCloud,
    TafDecoded,
    TafPeriod,
    TafTemperature,
    TafWind,
)
from app.services.visibilidad import MAX_VISIBILITY_M, SM_TO_M, is_open_ended, parse_visibility_sm

_CHANGES = {"FM": "from", "BECMG": "becoming", "TEMPO": "tempo", "PROB": "prob"}
# Los grupos que pasan a ser lo vigente: lo que declaran lo heredan los grupos siguientes.
_PREVAILING = {"initial", "from", "becoming"}
_CEILING_COVERS = frozenset({"BKN", "OVC", "VV"})
_CATEGORIES = ("VFR", "MVFR", "IFR", "LIFR")
_OPEN_SKY_SM = 10.0  # "6+" / "P6SM": 6 millas o más, para la categoría vale cualquier cosa > 5


# ---------------------------------------------------------------- lectura tolerante


def _dt(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    try:
        return datetime.fromtimestamp(value, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _non_negative(value: object) -> int | None:
    number = _int(value)
    return number if number is not None and number >= 0 else None


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value)


# ---------------------------------------------------------------- campos de un grupo


def _wind(period: dict[str, Any]) -> TafWind | None:
    wdir = period.get("wdir")
    variable = isinstance(wdir, str) and wdir.strip().upper() == "VRB"
    direction = None if variable else _int(wdir)
    speed = _non_negative(period.get("wspd"))
    gust = _non_negative(period.get("wgst"))
    if direction is None and not variable and speed is None and gust is None:
        return None
    return TafWind(direction_deg=direction, variable=variable, speed_kt=speed, gust_kt=gust)


def _visibility(visib: object) -> tuple[int | None, bool, float | None]:
    """(metros a 100 m, es "6 o más", millas para la categoría)."""
    miles = parse_visibility_sm(visib)
    if miles is None:
        return None, False, None
    if is_open_ended(visib):
        return int(MAX_VISIBILITY_M), True, _OPEN_SKY_SM
    meters = min(miles * SM_TO_M, MAX_VISIBILITY_M)
    return round(meters / 100.0) * 100, False, miles


def _clouds(value: object) -> list[TafCloud]:
    clouds: list[TafCloud] = []
    for layer in value if isinstance(value, list) else []:
        if not isinstance(layer, dict) or not isinstance(layer.get("cover"), str):
            continue
        kind = layer.get("type")
        clouds.append(
            TafCloud(
                cover=layer["cover"].strip().upper(),
                base_ft=_non_negative(layer.get("base")),
                kind=kind.strip().upper() if isinstance(kind, str) and kind.strip() else None,
            )
        )
    return clouds


def _weather(value: object) -> list[str]:
    return value.split() if isinstance(value, str) else []


# ---------------------------------------------------------------- categoría de vuelo (FAA)


def ceiling_ft(clouds: Sequence[TafCloud]) -> int | None:
    """Techo: la base más baja entre las capas BKN, OVC o VV. None si no hay techo."""
    bases = [c.base_ft for c in clouds if c.cover in _CEILING_COVERS and c.base_ft is not None]
    return min(bases) if bases else None


def flight_category(visibility_sm: float | None, ceiling: int | None) -> str | None:
    """VFR, MVFR, IFR o LIFR según la peor de la visibilidad y el techo. None si no hay ninguno."""
    ranks: list[int] = []
    if visibility_sm is not None:
        ranks.append(3 if visibility_sm < 1 else 2 if visibility_sm < 3 else 1 if visibility_sm <= 5 else 0)
    if ceiling is not None:
        ranks.append(3 if ceiling < 500 else 2 if ceiling < 1000 else 1 if ceiling <= 3000 else 0)
    if visibility_sm is None and ceiling is None:
        return None
    return _CATEGORIES[max(ranks, default=0)]


# ---------------------------------------------------------------- el TAF entero


def _change_of(raw_change: object, position: int) -> str:
    if raw_change is None:
        return "initial" if position == 0 else "from"
    name = str(raw_change).strip().upper()
    return _CHANGES.get(name, name.lower() or "from")


def _temperatures(fcsts: list[dict[str, Any]]) -> list[TafTemperature]:
    found: list[TafTemperature] = []
    for period in fcsts:
        for item in period.get("temp") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("maxOrMin") or "").strip().upper()
            celsius = _float(item.get("surfaceTemp"))
            valid_at = _dt(item.get("validTime"))
            if kind in ("MAX", "MIN") and celsius is not None and valid_at is not None:
                found.append(TafTemperature(kind=kind.lower(), celsius=celsius, valid_at=valid_at))
    return found


def normalize_taf(entry: Any) -> TafDecoded | None:
    """Entrada de AWC -> TAF por períodos. None si no hay ningún período con ventana de tiempo."""
    if not isinstance(entry, dict) or not isinstance(entry.get("fcsts"), list):
        return None
    usable = [p for p in entry["fcsts"] if isinstance(p, dict)]
    periods: list[TafPeriod] = []
    kept: list[dict[str, Any]] = []
    prev_wind: TafWind | None = None
    prev_vis: tuple[int | None, bool, float | None] = (None, False, None)
    prev_clouds: list[TafCloud] = []

    for raw in usable:
        valid_from, valid_to = _dt(raw.get("timeFrom")), _dt(raw.get("timeTo"))
        if valid_from is None or valid_to is None:
            continue
        change = _change_of(raw.get("fcstChange"), len(periods))
        inherited: list[str] = []

        wind = _wind(raw)
        if wind is None and prev_wind is not None:
            wind, inherited = prev_wind, [*inherited, "wind"]
        vis = _visibility(raw.get("visib"))
        if vis[0] is None and prev_vis[0] is not None:
            vis, inherited = prev_vis, [*inherited, "visibility"]
        clouds = _clouds(raw.get("clouds"))
        if not clouds and prev_clouds:
            clouds, inherited = list(prev_clouds), [*inherited, "clouds"]

        if change in _PREVAILING:
            prev_wind, prev_vis, prev_clouds = wind, vis, clouds
        periods.append(
            TafPeriod(
                change=change,
                probability=_non_negative(raw.get("probability")),
                valid_from=valid_from,
                valid_to=valid_to,
                becoming_by=_dt(raw.get("timeBec")),
                wind=wind,
                visibility_m=vis[0],
                visibility_over=vis[1],
                clouds=clouds,
                weather=_weather(raw.get("wxString")),
                flight_category=flight_category(vis[2], ceiling_ft(clouds)),
                inherited=inherited,
            )
        )
        kept.append(raw)

    if not periods:
        return None
    return TafDecoded(
        icao=str(entry.get("icaoId") or "").strip().upper(),
        name=entry.get("name") if isinstance(entry.get("name"), str) else None,
        issued_at=_iso(entry.get("issueTime") or entry.get("bulletinTime")),
        valid_from=_dt(entry.get("validTimeFrom")),
        valid_to=_dt(entry.get("validTimeTo")),
        raw=str(entry.get("rawTAF") or ""),
        periods=periods,
        temperatures=_temperatures(kept),
    )
