import { ApiError, type DensityAltitudeRequest, type DensityRisk } from '@/lib/api'
import riskMessages from '@/lib/riskMessages.json'

/** Copy del fallo de red en lenguaje del producto; nunca el "HTTP 502" crudo. */
export function describeServerError(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return error.retryAfter
      ? `Demasiadas consultas seguidas. Reintentá en ${error.retryAfter} s.`
      : 'Demasiadas consultas seguidas.'
  }
  if (error instanceof ApiError && error.status >= 500) return 'El servidor no respondió.'
  if (error instanceof DOMException && error.name === 'AbortError') return 'El servidor tardó demasiado.'
  return 'No pudimos contactar al servidor.'
}

/**
 * Estimación local de Altitud de Densidad (regla FAA, sin humedad) usada como
 * fallback fail-open mientras el backend despierta.
 *
 * Es un espejo REDUCIDO de app/services/aeronautica.py: misma altitud de
 * presión, misma desviación ISA y mismas reglas operacionales, pero sin la
 * corrección por temperatura virtual. Por eso SUBESTIMA la altitud de densidad
 * en aire húmedo — la UI debe marcarlo siempre como estimación.
 */

/**
 * Copia de los mensajes aprobados del backend (_RISK_INFO). El test
 * test_risk_messages_match_frontend_copy falla si divergen.
 */
export const RISK_MESSAGES: Record<DensityRisk, string> = riskMessages

/**
 * La estimación local nunca sobreestima la DA (omite la humedad, que solo la
 * sube) y el riesgo crece con la DA: un naranja o rojo estimado es un piso que
 * el servidor solo puede confirmar o subir. Verde y amarillo, en cambio, pueden
 * empeorar, así que no deben tranquilizar.
 */
export function isEstimateFloor(risk: DensityRisk): boolean {
  return risk === 'naranja' || risk === 'rojo'
}

export function requestsEqual(a: DensityAltitudeRequest, b: DensityAltitudeRequest): boolean {
  return (Object.keys(a) as (keyof DensityAltitudeRequest)[]).every(key => a[key] === b[key])
}

const FT_PER_HPA = 30
const FT_PER_DEG_C = 118.8

export interface DensityEstimate {
  densityAltitudeFt: number
  pressureAltitudeFt: number
  sigma: number
  tasKt: number
  /** Índice operacional wl_nom / sigma (no el wing loading físico). */
  adjustedWingLoading: number
  flareLossPct: number
  takeoffRunIncreasePct: number
  enginePowerLossPct: number | null
  risk: DensityRisk
}

/**
 * Espejo de classify_risk() del backend. Precedencia (gana la primera que aplica):
 * rojo: índice > 1.35×nominal o DA > 9.000 · naranja: índice > 1.25×nominal o
 * 6.000 <= DA <= 9.000 · amarillo: índice > 1.10×nominal o 3.000 <= DA < 6.000 ·
 * verde: el resto. En el borde compartido de 6.000 ft se escala a naranja.
 */
export function classifyRisk(adjustedWl: number, wlNom: number, daFt: number): DensityRisk {
  if (adjustedWl > 1.35 * wlNom || daFt > 9000) return 'rojo'
  if (adjustedWl > 1.25 * wlNom || daFt >= 6000) return 'naranja'
  if (adjustedWl > 1.1 * wlNom || daFt >= 3000) return 'amarillo'
  return 'verde'
}

export function estimateDensityAltitude(input: DensityAltitudeRequest): DensityEstimate {
  const pressureAltitudeFt = input.elev_ft + FT_PER_HPA * (1013.25 - input.qnh_hpa)
  const isaTempC = 15 - 1.98 * (pressureAltitudeFt / 1000)
  const densityAltitudeFt = pressureAltitudeFt + FT_PER_DEG_C * (input.oat_c - isaTempC)

  const sigma = (1 - 6.8756e-6 * densityAltitudeFt) ** 4.2561
  const daK = Math.max(0, densityAltitudeFt / 1000)

  return {
    densityAltitudeFt,
    pressureAltitudeFt,
    sigma,
    tasKt: input.ias_kt / Math.sqrt(sigma),
    adjustedWingLoading: input.wl_nom / sigma,
    flareLossPct: 4 * daK,
    takeoffRunIncreasePct: 10 * daK,
    enginePowerLossPct: input.aircraft_model === 'piston' ? 3.5 * daK : null,
    risk: classifyRisk(input.wl_nom / sigma, input.wl_nom, densityAltitudeFt),
  }
}

/** Incremento porcentual de TAS respecto de IAS: 1/√σ − 1. */
export function tasIncreasePct(sigma: number): number {
  return (1 / Math.sqrt(sigma) - 1) * 100
}

export interface RiskMeta {
  label: string
  summary: string
  color: string
  /** Grosor del borde del contenedor — escala con la gravedad (además del color). */
  borderPx: number
  glow: string
}

/** Colores alineados a la escala semántica de index.css (safe / watch / crit). */
export const RISK_META: Record<DensityRisk, RiskMeta> = {
  // Grosores enteros: en pantallas de DPR 1 el navegador redondea 1.5px a 1px.
  verde:    { label: 'Riesgo verde',    summary: 'Sin degradación relevante',  color: '#3ecf7a', borderPx: 1, glow: 'none' },
  amarillo: { label: 'Riesgo amarillo', summary: 'Degradación moderada',       color: '#e6c84a', borderPx: 2, glow: 'none' },
  naranja:  { label: 'Riesgo naranja',  summary: 'Degradación importante',     color: '#f0a030', borderPx: 3, glow: '0 0 18px rgba(240,160,48,0.22)' },
  rojo:     { label: 'Riesgo rojo',     summary: 'Degradación severa',         color: '#ff3333', borderPx: 4, glow: '0 0 26px rgba(255,51,51,0.32)' },
}

export interface DensityFormValues {
  elev_ft: string
  qnh_hpa: string
  oat_c: string
  td_c: string
  wl_nom: string
  ias_kt: string
  aircraft_model: DensityAltitudeRequest['aircraft_model']
}

export type DensityFieldErrors = Partial<Record<keyof DensityFormValues, string>>

interface FieldRule {
  key: Exclude<keyof DensityFormValues, 'aircraft_model'>
  label: string
  min: number
  max: number
  exclusiveMin?: boolean
}

// Mismos rangos que DensityAltitudeRequest en el backend.
const FIELD_RULES: FieldRule[] = [
  { key: 'elev_ft', label: 'Elevación', min: -1000, max: 20000 },
  { key: 'qnh_hpa', label: 'QNH', min: 850, max: 1085 },
  { key: 'oat_c', label: 'Temperatura', min: -60, max: 60 },
  { key: 'td_c', label: 'Punto de rocío', min: -80, max: 40 },
  { key: 'wl_nom', label: 'Wing loading', min: 0, max: 10, exclusiveMin: true },
  { key: 'ias_kt', label: 'Velocidad indicada', min: 0, max: 250, exclusiveMin: true },
]

export function parseDensityForm(
  values: DensityFormValues,
): { ok: true; request: DensityAltitudeRequest } | { ok: false; errors: DensityFieldErrors } {
  const errors: DensityFieldErrors = {}
  const parsed: Partial<Record<FieldRule['key'], number>> = {}

  for (const rule of FIELD_RULES) {
    const raw = values[rule.key].trim().replace(',', '.')
    const n = raw === '' ? NaN : Number(raw)
    const belowMin = rule.exclusiveMin ? n <= rule.min : n < rule.min
    if (!Number.isFinite(n)) {
      errors[rule.key] = `${rule.label}: ingresá un número.`
    } else if (belowMin || n > rule.max) {
      const lower = rule.exclusiveMin ? `mayor que ${rule.min}` : `desde ${rule.min}`
      errors[rule.key] = `${rule.label}: ${lower} hasta ${rule.max}.`
    } else {
      parsed[rule.key] = n
    }
  }

  if (
    errors.td_c === undefined &&
    errors.oat_c === undefined &&
    parsed.td_c !== undefined &&
    parsed.oat_c !== undefined &&
    parsed.td_c > parsed.oat_c
  ) {
    errors.td_c = 'El punto de rocío no puede superar la temperatura.'
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors }

  return {
    ok: true,
    request: {
      elev_ft: parsed.elev_ft as number,
      qnh_hpa: parsed.qnh_hpa as number,
      oat_c: parsed.oat_c as number,
      td_c: parsed.td_c as number,
      wl_nom: parsed.wl_nom as number,
      ias_kt: parsed.ias_kt as number,
      aircraft_model: values.aircraft_model,
    },
  }
}
