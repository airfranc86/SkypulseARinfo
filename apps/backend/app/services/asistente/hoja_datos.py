"""Hoja de datos: el JSON compacto, en español, con lo único que el asistente puede citar.

No hace pedidos: recibe los datos ya obtenidos (`Fuentes`) y arma un bloque por cada uno que el enrutador eligió.
Los números salen redondeados como se van a leer (el verificador compara contra estos valores), los datos que
faltan se omiten (nunca `null`) y un bloque pedido sin datos queda como `{"estado": "sin_dato"}`, para que el
modelo diga "no tengo ese dato" en vez de inventarlo. El texto libre que viene de afuera (avisos, METAR, lugar) se
limpia y se acota: va como dato, nunca como instrucción.
"""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from app.schemas.niebla import NieblaResponse
from app.schemas.smn_alertas import SmnAlerta
from app.schemas.taf import TafCloud, TafDecoded
from app.schemas.tools import ToolResult
from app.services.asistente.enrutador import Ruta
from app.services.calculators import SnowLevelResult, is_storm_wmo_code
from app.services.hourly_slots import HOUR_S, SLOT_HOURS, Slot
from app.services.metar_observation import MetarObservation
from app.services.tools_builder import DayAggregate, NowConditions

# Unos 800 tokens: en español, un JSON compacto rinde cerca de 3 caracteres por token.
PRESUPUESTO_CARACTERES = 2400

_AR = timezone(timedelta(hours=-3))  # Argentina no tiene horario de verano
_MAX_FRANJAS = 4
_MAX_DIAS = 2
_MAX_AVISOS = 3
_MAX_PERIODOS_TAF = 3
_MAX_TERMINOS = 2
_LARGO_AVISO = 240
# Caracteres que no pueden llegar a la hoja: así los delimitadores que use el prompt (Fase 3) se eligen entre ellos
# y ningún texto externo los puede imitar.
_PROHIBIDOS = str.maketrans("", "", "<>`{}#[]|")
_ORDEN_DE_NIVEL = {"rojo": 0, "naranja": 1, "amarillo": 2}


@dataclass(frozen=True)
class Fuentes:
    """Los datos ya obtenidos. `None` o vacío = esa fuente no está disponible (no se inventa)."""
    generado_en: datetime | None = None            # cuándo se pidió el pronóstico (UTC)
    lugar: str | None = None
    ahora: NowConditions | None = None
    franjas: tuple[Slot, ...] = ()
    dias: tuple[DayAggregate, ...] = ()
    avisos: tuple[SmnAlerta, ...] | None = None    # None = el feed no respondió; () = no hay avisos vigentes
    niebla: NieblaResponse | None = None
    cota_nieve: SnowLevelResult | None = None
    metar: MetarObservation | None = None
    taf: TafDecoded | None = None
    herramientas: Mapping[str, ToolResult] = field(default_factory=dict)  # clave: `tender`, `deporte`, ...
    glosario: Mapping[str, str] = field(default_factory=dict)             # término normalizado -> definición


@dataclass(frozen=True)
class Hoja:
    """La hoja armada: `datos` es lo que se serializa, `bloques` los que entraron y `omitidos` los que no cupieron."""
    datos: dict[str, Any]
    bloques: tuple[str, ...]
    omitidos: tuple[str, ...] = ()

    @property
    def tiene_datos(self) -> bool:
        return any(self.datos[b] != _sin_dato() for b in self.bloques)

    def a_json(self) -> str:
        return json.dumps(self.datos, ensure_ascii=False, separators=(",", ":"))


def _sin_dato() -> dict[str, str]:
    return {"estado": "sin_dato"}


def _num(valor: float | None, decimales: int) -> int | float | None:
    """Redondea (la mitad hacia arriba) y devuelve entero si no queda decimal, para no gastar caracteres."""
    if valor is None or isinstance(valor, bool) or not math.isfinite(valor):
        return None
    factor = 10 ** decimales
    redondeado = math.floor(valor * factor + 0.5) / factor
    return int(redondeado) if redondeado == int(redondeado) else redondeado


def _sin_nulos(datos: dict[str, Any]) -> dict[str, Any]:
    return {clave: valor for clave, valor in datos.items() if valor is not None}


def _limpiar(texto: object, maximo: int) -> str:
    """Una sola línea, sin controles ni caracteres que imiten delimitadores o formato, de largo acotado."""
    sin_controles = "".join(" " if unicodedata.category(c).startswith("C") else c for c in str(texto))
    limpio = " ".join(sin_controles.translate(_PROHIBIDOS).split())
    if len(limpio) <= maximo:
        return limpio
    corte = limpio[: maximo - 1]
    return (corte.rsplit(" ", 1)[0] if " " in corte else corte).rstrip() + "…"  # sin cortar un número a la mitad


def _local(momento: datetime | None) -> str | None:
    """`dd/mm HH:MM` en hora de Argentina (un datetime sin zona se toma como UTC)."""
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(_AR).strftime("%d/%m %H:%M")


# ---------------------------------------------------------------------------
# Un armador por bloque: devuelven None si no hay nada que decir (queda como `sin_dato`)
# ---------------------------------------------------------------------------

def _ahora(f: Fuentes) -> dict[str, Any] | None:
    if f.ahora is None:
        return None
    return _sin_nulos({
        "temp_c": _num(f.ahora.temp_c, 1),
        "humedad_pct": _num(f.ahora.humidity, 0),
        "viento_kmh": _num(f.ahora.wind_speed_kmh, 0),
    }) or None


def _franja(s: Slot) -> str:
    """`12:00-15:00`: la franja de 3 h que termina en `hour_label` (lo acumulado, como la lluvia, es de esas 3 h)."""
    inicio = datetime.fromtimestamp(s.timestamp, _AR) - timedelta(hours=SLOT_HOURS)
    return f"{inicio.strftime('%H:%M')}-{s.hour_label}"


def _horas(f: Fuentes, ahora_utc: datetime) -> list[dict[str, Any]] | None:
    # Igual que `upcoming_slots`: la franja que cubre la hora en curso (terminó hace menos de 1 h) todavía cuenta.
    corte = ahora_utc.timestamp() - HOUR_S
    proximas = sorted((s for s in f.franjas if s.timestamp > corte), key=lambda s: s.timestamp)[:_MAX_FRANJAS]
    return [
        _sin_nulos({
            "franja": _franja(s),
            "temp_c": _num(s.temp_c, 1),
            "lluvia_mm": _num(s.precip_mm, 1),
            "prob_lluvia_pct": _num(s.precip_prob, 0),
            "viento_kmh": _num(s.wind_speed_kmh, 0),
            "tormenta": True if is_storm_wmo_code(s.weather_code) else None,
        })
        for s in proximas
    ] or None


def _dias(f: Fuentes, ahora_utc: datetime) -> list[dict[str, Any]] | None:
    hoy = ahora_utc.astimezone(_AR).date()
    armados: list[dict[str, Any]] = []
    for dia in sorted(f.dias, key=lambda d: d.date):
        try:
            fecha = date.fromisoformat(dia.date)
        except ValueError:
            continue
        if fecha < hoy:
            continue
        armados.append(_sin_nulos({
            "cuando": "hoy" if fecha == hoy else "mañana" if fecha == hoy + timedelta(days=1) else None,
            "fecha": fecha.strftime("%d/%m"),
            "max_c": _num(dia.temp_max_c, 1),
            "min_c": _num(dia.temp_min_c, 1),
            "lluvia_mm": _num(dia.precip_sum_mm, 1),
            "prob_lluvia_pct": _num(dia.precip_prob_max, 0),
            "viento_max_kmh": _num(dia.wind_speed_max_kmh, 0),
            "viento_dir": _limpiar(dia.wind_dir_cardinal, 4) if dia.wind_dir_cardinal else None,
            "tormenta": True if is_storm_wmo_code(dia.weather_code) else None,
        }))
        if len(armados) == _MAX_DIAS:
            break
    return armados or None


def _clave_de_aviso(a: SmnAlerta) -> tuple[int, datetime]:
    """Más grave primero (rojo, naranja, amarillo, otro) y, entre iguales, el que empieza antes."""
    desde = a.fecha_desde
    if desde is None:
        desde = datetime.max.replace(tzinfo=timezone.utc)
    elif desde.tzinfo is None:
        desde = desde.replace(tzinfo=timezone.utc)
    return _ORDEN_DE_NIVEL.get(a.nivel.strip().lower(), 3), desde


def _avisos(f: Fuentes) -> dict[str, Any] | None:
    if f.avisos is None:
        return None  # el feed no respondió: "no sé", no "no hay"
    # El feed no viene ordenado: primero lo más grave, y entre iguales lo que empieza antes. Si hay más de los que
    # entran, `total` lo dice.
    ordenados = sorted(f.avisos, key=_clave_de_aviso)
    bloque: dict[str, Any] = {"vigentes": [
        _sin_nulos({
            "tipo": _limpiar(a.tipo, 40),
            "nivel": _limpiar(a.nivel, 20),
            "desde": _local(a.fecha_desde),
            "hasta": _local(a.fecha_hasta),
            "texto": _limpiar(a.descripcion, _LARGO_AVISO),
        })
        for a in ordenados[:_MAX_AVISOS]
    ]}
    if len(ordenados) > _MAX_AVISOS:
        bloque["total"] = len(ordenados)
    return bloque


def _niebla(f: Fuentes) -> dict[str, Any] | None:
    n = f.niebla
    if n is None:
        return None
    return _sin_nulos({
        "visibilidad_m": _num(n.visibility_m, 0),
        "estado": _limpiar(n.fog_label, 30),
        "fuente": _limpiar(n.source, 20),
        "estacion": _limpiar(n.metar_station, 8) if n.metar_station else None,
        "horas_con_niebla": [h.hour_label for h in n.hourly if h.fog_level >= 3][:3] or None,
    })


def _cota_nieve(f: Fuentes) -> dict[str, Any] | None:
    c = f.cota_nieve
    if c is None:
        return None
    return _sin_nulos({
        "promedio_m": _num(c.average_m, 0),
        "alcaide_m": _num(c.alcaide_m, 0),
        "gradiente_m": _num(c.gradiente_m, 0),
        "presion_m": _num(c.m850_hpa_m, 0),
        "temp_c": _num(c.temp_c, 1),
    })


def _metar(f: Fuentes) -> dict[str, Any] | None:
    m = f.metar
    if m is None:
        return None
    return _sin_nulos({
        "estacion": _limpiar(m.icao, 8),
        "observado": _local(m.observed_at),
        "temp_c": _num(m.temp_c, 1),
        "punto_rocio_c": _num(m.dewpoint_c, 1),
        "humedad_pct": _num(m.humidity, 0),
        "viento_dir_deg": _num(m.wind_dir_deg, 0),
        "viento_kmh": _num(m.wind_speed_kmh, 0),
        "rafaga_kmh": _num(m.wind_gust_kmh, 0),
        "fenomeno": _limpiar(m.wx_string, 40) if m.wx_string else None,
        "crudo": _limpiar(m.raw, 120) if m.raw else None,
    })


def _nube(capa: TafCloud) -> str:
    partes = [_limpiar(capa.cover, 4)]
    if capa.base_ft is not None:
        partes.append(f"{capa.base_ft} ft")
    if capa.kind:
        partes.append(_limpiar(capa.kind, 4))
    return " ".join(partes)


def _taf(f: Fuentes) -> dict[str, Any] | None:
    t = f.taf
    if t is None:
        return None
    periodos = []
    for p in t.periods[:_MAX_PERIODOS_TAF]:
        viento = p.wind
        periodos.append(_sin_nulos({
            "tipo": _limpiar(p.change, 10),
            "prob": p.probability,
            "desde": _local(p.valid_from),
            "hasta": _local(p.valid_to),
            "viento_dir_deg": _num(viento.direction_deg, 0) if viento else None,
            "viento_kt": _num(viento.speed_kt, 0) if viento else None,
            "rafaga_kt": _num(viento.gust_kt, 0) if viento else None,
            "visibilidad_m": _num(p.visibility_m, 0),
            "nubes": [_nube(c) for c in p.clouds[:3]] or None,
            "fenomenos": [_limpiar(w, 12) for w in p.weather[:4]] or None,
            "categoria": _limpiar(p.flight_category, 6) if p.flight_category else None,
        }))
    return _sin_nulos({"estacion": _limpiar(t.icao, 8), "emitido": _local(t.issued_at), "periodos": periodos})


def _herramienta(f: Fuentes, clave: str) -> dict[str, Any] | None:
    r = f.herramientas.get(clave)
    if r is None:
        return None
    return _sin_nulos({
        "puntaje": r.score,
        "veredicto": r.label,
        "titulo": _limpiar(r.headline, 80),
        "motivo": _limpiar(r.reason, 160),
        "mejor_franja": _limpiar(r.best_window, 30) if r.best_window else None,
    })


def _glosario(f: Fuentes, terminos: tuple[str, ...]) -> list[dict[str, str]] | None:
    return [
        {"termino": t, "definicion": _limpiar(f.glosario[t], 200)}
        for t in terminos[:_MAX_TERMINOS] if t in f.glosario
    ] or None


def _bloque(nombre: str, ruta: Ruta, f: Fuentes, ahora_utc: datetime) -> Any:
    if nombre.startswith("herramienta:"):
        return _herramienta(f, nombre.split(":", 1)[1])
    armadores = {
        "ahora": lambda: _ahora(f),
        "horas": lambda: _horas(f, ahora_utc),
        "dias": lambda: _dias(f, ahora_utc),
        "avisos": lambda: _avisos(f),
        "niebla": lambda: _niebla(f),
        "cota_nieve": lambda: _cota_nieve(f),
        "metar": lambda: _metar(f),
        "taf": lambda: _taf(f),
        "glosario": lambda: _glosario(f, ruta.terminos),
    }
    armador = armadores.get(nombre)
    return armador() if armador else None


# ---------------------------------------------------------------------------
# Presupuesto
# ---------------------------------------------------------------------------

def _recortar(valor: Any) -> bool:
    """Saca el último elemento de la primera lista con más de uno que encuentre; False si no hay nada que recortar."""
    if isinstance(valor, list):
        if len(valor) > 1:
            valor.pop()
            return True
        return any(_recortar(v) for v in valor)
    if isinstance(valor, dict):
        return any(_recortar(v) for v in reversed(list(valor.values())))
    return False


def _largo(encabezado: dict[str, Any], bloques: dict[str, Any], omitidos: list[str]) -> int:
    datos = {**encabezado, **bloques, **({"omitidos": omitidos} if omitidos else {})}
    return len(json.dumps(datos, ensure_ascii=False, separators=(",", ":")))


def armar_hoja(ruta: Ruta, fuentes: Fuentes, ahora_utc: datetime, *, presupuesto: int = PRESUPUESTO_CARACTERES) -> Hoja:
    """Arma la hoja de la `ruta` con las `fuentes`. Si no entra en el presupuesto saca los últimos bloques.

    `ahora_utc` tiene que traer zona horaria; un `generado_en` sin zona se toma como UTC.
    """
    if ahora_utc.tzinfo is None:
        raise ValueError("ahora_utc necesita zona horaria (UTC)")
    encabezado: dict[str, Any] = {}
    if fuentes.lugar:
        encabezado["lugar"] = _limpiar(fuentes.lugar, 40)
    if fuentes.generado_en is not None:
        generado = fuentes.generado_en if fuentes.generado_en.tzinfo else fuentes.generado_en.replace(tzinfo=timezone.utc)
        horas = (ahora_utc - generado).total_seconds() / 3600
        if horas >= 2:
            encabezado["pronostico_hace_h"] = _num(horas, 0)

    bloques = {n: _bloque(n, ruta, fuentes, ahora_utc) or _sin_dato() for n in ruta.bloques}
    omitidos: list[str] = []
    while _largo(encabezado, bloques, omitidos) > presupuesto:
        if len(bloques) > 1:
            omitidos.insert(0, list(bloques)[-1])
            del bloques[omitidos[0]]
        elif not _recortar(next(iter(bloques.values()), None)):
            break

    datos = {**encabezado, **bloques, **({"omitidos": omitidos} if omitidos else {})}
    return Hoja(datos=datos, bloques=tuple(bloques), omitidos=tuple(omitidos))
