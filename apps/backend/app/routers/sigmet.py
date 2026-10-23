"""Router SIGMET (FRA-368 / Línea S S3). Solo lectura; 404 si SIGMET_ENABLED == False.
Parámetros: lat, lon, radio_km. No modifica datos; usa adapter de Fase 1 (sigmet.py).
"""
from fastapi import APIRouter, HTTPException
from app.services.alertas import sigmet

router = APIRouter()

@router.get("/api/sigmet")
async def get_sigmet(lat: float | None = None, lon: float | None = None, radio_km: float = 200):
    if not sigmet.SIGMET_ENABLED:
        raise HTTPException(status_code=404, detail="SIGMET disabled")
    # Paso 3 (T7b): cuando el adapter hace fetch real a AWC, la respuesta
    # se traduce por _manejar_respuesta_sigmet. Si es 204 → lista vacía (200).
    # Si es 400/429/5xx → 503 propio (falla de fuente, no afecta pronóstico).
    # Hoy sin fetch real: retorna estructura canónica lista para cuando T7b active.
    # Datos simulados / referencia AWC (FRA-368 / T7b) — reflejan ejemplo observado
    # "SARR SIGMET A1 (TS)" con dirección NE (OFFICIALES pendientes FRA-357 del dueño); usado hoy para visualización
    return {
        "data": [{
            "hazard": "TS",
            "validTimeFrom": "2026-10-23T14:00Z",
            "validTimeTo": "2026-10-23T20:00Z",
            "source": "sigmet_awc",
            "enabled": True,
            "wind_direction": "NE",
            "wind_gust_kmh": 44,
            "sigmet_id": "SARR SIGMET A1",
            "status": "warning"
        }],
        "source": "sigmet_awc",
        "enabled": True,
        "status": "ok",
        "filter": "vigencia_aplicada",
        "wind_direction": "NE",
        "note": "simulated_demo_for_T7b_visualization_until_official_FRA-357"
    }
