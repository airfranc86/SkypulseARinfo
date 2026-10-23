"""Router SIGMET (FRA-368 / Línea S S3). Solo lectura; 404 si SIGMET_ENABLED == False.
Parámetros: lat, lon, radio_km. No modifica datos; usa adapter de Fase 1 (sigmet.py).
"""
from fastapi import APIRouter
from app.services.alertas import sigmet

router = APIRouter()

@router.get("/api/sigmet")
async def get_sigmet(lat: float | None = None, lon: float | None = None, radio_km: float = 200):
    if not sigmet.SIGMET_ENABLED:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="SIGMET disabled")
    return {"data": [], "source": "sigmet_awc", "enabled": sigmet.SIGMET_ENABLED}
