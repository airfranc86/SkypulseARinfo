"""Write the run results: resumen.md, CSV files and metadatos.json (no local paths)."""

from __future__ import annotations

import csv
import datetime as dt
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from aggregation import Window
from combos import FoldResult
from metrics import ErrorRecord
from openmeteo_client import MODEL_IDS, PARAMETER_VERSION
from pipeline import FoldStationSummary, MeasurementResult
from report import (
    coverage_table,
    fold_section,
    improvement_table,
    station_delta_table,
    stats_table,
    window_ranking_table,
)

_FOLD_TITLES = {
    "fold_1": "Pliegue 1 (entrena con la primera mitad, prueba con la segunda)",
    "fold_2": "Pliegue 2 (entrena con la segunda mitad, prueba con la primera)",
}
_CASE_HEADER = (
    "pliegue", "estacion", "fecha", "anticipacion_dias", "variable", "modelo",
    "pronostico", "observado", "error",
)  # fmt: skip
_STATION_HEADER = (
    "pliegue", "estacion", "variable", "anticipacion_dias", "modelo", "n",
    "mae_modelo", "mae_mean", "diferencia", "mejora_umbral",
)  # fmt: skip


def _window_meta(window: Window, forced: bool) -> dict[str, object]:
    return {
        "nombre": window.name,
        "hora_inicio_utc": window.start_hour_utc,
        "desfase_dias": window.day_offset,
        "horas": window.length_hours,
        "forzada": forced,
    }


def build_metadata(
    result: MeasurementResult,
    http_calls: int,
    cache_hits: int,
    chunk_days: int,
    regtemp_file: str,
    now: dt.datetime,
) -> dict[str, object]:
    """Run metadata; only file base names, never absolute paths."""
    choice = result.window_choice
    return {
        "fecha_corrida": now.isoformat(timespec="seconds"),
        "periodo": {"inicio": result.start.isoformat(), "fin": result.end.isoformat()},
        "ventanas": {
            "tmax": _window_meta(choice.tmax, choice.tmax_forced),
            "tmin": _window_meta(choice.tmin, choice.tmin_forced),
        },
        "ventanas_coinciden_entre_modelos": choice.models_agree,
        "modelos": dict(MODEL_IDS),
        "parametros_version": PARAMETER_VERSION,
        "llamadas_http": http_calls,
        "llamadas_cache": cache_hits,
        "chunk_dias": chunk_days,
        "min_horas_validas": result.min_valid_hours,
        "umbral_mejora_c": result.threshold,
        "regtemp_archivo": regtemp_file,
        "estaciones": [
            {
                "nombre": s.smn_name,
                "icao": s.icao,
                "wmo_id": s.wmo_id,
                "parcial": s.partial_coverage,
            }
            for s in result.stations
        ],
    }


def _window_section(result: MeasurementResult) -> list[str]:
    choice = result.window_choice
    agree = "sí" if choice.models_agree else "no"
    lines = [
        "## Ventana horaria del SMN",
        "",
        f"Ventana elegida para Tmax: **{choice.tmax.name}**; para Tmin: **{choice.tmin.name}** "
        "(24 h desde esa hora UTC; `D-1` indica que empieza el día UTC anterior).",
        f"ECMWF y GFS coinciden en la mejor ventana: {agree}.",
        "",
    ]
    for variable, label in (("tmax", "Tmax"), ("tmin", "Tmin")):
        lines += [f"### Ranking de ventanas para {label} (modelos combinados)", ""]
        lines += [window_ranking_table(getattr(choice.ranking, variable)), ""]
        for ranking in choice.per_model:
            best = getattr(ranking, variable)[0]
            lines.append(f"- Mejor ventana con {ranking.model}: {best.window.name}")
        lines.append("")
    return lines


def _station_section(summaries: Sequence[FoldStationSummary], threshold: float) -> list[str]:
    lines = [
        "## Estaciones que mejoran frente a mean",
        "",
        f"Una estación mejora si su MAE baja al menos {threshold:.2f} °C respecto de `mean`.",
        "",
    ]
    for summary in summaries:
        title = _FOLD_TITLES.get(summary.fold_name, summary.fold_name)
        lines += [f"#### {title}", "", improvement_table(summary.by_lead.counts), ""]
        lines += ["Todas las anticipaciones juntas:", ""]
        lines += [improvement_table(summary.pooled.counts), ""]
        lines += ["Detalle por estación (todas las anticipaciones):", ""]
        lines += [station_delta_table(summary.pooled.deltas), ""]
    return lines


def render_summary(result: MeasurementResult, metadata: Mapping[str, object]) -> str:
    """The full Spanish markdown report."""
    lines = [
        "# Verificación de Tmax/Tmin: ECMWF, GFS y combinaciones",
        "",
        f"Período objetivo: {result.start} a {result.end}. Estaciones: {len(result.stations)}. "
        f"Corrida: {metadata['fecha_corrida']}. "
        f"Llamadas HTTP: {metadata['llamadas_http']} (desde caché: {metadata['llamadas_cache']}).",
        "",
        "## Advertencias",
        "",
        *[f"- {w}" for w in result.warnings],
        "",
        *_window_section(result),
        "## Cobertura por estación",
        "",
        coverage_table(result.coverage),
        "",
        "## Resultados sin ajuste (todo el período)",
        "",
        "Error = pronóstico - observado, en °C; `mean` es la media simple de ECMWF y GFS.",
        "",
        stats_table(result.overall_rows),
        "",
        "## Validación cruzada de 2 pliegues",
        "",
        "El ajuste (sesgo, pesos) usa solo el período de entrenamiento "
        "y la medición solo el de prueba.",
        "",
    ]
    for fold in result.folds:
        lines += [fold_section(fold, _FOLD_TITLES.get(fold.name, fold.name)), ""]
    lines += _station_section(result.fold_summaries, result.threshold)
    return "\n".join(lines).rstrip() + "\n"


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _case_rows(folds: Sequence[FoldResult]) -> Iterable[Sequence[object]]:
    for fold in folds:
        for r in fold.records:
            yield _case_row(fold.name, r)


def _case_row(fold_name: str, r: ErrorRecord) -> Sequence[object]:
    return (
        fold_name, r.station, r.target_date.isoformat(), r.lead_days, r.variable, r.model,
        f"{r.forecast:.3f}", f"{r.observed:.3f}", f"{r.error:.3f}",
    )  # fmt: skip


def _station_rows(summaries: Sequence[FoldStationSummary]) -> Iterable[Sequence[object]]:
    for summary in summaries:
        for d in summary.by_lead.deltas:
            yield (
                summary.fold_name, d.station, d.variable, d.lead_days, d.model, d.n,
                f"{d.mae_model:.3f}", f"{d.mae_mean:.3f}", f"{d.mae_diff:.3f}",
                "si" if d.improves else "no",
            )  # fmt: skip


def write_outputs(
    result: MeasurementResult, out_dir: Path, metadata: Mapping[str, object]
) -> tuple[Path, ...]:
    """Write the four result files into ``out_dir`` (created if needed)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = out_dir / "resumen.md"
    cases = out_dir / "errores_por_caso.csv"
    stations = out_dir / "errores_por_estacion.csv"
    meta = out_dir / "metadatos.json"
    summary.write_text(render_summary(result, metadata), encoding="utf-8")
    _write_csv(cases, _CASE_HEADER, _case_rows(result.folds))
    _write_csv(stations, _STATION_HEADER, _station_rows(result.fold_summaries))
    meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return (summary, cases, stations, meta)

