#!/usr/bin/env python3
"""
ForecastAgent — Reporte narrativo del cielo (S4 — AI-Meteorologist style)

Estado: rules-based con intento opcional de LLM (Gemini/Qwen).
Si hay GOOGLE_API_KEY o clave de Qwen configurada, intenta generar
narración LLM; si no, usa template narrativo basado en la clasificación
real de la alerta (grounded forecasting — evita hallucination).

Uso:
  python scripts/forecast_agent.py --alert alerts/alert_<id>.json --output-dir output/
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Intento opcional LLM (no obligatorio; fallback rules siempre funciona)
LLM_AVAILABLE = False
try:
    import google.generativeai as genai
    _api_key = os.getenv("GOOGLE_API_KEY", "")
    if _api_key:
        genai.configure(api_key=_api_key)
        LLM_AVAILABLE = True
    else:
        # Intenta OpenRouter / Qwen via langgraph o http
        pass
except Exception:
    pass

# ============================================================
# Template rules (fallback seguro — grounded)
# ============================================================

NARRATIVES = {
    "clear": {
        "titulo": "Cielo despejado — Condiciones estables",
        "narracion": "El cielo observado presenta condiciones claras. No se detectan sistemas de nubes significativos en este momento; la radiación solar se distribuye sin interferencia, lo que indica un período de estabilidad atmosférica para esta ubicación.",
        "recomendaciones": ["Mantener monitoreo rutinario.", "Condiciones favorables para observación óptica y registro continuo."],
    },
    "cloud": {
        "titulo": "Presencia de nubes — Estado de transición",
        "narracion": "Se observa cobertura nubosa moderada. El sistema indica un cambio gradual en la dinámica atmosférica local. Aunque no se detectan señales de tormenta inmediata, la evolución del cielo debe seguirse con atención para descartar cambios rápidos.",
        "recomendaciones": ["Revisar datos de presión y temperatura si están disponibles.", "Programar captura adicional en intervalo corto (15-30 min)."],
    },
    "storm": {
        "titulo": "Alerta: Sistema de tormenta detectado",
        "narracion": "El análisis de la imagen indica formación de sistemas de tormenta. Las características observadas (densidad, contraste y distribución espacial de las nubes) coinciden con patrones de inestabilidad atmosférica que pueden derivar en eventos de precipitación intensa o descargas.",
        "recomendaciones": ["Activar protocolo de alertas en sistemas conectados.", "Notificar a operadores locales si la cámara está vinculada a un observatorio o servicio meteorológico."],
    },
    "precipitable": {
        "titulo": "Alerta alta: Nubes con alta probabilidad de precipitación",
        "narracion": "Las características visuales de la nube observada —alta densidad óptica, textura homogénea y baja reflectancia relativa— corresponden a sistemas con alta probabilidad de precipitación activa o inminente. Se recomienda considerar medidas preventivas en zonas expuestas.",
        "recomendaciones": ["Activar protocolos de seguridad en instalaciones expuestas.", "Coordinar con servicios meteorológicos locales para verificación cruzada."],
    },
}


def generate_llm_narrative(alert: dict) -> str:
    """Intenta usar LLM (Gemini); si falla o no está disponible, retorna vacío."""
    if not LLM_AVAILABLE:
        return ""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""Eres un meteorólogo científico (estilo AI-Meteorologist, arXiv 2512.11819).
Escribe un breve párrafo narrativo científico (2-3 oraciones) sobre el cielo observado.
Datos:
- Tipo de nube: {alert.get('cloud_name', 'desconocido')}
- Confianza del modelo: {alert.get('confidence', 0)}
- Nivel de alerta: {alert.get('level', 'NONE')}
- Razón de la alerta: {alert.get('reason', 'N/A')}
No inventes datos adicionales. Usa solo los datos proporcionados para fundamentar la narración."""
        response = model.generate_content(prompt)
        text = response.text if hasattr(response, "text") else str(response)
        return text.strip()
    except Exception as e:
        return ""


def build_report(alert: dict, llm_text: str = "") -> str:
    """Construye el archivo forecast_report.md (S4)."""
    cloud_name = alert.get("cloud_name", "clear")
    level = alert.get("level", "NONE")
    confidence = alert.get("confidence", 0)
    reason = alert.get("reason", "")
    timestamp = alert.get("evaluated_at", datetime.now().isoformat())
    image_id = alert.get("image_id", "unknown")

    # Template rules (grounded)
    template = NARRATIVES.get(cloud_name, NARRATIVES["clear"])
    if cloud_name == "clear" and level in ("LOW", "HIGH"):
        # Si hay alerta pero el tipo es clear, usar el contexto de alerta
        pass

    # Sección narrativa: LLM primero si existe y es coherente; si no, rules
    if llm_text and len(llm_text) > 30:
        narracion = llm_text
    else:
        narracion = template["narracion"]

    # Si hay alerta activa, reforzar con contexto de la alerta
    if level != "NONE":
        narracion += f"\n\nNota de alerta ({level}): {reason}"
    else:
        narracion += "\n\nEstado de alerta: Ninguna alerta activa en este momento."

    # Recomendaciones según nivel
    recomendaciones = template.get("recomendaciones", ["Monitoreo continuo recomendado."])
    if level == "HIGH":
        recomendaciones.extend(["Priorizar notificación a autoridades locales.", "Considerar suspensión de actividades expuestas."])
    elif level == "LOW":
        recomendaciones.extend(["Aumentar frecuencia de captura para confirmar evolución.", "Revisar condiciones de viento y temperatura si están disponibles."])

    md = f"""# Forecast Report — FeatureUnivision (SkyPulseAR)

**Fecha de generación**: {timestamp}  
**Imagen analizada**: `{image_id}`  
**Tipo de nube detectado**: `{cloud_name}` (tipo={alert.get('cloud_type', '?')})  
**Confianza del modelo**: `{confidence}`  
**Nivel de alerta**: `{level}`  

---

## 1. Descripción del cielo observado

{narracion}

---

## 2. Estado de la alerta

- **Nivel**: `{level}`
- **Razón**: {reason if reason else "Sin alerta activa; condiciones estables o dentro de umbrales normales."}
- **Disparador**: {'Sí — cambio detectado en frames consecutivos' if alert.get('triggered') else 'No — evaluación independiente'}

---

## 3. Recomendaciones

"""
    for idx, rec in enumerate(recomendaciones, 1):
        md += f"- {idx}. {rec}\n"

    md += "\n---\n\n## 4. Notas técnicas\n\n"
    md += f"- Modelo de segmentación: `{alert.get('model', 'stub_heuristic_v0')}` (reemplazar por ACLNet / EfficientNet-B0+ASPP con PyTorch).\n"
    md += f"- Fuente del dataset: All-Sky camera + benchmark DeepSky / FY-4A-Himawari-8.\n"
    md += f"- Diseño de referencia: `docs/superpowers/specs/univision_forecast_design_2026-10-27.md` (S4 — AI-Meteorologist style).\n"
    md += "\n---\n*Fin del reporte generado por FeatureUnivision — ForecastAgent (S4).\n"
    return md


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="ForecastAgent — Reporte narrativo del cielo (S4)")
    parser.add_argument("--alert", type=Path, required=True, help="JSON de alert_agent")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Directorio para guardar forecast_report.md")
    parser.add_argument("--try-llm", action="store_true", help="Intentar LLM (opcional, puede bloquear si hay latencia)")
    args = parser.parse_args()

    with open(args.alert, "r", encoding="utf-8") as f:
        alert_data = json.load(f)

    llm_text = ""
    if args.try_llm and LLM_AVAILABLE:
        llm_text = generate_llm_narrative(alert_data)
        if llm_text:
            print("[ForecastAgent] LLM generó narración; usando como base.")
        else:
            print("[ForecastAgent] LLM falló; usando rules (grounded forecasting).")
    else:
        if args.try_llm:
            print("[ForecastAgent] --try-llm solicitado pero LLM no disponible; usando rules.")
        else:
            print("[ForecastAgent] Modo rules (default); no se intentó LLM.")

    report_md = build_report(alert_data, llm_text)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Nombre de archivo: forecast_report_{timestamp}_{image_id}.md
    timestamp_part = alert_data.get("evaluated_at", datetime.now().strftime("%Y%m%d_%H%M%S"))[:19].replace(":", "")
    image_part = alert_data.get("image_id", "unknown")[:16]
    filename = args.output_dir / f"forecast_report_{timestamp_part}_{image_part}.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"[ForecastAgent] Reporte guardado: {filename}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
