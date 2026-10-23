#!/usr/bin/env python3
"""
DatasetAgent — Ingesta de frames All-Sky / Benchmark DeepSky

Uso:
  python scripts/dataset_agent.py --source local --input-dir ./my_sky_photos
  python scripts/dataset_agent.py --source synthetic --count 10
  python scripts/dataset_agent.py --source deepsky --download
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: Pillow no instalado. Ejecuta: pip install pillow")
    sys.exit(1)

# ============================================================
# Config
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent
DATASET_FRAMES_DIR = PROJECT_ROOT / "dataset_frames"
INDEX_FILE = DATASET_FRAMES_DIR / "dataset_index.jsonl"


# ============================================================
# Utilidades
# ============================================================
def ensure_dirs():
    DATASET_FRAMES_DIR.mkdir(parents=True, exist_ok=True)


def write_index_entry(entry: dict):
    """Añade una línea al índice JSONL."""
    with open(INDEX_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def generate_synthetic_frame(
    frame_id: str,
    width: int = 640,
    height: int = 480,
    cloud_type: str = "clear",
) -> Path:
    """Genera un frame sintético simple (solo para testing sin cámara real)."""
    img = Image.new("RGB", (width, height), color="lightblue")
    draw = ImageDraw.Draw(img)

    # Dibuja nubes simples según tipo
    if cloud_type == "storm":
        draw.ellipse([100, 100, 300, 250], fill="darkgray", outline="gray")
        draw.ellipse([350, 50, 550, 200], fill="gray", outline="darkgray")
    elif cloud_type == "precipitable":
        draw.ellipse([150, 150, 400, 350], fill="white", outline="lightgray")
        draw.ellipse([200, 100, 450, 300], fill="white", outline="lightgray")
    elif cloud_type == "cloud":
        draw.ellipse([200, 150, 450, 300], fill="white", outline="lightgray")

    # Texto informativo
    draw.text((10, 10), f"SYNTHETIC {cloud_type.upper()} - {frame_id}", fill="black")

    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{frame_id}.png"
    filepath = DATASET_FRAMES_DIR / filename
    img.save(filepath)
    return filepath


def ingest_local_directory(input_dir: Path, camera_id: str = "cam01") -> int:
    """Ingesta imágenes desde un directorio local (fotos All-Sky reales)."""
    count = 0
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff"):
        for img_path in input_dir.glob(ext):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            frame_id = uuid.uuid4().hex[:8]
            filename = f"{timestamp}_{camera_id}_{frame_id}.png"
            dest = DATASET_FRAMES_DIR / filename

            # Copia/convierte a PNG
            with Image.open(img_path) as img:
                img.save(dest, "PNG")

            entry = {
                "image_id": frame_id,
                "camera_id": camera_id,
                "timestamp": datetime.now().isoformat(),
                "source_path": str(img_path),
                "stored_path": str(dest.relative_to(PROJECT_ROOT)),
                "width": img.width,
                "height": img.height,
            }
            write_index_entry(entry)
            count += 1
            print(f"  [OK] Ingerido: {img_path.name} -> {filename}")
    return count


def ingest_synthetic(count: int, camera_id: str = "cam01") -> int:
    """Genera frames sintéticos para testing (clear/cloud/storm/precipitable)."""
    cloud_types = ["clear", "cloud", "storm", "precipitable"]
    n = 0
    for i in range(count):
        ct = cloud_types[i % len(cloud_types)]
        frame_id = uuid.uuid4().hex[:8]
        filepath = generate_synthetic_frame(frame_id, cloud_type=ct)

        entry = {
            "image_id": frame_id,
            "camera_id": camera_id,
            "timestamp": datetime.now().isoformat(),
            "source_path": "synthetic",
            "stored_path": str(filepath.relative_to(PROJECT_ROOT)),
            "width": 640,
            "height": 480,
            "synthetic_cloud_type": ct,
        }
        write_index_entry(entry)
        n += 1
        print(f"  [OK] Synthetic {ct}: {filepath.name}")
    return n


def download_deepsky_sample() -> int:
    """Descarga muestra de DeepSky (si hay red y el ZIP está disponible).

    Nota: El dataset DeepSky real está en Zenodo (8208504). Aquí solo
    creamos un placeholder; en producción usar pystac_client o wget.
    """
    print("  [INFO] DeepSky dataset real está en Zenodo: https://doi.org/10.5281/zenodo.8208504")
    print("  [INFO] Para usar: descarga manualmente y usa --source local --input-dir <path>")
    return 0


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="DatasetAgent - Ingesta de frames All-Sky")
    parser.add_argument(
        "--source",
        choices=["local", "synthetic", "deepsky"],
        default="synthetic",
        help="Fuente de imágenes",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Directorio con imágenes reales (para --source local)",
    )
    parser.add_argument(
        "--camera-id",
        default="cam01",
        help="ID de la cámara (metadata)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Número de frames sintéticos a generar",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Descargar muestra DeepSky (placeholder)",
    )

    args = parser.parse_args()
    ensure_dirs()

    print(f"[DatasetAgent] Fuente: {args.source}")
    print(f"[DatasetAgent] Guardando en: {DATASET_FRAMES_DIR}")
    print(f"[DatasetAgent] Índice: {INDEX_FILE}")

    total = 0
    if args.source == "local":
        if not args.input_dir or not args.input_dir.exists():
            print(f"ERROR: --input-dir requerido y debe existir: {args.input_dir}")
            sys.exit(1)
        total = ingest_local_directory(args.input_dir, args.camera_id)
    elif args.source == "synthetic":
        total = ingest_synthetic(args.count, args.camera_id)
    elif args.source == "deepsky":
        total = download_deepsky_sample()

    print(f"[DatasetAgent] Completado. Frames procesados: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())