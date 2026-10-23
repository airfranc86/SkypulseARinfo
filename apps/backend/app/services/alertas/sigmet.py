"""Regla SIGMET (FRA-368 / Línea S S2). Adapter al módulo Fase 1 — NO crea fetch nuevo.
Referencia única al endpoint AWC ya usado por Fase 1 (consumo compartido, no duplicación).
La bandera SIGMET_ENABLED (apagada = 404) protege producción.
"""
from app.services.alertas import umbrales

from app.core.config import settings
SIGMET_ENABLED: bool = settings.sigmet_enabled
# Cache TTL (minutos) y contador sugerido por FRA-348 / FRA-368
SIGMET_TTL_MIN: int = 5
SIGMET_COUNTER_NAME: str = "sigmet_awc"  # propuesta; requiere registros en quotas.py

# Paso 3 (T7b): manejo de errores del endpoint AWC (FRA-348 / FRA-368 / Línea S S3).
# El feed puede devolver 200 (datos), 204 (sin datos vigentes), 400 (pedido inválido),
# 429 (límite de 100/min excedido) o 5xx (falla del servicio AWC).
# El adapter no hace fetch hoy (S3 aún pendiente de T7b + encendido), pero las
# funciones de manejo ya están definidas para que el endpoint responda 503
# (fuente no disponible) sin afectar el contrato de Fase 1.

def _manejar_respuesta_sigmet(status_code: int) -> str:
    """Traduce códigos AWC a un mensaje canónico; 204 = sin avisos vigentes (200 con lista vacía)."""
    if status_code == 200:
        return "ok"
    if status_code == 204:
        return "sin_avisos_vigentes"
    if status_code == 400:
        return "pedido_invalido"
    if status_code == 429:
        return "limite_excedido"
    if status_code >= 500:
        return "falla_servicio"
    return "desconocido"


def es_aviso_vigente(valid_time_to: int | None, ahora_epoch: int = 0) -> bool:
    """Filtra SIGMET por vigencia: el feed no viene filtrado por AWC."""
    if valid_time_to is None:
        return False
    return ahora_epoch < valid_time_to
