#!/usr/bin/env python3
"""
FeatureUnivision — Endpoint de integración (B) para SkypulseAR.
Expone el forecast más reciente como JSON o HTML.

Uso local (no requiere modificar SkypulseAR inmediatamente):
  uv run uvicorn feature_univision.app:app --host 0.0.0.0 --port 8082
O integrarlo como sub-app en FastAPI / Vercel con proxy inverso.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pathlib import Path
import json
from datetime import datetime

class ForecastNotReady(Exception):
    pass

def _clean_error(status: str, message: str, code: int = 404) -> dict:
    return {
        "feature": "FeatureUnivision",
        "status": status,
        "message": message,
        "recovery": "Ejecutar dataset_agent, segmentation_agent, alert_agent y forecast_agent secuencialmente.",
        "pipeline_refs": ["dataset_agent", "segmentation_agent", "alert_agent", "forecast_agent"],
    }

app = FastAPI(title="FeatureUnivision — Forecast Endpoint")

ROOT = Path(__file__).parent


@app.get("/")
def root():
    return {"feature": "FeatureUnivision", "status": "active", "docs": "/docs"}


@app.get("/forecast/latest")
def latest_forecast(format: str = "json"):
    """Devuelve el forecast más reciente. format=json (por defecto) o html."""
    output_dir = ROOT / "output"
    reports = sorted(output_dir.glob("forecast_report_*.md"))
    if not reports:
        return JSONResponse(_clean_error("no_forecast", "No hay reporte generado aún."), status_code=404)
    latest = reports[-1]
    # Leer primeras líneas como evidencia (no todo el archivo para evitar latencia)
    with open(latest, "r", encoding="utf-8") as f:
        first_lines = "".join(f.readline() for _ in range(10))
    if format == "html":
        html = f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>FeatureUnivision</title></head><body style='font-family:system-ui,sans-serif;max-width:720px;margin:4rem auto;padding:0 1rem;line-height:1.6;color:#111;'><h1>FeatureUnivision — Forecast</h1><p><strong>Estado</strong>: ok &nbsp;|&nbsp; <strong>Archivo</strong>: <code>{latest.name}</code></p><pre style='background:#f6f8fa;padding:1rem;border-radius:12px;overflow:auto;font-size:.85rem;'>{first_lines}</pre><p><strong>Pipeline refs</strong>: dataset_agent, segmentation_agent, alert_agent, forecast_agent</p><hr><p><small>SkyPulseAR — Integrated feature endpoint (B). Source: {str(latest.relative_to(ROOT.parent))}</small></p></body></html>"
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html, status_code=200)
    return {
        "feature": "FeatureUnivision",
        "status": "ok",
        "generated_at": datetime.now().isoformat(),
        "file": latest.name,
        "path": str(latest.relative_to(ROOT.parent)),
        "preview_md_first_10_lines": first_lines,
        "pipeline_refs": ["dataset_agent", "segmentation_agent", "alert_agent", "forecast_agent"],
        "note": "Reemplazar stub de segmentation con ACLNet (torch) cuando esté disponible.",
    }


@app.get("/forecast/alerts")
def latest_alert():
    alert_dir = ROOT / "alerts"
    files = sorted(alert_dir.glob("alert_*.json"))
    if not files:
        return JSONResponse(_clean_error("no_alert", "No hay alerta generada aún."), status_code=404)
    with open(files[-1], "r", encoding="utf-8") as f:
        return json.load(f)
