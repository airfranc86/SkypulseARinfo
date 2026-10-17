"""Reglas de tormenta (FRA-348 / FRA-351) y de lluvia persistente (modo sombra) para alertas push.

Funciones puras: reciben la serie horaria de ECMWF ya obtenida
(`HourlyForecastExt` con `weather_codes`, `cape_j_kg`, `precipitations` y `precip_probs` de ECMWF) y no hacen
red. Pedir el pronóstico de cada zona le toca a la evaluación programada.
Los umbrales y horarios están en `umbrales.py`.
"""

import math
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
    silencio (22 a 5 h), no hay ventana.
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


# ---------------------------------------------------------------------------
# Lluvia persistente (MODO SOMBRA: el resultado solo se cuenta, nunca dispara un aviso)
# ---------------------------------------------------------------------------

MotivoLluvia = Literal["probabilidad", "persistencia"]
_SEGUNDOS_POR_HORA = 3600


@dataclass(frozen=True)
class VentanaLluvia:
    """Una ventana móvil de `LLUVIA_VENTANA_HORAS` horas seguidas que cumple la regla."""

    inicio: int  # epoch segundos: primera hora de la ventana
    fin: int  # epoch segundos: fin (exclusivo) de la ventana
    mm: float
    probabilidad_media: float | None  # None si ECMWF no dio la probabilidad de todas las horas
    horas_con_agua: int
    motivo: MotivoLluvia  # "probabilidad": media >= 70 %; "persistencia": sin probabilidad, >= 4 horas con agua


@dataclass(frozen=True)
class ResultadoLluvia:
    ventanas: tuple[VentanaLluvia, ...]

    @property
    def hay_lluvia(self) -> bool:
        return bool(self.ventanas)


def _numero(valor: object, minimo: float, maximo: float | None) -> float | None:
    """`valor` si es un número finito dentro del rango; si no, `None` (sin dato: nunca se lee un hueco como lluvia)."""
    if isinstance(valor, bool) or not isinstance(valor, int | float) or not math.isfinite(valor):
        return None
    if valor < minimo or (maximo is not None and valor > maximo):
        return None
    return float(valor)


def evaluar_lluvia(hourly: HourlyForecastExt | None, inicio: int, fin: int) -> ResultadoLluvia:
    """Ventanas de lluvia persistente que EMPIEZAN en `inicio <= timestamp < fin`.

    Una ventana son `LLUVIA_VENTANA_HORAS` horas consecutivas, todas con precipitación en la serie (una hora sin dato
    descarta la ventana: un hueco no es lluvia, y tampoco calma). Cumple la regla si:

    - suma `LLUVIA_MM_VENTANA` mm o más; y
    - si ECMWF dio la probabilidad de TODAS las horas de la ventana, su media es `LLUVIA_PROBABILIDAD_MEDIA_MINIMA` o
      más (motivo "probabilidad"); si no la dio (lista vacía o con huecos), al menos `LLUVIA_HORAS_CON_AGUA_MINIMAS`
      de las horas tienen `LLUVIA_MM_HORA_CON_AGUA` mm o más (motivo "persistencia").

    Una ventana puede terminar DESPUÉS de `fin`: la revisión de las 19 h ve la lluvia de la noche aunque se extienda
    de madrugada. Por eso las ventanas no se recortan a la revisión. Sin serie, o sin datos, no hay lluvia.
    """
    if hourly is None:
        return ResultadoLluvia(ventanas=())
    horas = umbrales.LLUVIA_VENTANA_HORAS
    mm_por_hora: dict[int, float] = {}
    probabilidad_por_hora: dict[int, float] = {}
    for i, ts in enumerate(hourly.timestamps):
        mm = _numero(_en(hourly.precipitations, i), 0.0, None)
        if mm is not None:
            mm_por_hora[ts] = mm
        probabilidad = _numero(_en(hourly.precip_probs, i), 0.0, 100.0)
        if probabilidad is not None:
            probabilidad_por_hora[ts] = probabilidad
    ventanas: list[VentanaLluvia] = []
    for ts in hourly.timestamps:
        if not inicio <= ts < fin:
            continue
        horas_de_la_ventana = [ts + k * _SEGUNDOS_POR_HORA for k in range(horas)]
        if any(h not in mm_por_hora for h in horas_de_la_ventana):
            continue
        mms = [mm_por_hora[h] for h in horas_de_la_ventana]
        total = round(sum(mms), 6)  # 0,05 + 0,05 + 0,05 + 0,57 + 1,13 + 1,15 da 2,9999999999999996 en coma flotante: sin redondear perdería el límite de 3 mm
        if total < umbrales.LLUVIA_MM_VENTANA:
            continue
        con_agua = sum(1 for mm in mms if mm >= umbrales.LLUVIA_MM_HORA_CON_AGUA)
        probabilidades = [probabilidad_por_hora.get(h) for h in horas_de_la_ventana]
        if all(p is not None for p in probabilidades):
            media = round(sum(p for p in probabilidades if p is not None) / horas, 6)
            if media < umbrales.LLUVIA_PROBABILIDAD_MEDIA_MINIMA:
                continue
            motivo: MotivoLluvia = "probabilidad"
            probabilidad_media: float | None = media
        else:
            if con_agua < umbrales.LLUVIA_HORAS_CON_AGUA_MINIMAS:
                continue
            motivo = "persistencia"
            probabilidad_media = None
        ventanas.append(
            VentanaLluvia(
                inicio=ts,
                fin=ts + horas * _SEGUNDOS_POR_HORA,
                mm=total,
                probabilidad_media=probabilidad_media,
                horas_con_agua=con_agua,
                motivo=motivo,
            )
        )
    return ResultadoLluvia(ventanas=tuple(ventanas))


def evaluar_revision_lluvia(hourly: HourlyForecastExt | None, ahora: datetime) -> ResultadoLluvia | None:
    """La lluvia de la revisión de `ahora`; `None` si esa hora no es de revisión (incluye el silencio).

    Usa la MISMA ventana que la tormenta (`ventana`): las ventanas de lluvia empiezan dentro de ella.
    """
    ventana_ahora = ventana(ahora)
    if ventana_ahora is None:
        return None
    return evaluar_lluvia(hourly, *ventana_ahora)
