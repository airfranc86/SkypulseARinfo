#!/usr/bin/env python3
"""
SegmentationAgent — Stub para PyTorch / ACLNet / DeepSky

Estado: PLACEHOLDER (PyTorch no instalado en este entorno).
Reemplazar cuerpo de classify_frame() por:
  model = torch.load("models/aclnet.pt")
  ... inferencia ...

Interfaz definida por el diseño (S2):
  classify_frame(image_path: Path) -> dict
  Entrada: PNG frame (640x480 o similar)
  Salida: {"image_id": ..., "cloud_type": int, "confidence": float,
           "mask": Optional[str]}
"""

import argparse
from pathlib import Path
from PIL import Image, ImageStat
import json
import uuid
from datetime import datetime

# ============================================================
# Interfaz requerida (S2 — Design Spec)
# ============================================================


def classify_frame(image_path: Path) -> dict:
    """
    STUB — reemplazar con PyTorch ACLNet / EfficientNet-B0+ASPP
    cuando torch esté disponible.

    Heurística temporal (solo para que el pipeline funcione):
    - Calcula color medio y detecta nubes por saturación/valor.
    - Devuelve clasificación aproximada (clear / cloud / storm / precipitable).
    """
    try:
        img = Image.open(image_path).convert("RGB")
        stat = ImageStat.Stat(img)
        r, g, b = stat.mean[:3]
        gray = (r + g + b) / 3.0
        # Heurística simple: si es muy claro → cloud; si gris oscuro → storm; etc.
        if gray > 220:
            cloud_type = 0  # clear
            conf = 0.85
        elif gray > 190:
            cloud_type = 1  # cloud
            conf = 0.72
        elif gray > 150:
            cloud_type = 2  # storm
            conf = 0.65
        else:
            cloud_type = 3  # precipitable / heavy
            conf = 0.55
    except Exception as e:
        cloud_type = 0
        conf = 0.1

    # Genera frame_id de nombre del archivo o UUID
    frame_id = image_path.stem.split("_")[-1] if "_" in image_path.name else uuid.uuid4().hex[:8]
    return {
        "image_id": frame_id,
        "cloud_type": cloud_type,
        "cloud_type_name": ["clear", "cloud", "storm", "precipitable"][cloud_type],
        "confidence": round(conf, 3),
        "mask": None,
        "source_image": str(image_path),
        "classified_at": datetime.now().isoformat(),
        "model": "stub_heuristic_v0",
        "note": "Reemplazar por ACLNet / EfficientNet-B0+ASPP (PyTorch) cuando torch esté disponible.",
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="SegmentationAgent - Stub")
    parser.add_argument("--image", type=Path, required=True, help="Path al frame PNG")
    parser.add_argument("--output", type=Path, default=None, help="JSON de salida (opcional)")
    args = parser.parse_args()

    result = classify_frame(args.image)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        print(f"[SegmentationAgent] Guardado: {args.output}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
