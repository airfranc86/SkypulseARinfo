#!/usr/bin/env python3
"""
AlertAgent — Reglas de alerta (S3 — Diseño FeatureUnivision)

Uso:
  python scripts/alert_agent.py --input <json_de_segmentation> [--prev <prev_json>]
  python scripts/segmentation_agent.py --image dataset_frames/... | python scripts/alert_agent.py

Thresholds (definidos en diseño S3):
  - cloud_type == 1 (storm) + confidence > 0.6  -> LOW
  - cloud_type == 2 (precipitable) + confidence > 0.7 -> HIGH
  - cambio normal -> storm en frames consecutivos -> TRIGGER
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
import sys

# ============================================================
# Reglas (S3)
# ============================================================

THRESHOLDS = {
    1: {"level": "LOW", "min_confidence": 0.60},    # storm
    2: {"level": "HIGH", "min_confidence": 0.70},  # precipitable
}


# ============================================================
# Core
# ============================================================

def evaluate_alert(classification: dict, previous: dict = None) -> dict:
    """Devuelve dict de alerta según clasificación actual (+ anterior si hay)."""
    cloud_type = classification.get("cloud_type", 0)
    confidence = classification.get("confidence", 0.0)
    image_id = classification.get("image_id", "unknown")
    cloud_name = classification.get("cloud_type_name", ["clear", "cloud", "storm", "precipitable"][cloud_type] if isinstance(cloud_type, int) else "unknown")

    # Evaluar umbrales
    level = None
    reason = ""
    if isinstance(cloud_type, int) and cloud_type in THRESHOLDS:
        spec = THRESHOLDS[cloud_type]
        if confidence >= spec["min_confidence"]:
            level = spec["level"]
            reason = f"Tipo de nube '{cloud_name}' (tipo={cloud_type}) con confianza {confidence:.2f} supera umbral {spec['min_confidence']}"

    # ALERTA TRIGGER: cambio de "clear/cloud" (0/1) -> storm (1) o normal -> high
    triggered = False
    if previous:
        prev_cloud = previous.get("cloud_type", 0)
        prev_name = previous.get("cloud_type_name", ["clear", "cloud", "storm", "precipitable"][prev_cloud] if isinstance(prev_cloud, int) else "unknown")
        prev_level = previous.get("alert_level", "NONE")
        # Trigger si pasa de no-alerta a alerta (o baja -> alta)
        if prev_level == "NONE" and level is not None:
            triggered = True
            reason = f"TRIGGER: Cambio de '{prev_name}' (no alerta) a '{cloud_name}' (alerta {level}) en frame consecutivo."
        # También trigger si aumenta nivel
        elif prev_level == "LOW" and level == "HIGH":
            triggered = True
            reason = f"TRIGGER: Aumento de LOW -> HIGH: '{prev_name}' -> '{cloud_name}'."

    alert = {
        "alert_id": f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:20]}",
        "image_id": image_id,
        "level": level if level else "NONE",
        "triggered": triggered,
        "reason": reason,
        "cloud_type": cloud_type,
        "confidence": confidence,
        "cloud_name": cloud_name,
        "evaluated_at": datetime.now().isoformat(),
    }
    return alert


def save_alert(alert: dict, output_dir: Path = None) -> Path:
    out_dir = output_dir or (Path(__file__).parent.parent / "alerts")
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"alert_{alert['alert_id'].split('_')[-1]}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(alert, f, indent=2, ensure_ascii=False)
    return filename


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AlertAgent — Reglas de alerta (S3)")
    parser.add_argument("--input", type=Path, required=True, help="JSON de segmentation_agent")
    parser.add_argument("--prev", type=Path, default=None, help="JSON anterior (opcional, para detectar TRIGGER)")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directorio para guardar alertas JSON")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        classification = json.load(f)

    previous = None
    if args.prev:
        with open(args.prev, "r", encoding="utf-8") as f:
            previous = json.load(f)

    alert = evaluate_alert(classification, previous)
    print(json.dumps(alert, indent=2, ensure_ascii=False))

    out_path = save_alert(alert, args.output_dir)
    print(f"[AlertAgent] Alerta guardada: {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
