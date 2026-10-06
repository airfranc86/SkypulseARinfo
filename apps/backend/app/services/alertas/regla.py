"""Regla de tormenta para alertas push (FRA-348 / FRA-351).

Funciones puras: reciben la serie horaria de ECMWF ya obtenida
(`HourlyForecastExt` con `weather_codes` y `cape_j_kg` de ECMWF) y no hacen
red. Pedir el pronóstico de cada zona le toca a la evaluación programada.
Los umbrales y horarios están en `umbrales.py`.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from app.services.alertas import umbrales
from app.services.openmeteo import HourlyForecastExt

_AR = timezone(timedelta(hours=-3))

Motivo = Literal["codigo", "cape", "codigo+cape"]


@dataclass(frozen=True)
class HoraTormenta:
    hora: str  # "HH:00", hora de Argentina
    timestamp: int
    weather_code: int | None
    cape_j_kg: float | None
    motivo: Motivo


@dataclass(frozen=True)
class ResultadoRegla:
    horas: tuple[HoraTormenta, ...]

    @property
    def hay_tormenta(self) -> bool:
        return bool(self.horas)


def _motivo(weather_code: int | None, cape_j_kg: float | None) -> Motivo | None:
    por_codigo = weather_code is not None and weather_code in umbrales.CODIGOS_TORMENTA
    por_cape = cape_j_kg is not None and cape_j_kg >= umbrales.CAPE_TORMENTA_J_KG
    if por_codigo and por_cape:
        return "codigo+cape"
    if por_codigo:
        return "codigo"
    if por_cape:
        return "cape"
    return None


def es_hora_de_tormenta(weather_code: int | None, cape_j_kg: float | None) -> bool:
    """Una hora cuenta como tormenta por código 95-99 o por CAPE >= 2500 J/kg. Sin datos, nunca."""
    return _motivo(weather_code, cape_j_kg) is not None


def ventana(ahora: datetime) -> tuple[int, int] | None:
    """Ventana [inicio, fin) en segundos epoch que mira la revisión de `ahora`.

    Las revisiones de hoy miran desde su hora en punto hasta la medianoche; la
    de las 21 h mira el día siguiente completo. Fuera de esas horas, o en el
    silencio (22 a 7 h), no hay ventana.
    """
    local = ahora.astimezone(_AR)
    hora = local.hour
    if hora >= umbrales.SILENCIO_DESDE_H or hora < umbrales.SILENCIO_HASTA_H:
        return None
    medianoche_hoy = local.replace(hour=0, minute=0, second=0, microsecond=0)
    medianoche_manana = medianoche_hoy + timedelta(days=1)
    if hora == umbrales.REVISION_MANANA:
        inicio, fin = medianoche_manana, medianoche_manana + timedelta(days=1)
    elif hora in umbrales.REVISIONES_HOY:
        inicio, fin = local.replace(minute=0, second=0, microsecond=0), medianoche_manana
    else:
        return None
    return int(inicio.timestamp()), int(fin.timestamp())


def _en(lista: list, i: int):
    return lista[i] if i < len(lista) else None


def evaluar_tormenta(hourly: HourlyForecastExt | None, inicio: int, fin: int) -> ResultadoRegla:
    """Horas de tormenta con `inicio <= timestamp < fin`. Sin serie, o sin datos, no hay tormenta."""
    if hourly is None:
        return ResultadoRegla(horas=())
    horas: list[HoraTormenta] = []
    for i, ts in enumerate(hourly.timestamps):
        if not inicio <= ts < fin:
            continue
        codigo = _en(hourly.weather_codes, i)
        cape = _en(hourly.cape_j_kg, i)
        motivo = _motivo(codigo, cape)
        if motivo is None:
            continue
        etiqueta = _en(hourly.hour_labels, i) or datetime.fromtimestamp(ts, _AR).strftime("%H:00")
        horas.append(HoraTormenta(hora=etiqueta, timestamp=ts, weather_code=codigo, cape_j_kg=cape, motivo=motivo))
    return ResultadoRegla(horas=tuple(horas))


def evaluar_revision(hourly: HourlyForecastExt | None, ahora: datetime) -> ResultadoRegla | None:
    """Evalúa la revisión de `ahora`; `None` si esa hora no es de revisión (incluye el silencio)."""
    ventana_ahora = ventana(ahora)
    if ventana_ahora is None:
        return None
    return evaluar_tormenta(hourly, *ventana_ahora)
