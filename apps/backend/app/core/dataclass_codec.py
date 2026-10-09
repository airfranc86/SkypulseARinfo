"""Códec JSON explícito de dataclasses (sin pickle).

Guardar el "último dato bueno" en Redis exige serializar las dataclasses de Open-Meteo. Se hace con
JSON y con un registro cerrado de tipos: lo que viene de Redis nunca elige qué clase se instancia
(solo las registradas) ni ejecuta código (no hay pickle), y cada valor se valida contra los type hints
de la dataclass. Cualquier desajuste lanza ``CodecError``; el llamador lo trata como "no hay copia".

Tipos soportados: ``None``, ``bool``, ``int``, ``float``, ``str``, ``datetime``, ``list[X]``,
``dict[str, X]``, uniones ``X | None`` y dataclasses registradas (anidadas incluidas). Además, un
``dict``/``list`` de JSON crudo (p. ej. la respuesta sin parsear de Niebla) viaja con el tipo ``"json"``.

Los mensajes de ``CodecError`` nombran campos y tipos, nunca valores.
"""
from __future__ import annotations

import dataclasses
import types
import typing
from datetime import datetime
from typing import Any

RAW_JSON_TYPE = "json"


class CodecError(Exception):
    """El valor no se puede codificar o no encaja con el tipo registrado."""


def _is_union(origin: Any) -> bool:
    return origin is typing.Union or origin is types.UnionType


class DataclassCodec:
    """Convierte instancias de las dataclasses registradas a datos JSON y de vuelta."""

    def __init__(self, *classes: type) -> None:
        for cls in classes:
            if not dataclasses.is_dataclass(cls):
                raise TypeError(f"{cls!r} no es una dataclass")
        self._registry: dict[str, type] = {cls.__name__: cls for cls in classes}
        self._hints: dict[type, dict[str, Any]] = {}

    # -- Codificación ------------------------------------------------------------------------

    def encode(self, value: Any) -> tuple[str, Any]:
        """``(nombre_del_tipo, datos_json)``. Solo acepta los tipos registrados o JSON crudo."""
        if isinstance(value, (dict, list)):
            return RAW_JSON_TYPE, value
        cls = type(value)
        if dataclasses.is_dataclass(value) and self._registry.get(cls.__name__) is cls:
            return cls.__name__, self._encode(value)
        raise CodecError(f"tipo no registrado: {cls.__name__}")

    def _encode(self, value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, list):
            return [self._encode(item) for item in value]
        if isinstance(value, dict):
            return {str(k): self._encode(v) for k, v in value.items()}
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            if self._registry.get(type(value).__name__) is not type(value):
                raise CodecError(f"dataclass no registrada: {type(value).__name__}")
            return {f.name: self._encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
        raise CodecError(f"tipo no serializable: {type(value).__name__}")

    # -- Decodificación ----------------------------------------------------------------------

    def decode(self, type_name: str, data: Any) -> Any:
        """Reconstruye el valor. ``CodecError`` si el tipo no está registrado o los datos no encajan."""
        if type_name == RAW_JSON_TYPE:
            if isinstance(data, (dict, list)):
                return data
            raise CodecError("json crudo: se esperaba objeto o lista")
        cls = self._registry.get(type_name) if isinstance(type_name, str) else None
        if cls is None:
            raise CodecError("tipo desconocido")
        return self._decode_dataclass(cls, data)

    def _fields_of(self, cls: type) -> dict[str, Any]:
        hints = self._hints.get(cls)
        if hints is None:
            hints = typing.get_type_hints(cls)
            self._hints[cls] = hints
        return hints

    def _decode_dataclass(self, cls: type, data: Any) -> Any:
        if not isinstance(data, dict):
            raise CodecError(f"{cls.__name__}: se esperaba un objeto")
        fields = {f.name: f for f in dataclasses.fields(cls)}
        unknown = set(data) - set(fields)
        if unknown:
            raise CodecError(f"{cls.__name__}: campo desconocido {sorted(unknown)[0]!r}")
        hints = self._fields_of(cls)
        kwargs: dict[str, Any] = {}
        for name, field in fields.items():
            if name in data:
                kwargs[name] = self._decode(hints[name], data[name], f"{cls.__name__}.{name}")
            elif field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
                raise CodecError(f"{cls.__name__}: falta el campo {name!r}")
        return cls(**kwargs)

    def _decode(self, tp: Any, data: Any, path: str) -> Any:
        origin = typing.get_origin(tp)
        args = typing.get_args(tp)

        if tp is Any:
            return data
        if _is_union(origin):
            return self._decode_union(args, data, path)
        if origin is list:
            if not isinstance(data, list):
                raise CodecError(f"{path}: se esperaba una lista")
            return [self._decode(args[0], item, f"{path}[]") for item in data]
        # dict[str, X] y las dataclasses anidadas se prueban con las clases registradas (MultiModelDailyData);
        # ninguna caché de producción las guarda hoy (el consenso multi-modelo no se persiste).
        if origin is dict:
            if not isinstance(data, dict):
                raise CodecError(f"{path}: se esperaba un objeto")
            return {k: self._decode(args[1], v, f"{path}{{}}") for k, v in data.items()}
        if tp is type(None):
            if data is not None:
                raise CodecError(f"{path}: se esperaba null")
            return None
        if tp is bool:
            if not isinstance(data, bool):
                raise CodecError(f"{path}: se esperaba bool")
            return data
        if tp is int:
            if isinstance(data, bool) or not isinstance(data, int):
                raise CodecError(f"{path}: se esperaba int")
            return data
        if tp is float:
            if isinstance(data, bool) or not isinstance(data, (int, float)):
                raise CodecError(f"{path}: se esperaba número")
            return float(data)
        if tp is str:
            if not isinstance(data, str):
                raise CodecError(f"{path}: se esperaba str")
            return data
        if tp is datetime:
            return self._decode_datetime(data, path)
        if isinstance(tp, type) and dataclasses.is_dataclass(tp):
            if self._registry.get(tp.__name__) is not tp:
                raise CodecError(f"{path}: dataclass no registrada")
            return self._decode_dataclass(tp, data)
        raise CodecError(f"{path}: tipo no soportado")

    def _decode_union(self, args: tuple[Any, ...], data: Any, path: str) -> Any:
        if data is None:
            if type(None) in args:
                return None
            raise CodecError(f"{path}: no admite null")
        for arg in args:
            if arg is type(None):
                continue
            try:
                return self._decode(arg, data, path)
            except CodecError:
                continue
        raise CodecError(f"{path}: ninguna variante de la unión encaja")

    @staticmethod
    def _decode_datetime(data: Any, path: str) -> datetime:
        if not isinstance(data, str):
            raise CodecError(f"{path}: se esperaba un datetime ISO 8601")
        try:
            return datetime.fromisoformat(data)
        except ValueError:
            raise CodecError(f"{path}: datetime ilegible") from None
