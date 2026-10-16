"""La costura entre el endpoint y las fuentes de datos del asistente.

El endpoint no sabe de dónde salen los datos: le pide a un `ProveedorDeFuentes` los bloques que el enrutador eligió, para
una ubicación, y recibe `Fuentes` ya armadas. En el PR 2b el proveedor es `FuentesVacias` (todo "sin dato"); el PR 2c lo
reemplaza por uno que lee de la caché sin provocar pedidos nuevos a Open-Meteo.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.services.asistente.hoja_datos import Fuentes


class ProveedorDeFuentes(Protocol):
    async def obtener(self, bloques: tuple[str, ...], *, lat: float, lon: float, ahora_utc: datetime) -> Fuentes:
        """Las fuentes para los `bloques` pedidos en (`lat`, `lon`). Puede levantar una excepción si falla."""
        ...


class FuentesVacias:
    """No tiene ningún dato: cada bloque pedido queda como "sin dato" y el modelo ni se llama."""

    async def obtener(self, bloques: tuple[str, ...], *, lat: float, lon: float, ahora_utc: datetime) -> Fuentes:
        return Fuentes()
