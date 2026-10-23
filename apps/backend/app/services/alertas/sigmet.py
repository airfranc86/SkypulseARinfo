"""Regla SIGMET (FRA-368 / Línea S S2). Adapter al módulo Fase 1 — NO crea fetch nuevo.
Referencia única al endpoint AWC ya usado por Fase 1 (consumo compartido, no duplicación).
La bandera SIGMET_ENABLED (apagada = 404) protege producción.
"""
from app.services.alertas import umbrales

SIGMET_ENABLED: bool = False  # producción apagada; activa con T7b + S3
# Cache TTL (minutos) y contador sugerido por FRA-348 / FRA-368
SIGMET_TTL_MIN: int = 5
SIGMET_COUNTER_NAME: str = "sigmet_awc"  # propuesta; requiere registros en quotas.py
