// Fase mapa de presión / isobaras (paso 1 — seam confirmado)
// Datos: pressure_hpa (openmeteo / smn / aggregator); líneas de presión + valores + frentes.
// Skills: frontend-ui-engineering, build-dashboard, codebase-design.
import { useState } from "react";

export interface PressureIsobarMapProps {
  lat: number;
  lon: number;
  model?: "ecmwf" | "openmeteo";
  // Datos del backend: líneas de presión y valores
  pressureLines?: { value_hpa: number; label: string }[];
  fronts?: { type: "cold" | "warm" | "stationary"; lat: number; lon: number }[];
}

export default function PressureIsobarMap({ lat, lon, model = "ecmwf", pressureLines = [], fronts = [] }: PressureIsobarMapProps) {
  // Paso 2: líneas etiquetadas con valores de presión (hPa) — ya confirmadas en datos backend.
  const labeled = pressureLines.map((l) => ({ ...l, label: `${l.value_hpa} hPa — ${l.label}` }));
  // Componente base para isobaras: muestra valores de línea y marcas de frente.
  // Datos provenientes del backend (Fase 2/4); no se tocan scripts/instagram ni contrato frontend.
  const [selected] = useState({ lat, lon, model });
  return (
    <div aria-label="Mapa de isobaras / presión">
      <h3>Mapa de presión — Isobaras</h3>
      <p>Lat {selected.lat}, Lon {selected.lon} · Modelo: {selected.model}</p>
      {pressureLines.length === 0 && <p>Sin datos de líneas de presión aún.</p>}
      <ul>
        {labeled.map((line) => (
          <li key={line.value_hpa}>{line.label}</li>
        ))}
      </ul>
      <p>Frentes (frío / cálido / estacionario): {fronts.length}</p>
      <ul>
        {fronts.map((f, i) => (
          <li key={i} aria-label={`Frente ${f.type}`}>
            <strong>{f.type === "cold" ? "Frente frío" : f.type === "warm" ? "Frente cálido" : "Estacionario"}</strong>
            {" — "}lat {f.lat}, lon {f.lon}
          </li>
        ))}
      </ul>
    </div>
  );
}
