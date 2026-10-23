# FeatureUnivision — Design Document

**Fecha**: 2026-10-27  
**Enfoque**: 2 (Balancedo) — Alertas en tiempo real + cálculo del forecast  
**Fuente**: All-Sky camera + FY-4A-Himawari-8 / DeepSky / ACLNet (PyTorch)  
**Purpose**: Detection cloud types in sky images + alerts + forecast narrativo (AI-Meteorologist style)

---

## 1. Specs (S#)

### S1 — DatasetAgent (Data Ingestion)
- **Goal**: Traer frames de All-Sky camera (o usar benchmark FY-4A-Himawari-8 / DeepSky) y guardarlos como `dataset_frames/` con metadatos (`timestamp, camera_id, filepath`).
- **Input**: Imagen All-Sky (path o numpy array) / dataset FYH (parquet / zip de arXiv DeepSky).
- **Output**: `dataset_frames/{timestamp}_{camera_id}.png` + JSON line con `{"image_id": ..., "camera_id": ..., "timestamp": ...}`.
- **Métricas**: `num_frames_ingested`, `frame_gap_seconds`.
- **Dependencias**: `torchvision.transforms`, `pillow`, `pandas`.

### S2 — segmentation-agent (Classification & Segmentation)
- **Goal**: Dado un frame, clasificar tipo de nube y producir bounding boxes / masks.
- **Modelo**: ACLNet (recomendado del paper "Let's Unleash the Network Judgment") o backbone EfficientNet-B0 + ASPP (del benchmark CloudVision). Entrenado con PyTorch sobre FY-4A/Himawari-8 o DeepSky.
- **Salida**: `{"image_id": ..., "cloud_type": int (0:Cloud, 1:Storm, 2:Precipitable), "mask": [RLE], "confidence": float}`.
- **Threshold**: Cloud > 0.5 → normal; Storm > 0.6 → alert; Precipitable > 0.7 → high alert.

### S3 — alert-agent (Rule-based Trigger)
- **Goal**: Revisar cada clasificación nueva y determinar si dispara una alerta.
- **Lógica**:
  - Si `cloud_type == 1` (Storm) y `confidence > 0.6` → **ALERTA LOW**.
  - Si `cloud_type == 2` (Precipitable) y `confidence > 0.7` → **ALERTA HIGH**.
  - Si cambio de clasificación de "normal" a "storm" en frames consecutivos → **ALERTA TRIGGER**.
- **Output**: JSON `{"alert_id": ..., "level": "LOW"|"HIGH", "triggered_at": ..., "reason": "...", "image_id": ...}`.

### S4 — forecast-agent (LLM + Reglas)
- **Goal**: Dada la alerta (o clasificación normal), producir un reporte narrativo meteorológico del cielo.
- **Input**: `{"alert": {...} | null, "latest_classification": {...}, "camera_view": "clear/stormy/rainy", "metadata": {...}}`.
- **LLM Prompt** (inspirado en AI-Meteorologist, arXiv 2512.11819):
  > "Dado el cielo observado a las HH:MM en ubicación X, las nubes observadas son [tipo], con probabilidad Y. El pronóstico indica [narración narrativa]. Si hay alerta Z, esta se debe a...".
- **Output**: `forecast_report.md` con estructura:
  - `timestamp`
  - `cloud_type_description`
  - `narrative_forecast`
  - `alert_status` (LOW/HIGH/NONE)
  - `recommended_actions`

### S5 — output-agent (Persistencia + Logging)
- **Goal**: Guardar cada reporte y log asociado.
- **Archivos**:
  - `output/univision_forecast_[YYYYMMDD_HHMMSS].md`
  - `logs/univision_agent_[YYYYMMDD_HHMMSS].log`
- **Notificación opcional**: soporte para `notify` channel (definido después, por defecto none).

---

## 2. Tasks

| ID | Tarea | S# | Descripción breve | Tiempo estimado |
|----|-------|----|-------------------|-----------------|
| T1 | **Configurar DatasetAgent** | S1 | Setup de ingestion pipeline (All-Sky + FY-4A / DeepSky); guardado de frames + JSONL. | 1 día |
| T2 | **Implementar segmentation-agent** | S2 | Cargar modelo ACLNet o EfficientNet-B0+ASPP (PyTorch); función de clasificación y máscara por frame. | 1.5 días |
| T3 | **Diseñar alert-agent** | S3 | Lógica de thresholds + tipos de alerta LOW/HIGH; generación de `alert_id`. | 0.5 días |
| T4 | **Desarrollar forecast-agent** | S4 | Configurar LLM (Gemini o OpenRouter Qwen) + prompt narrativo; reglas de storytelling del forecast. | 1.5 días |
| T5 | **Crear output-agent + tests** | S5 | Script que guarda `forecast_report.md` y `log` por ejecución; tests unitarios para cada agente. | 1 día |

**Total**: ~5.5 días de entrega (MVP).

---

## 3. Log (L1–L5)

- **L1**: 2026-10-27 original prompt: *"usar brainstorming y AlphaCode para investigar, sacar fotos de la universidad y cómo interpretar eso con PyTorch y otros langraph MLs"* (sesión evolvionnexus, tema cambiado a FeatureUnivision).
- **L2**: 2026-10-27 decisión B: tema cielo/clima (no universidad); fuente a+c (All-Sky + FY-4A-Himawari-8/Dataset).
- **L3**: 2026-10-27 selección: 2B (alertas en tiempo real) y 3C (forecast calculado).
- **L4**: 2026-10-27 brainstorming confirmado: enfoque 2 balanceado; dataset + segmentation + alert + forecast + output.
- **L5**: 2026-10-27 diseño documentado (este archivo) → paso a implementation plan.

---

## 4. Implementation Plan (next steps)

1. **Crear entorno** `uv venv && uv add torch torchvision pillow pandas langgraph google-generativeai`.
2. **Clonar modelo** (o descargar `DeepSky` / `ACLNet` weights) a `FeatureUnivision/scripts/weights/`.
3. **Implementar T1**: DatasetAgent básico que lea frames y los guarde.
4. **Implementar T2**: segmentation-agent con modelo PyTorch pre-entrenado (usar `torch.hub` o weights locales).
5. **Implementar T3**: alert-agent con thresholds simples.
6. **Implementar T4**: forecast-agent usando Gemini / Qwen via OpenRouter + prompt estructurado.
7. **Implementar T5**: output-agent + tests; `uv run pytest tests/` en repo.
8. **Validación end-to-end**: Ejecutar `python main.py --image <path>` → debe imprimir `forecast_report.md` con clasificación y alerta.

---

**Risk**: medio. Los riesgos principales son:
- Fallo de integración PyTorch en este entorno (TensorRT / GPU limitante) → mitigar con CPU-only modelos ligeros (EfficientNet-B0).
- Hallucination en el LLM forecast → mitigar con *grounding* en clasificación real (usar clasificación real como *facts* en el prompt).

--- 

*Fin del diseño.*