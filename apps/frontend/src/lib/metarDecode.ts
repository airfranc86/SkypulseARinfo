// Textos de las tarjetas del METAR decodificado (FRA-367, parte 2), como funciones puras.
//
// Salen de `Metar.tsx` para poder probarlas con `node --test` y para no seguir engordando esa página.
// Dos reglas de fondo:
// - Cuando el texto del METAR (`raw_text`) y el dato decodificado de CheckWX difieren, manda el texto
//   del METAR: CheckWX convierte unidades y agrega decimales (Q1008 aparece como 1008.1 hPa).
// - Las categorías de vuelo se miden en millas terrestres (FAA), como en el TAF; con su equivalente en km.

import { parseObservedAt } from './windShearHelpers.ts'
import { formatLocalInstant } from './taf.ts'
import { cloudBaseFeet, cloudBaseText, cloudType, type CloudLayerData } from './cloudBase.ts'

const SM_IN_METERS = 1609.344
const HPA_PER_INHG = 33.8639

// ------------------------------------------------------------------ viento

export interface MetarWindData {
  degrees?: number
  direction?: string
  speed_kts?: number
  gust_kts?: number
  speed?: number
}

const VARIABLE_WIND_RE = /\bVRB\d{2,3}(?:G\d{2,3})?(?:KT|MPS)\b/
const WIND_RANGE_RE = /\b(\d{3})V(\d{3})\b/

const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

export function windDisplay(
  wind: MetarWindData | undefined,
  rawText: string | undefined,
): { value: string; note: string } | null {
  if (!wind) return null
  const raw = rawText ?? ''
  const speed = isFiniteNumber(wind.speed_kts) ? wind.speed_kts : isFiniteNumber(wind.speed) ? wind.speed : null
  const gust = isFiniteNumber(wind.gust_kts) && wind.gust_kts > 0 ? wind.gust_kts : null
  const degrees = isFiniteNumber(wind.degrees) ? wind.degrees : null

  if (speed === 0 && gust === null) return { value: 'Calmo', note: 'Sin viento' }

  const variable = VARIABLE_WIND_RE.test(raw) || degrees === null
  const speedText = `${speed ?? '?'} kt${gust === null ? '' : ` G${gust}`}`
  const value = variable ? `Variable / ${speedText}` : `${String(Math.round(degrees)).padStart(3, '0')}° / ${speedText}`

  const parts = [gust === null ? 'Sin ráfagas reportadas' : `Ráfagas de ${gust} kt — atención al despegue y aterrizaje`]
  const range = WIND_RANGE_RE.exec(raw)
  if (variable) parts.push('Dirección variable (VRB)')
  else if (range) parts.push(`La dirección varía entre ${range[1]}° y ${range[2]}°`)
  return { value, note: parts.join(' · ') }
}

// ------------------------------------------------------------------ visibilidad y categorías

/** Nota de la visibilidad con los límites FAA (millas); antes usaba cortes en metros que daban otra categoría. */
export function visibilityNote(meters: number | null): string {
  if (meters === null) return ''
  if (meters >= 9999) return 'Excelente visibilidad — VFR sin restricciones'
  const miles = meters / SM_IN_METERS
  if (miles > 5) return 'Buena visibilidad — VFR (más de 5 millas)'
  if (miles >= 3) return 'Visibilidad reducida — MVFR (3 a 5 millas)'
  if (miles >= 1) return 'Visibilidad baja — IFR (1 a 3 millas)'
  return 'Visibilidad muy baja — LIFR (menos de 1 milla), condiciones críticas'
}

export interface FlightCategoryRule {
  cat: 'VFR' | 'MVFR' | 'IFR' | 'LIFR'
  sub: string
  ceiling: string
  vis: string
  note: string
}

/** Las cuatro tarjetas de "Categorías de vuelo": millas con su equivalente en km (no millas rotuladas como km). */
export const FLIGHT_CATEGORY_RULES: readonly FlightCategoryRule[] = [
  { cat: 'VFR', sub: 'Visual Flight Rules', ceiling: 'Techo sobre 3.000 ft', vis: 'Visib. más de 5 millas (8 km)', note: 'Vuelo visual sin restricciones' },
  { cat: 'MVFR', sub: 'Marginal VFR', ceiling: 'Techo 1.000 a 3.000 ft', vis: 'Visib. 3 a 5 millas (4,8 a 8 km)', note: 'Condiciones límite VFR' },
  { cat: 'IFR', sub: 'Instrument Flight Rules', ceiling: 'Techo 500 a 999 ft', vis: 'Visib. 1 a 3 millas (1,6 a 4,8 km)', note: 'Solo vuelo instrumental' },
  { cat: 'LIFR', sub: 'Low IFR', ceiling: 'Techo menos de 500 ft', vis: 'Visib. menos de 1 milla (1,6 km)', note: 'Condiciones muy severas' },
]

// ------------------------------------------------------------------ temperatura y rocío

export function dewpointText(tempC: number | null | undefined, dewC: number | null | undefined): string {
  if (!isFiniteNumber(tempC)) return ''
  return isFiniteNumber(dewC) ? `${tempC}°C / Rocío ${dewC}°C` : `${tempC}°C`
}

export function temperatureNote(tempC: number | null | undefined, dewC: number | null | undefined): string {
  if (!isFiniteNumber(tempC) || !isFiniteNumber(dewC)) return 'Temperatura registrada'
  const spread = Number(Math.abs(tempC - dewC).toFixed(1))
  return `Diferencia Temp–Rocío: ${spread}°C${spread < 3 ? ' — riesgo de niebla' : ''}`
}

// ------------------------------------------------------------------ QNH

/** QNH en hPa enteros: de `Q1008` (o `A2992` en pulgadas) del texto del METAR; si no hay, el dato decodificado redondeado. */
export function qnhHpa(rawText: string | undefined, decodedHpa: number | null | undefined): number | null {
  const raw = rawText ?? ''
  const hpa = /\bQ(\d{4})\b/.exec(raw)
  if (hpa) return Number(hpa[1])
  const inches = /\bA(\d{4})\b/.exec(raw)
  if (inches) return Math.round((Number(inches[1]) / 100) * HPA_PER_INHG)
  return isFiniteNumber(decodedHpa) ? Math.round(decodedHpa) : null
}

/**
 * Límites del texto de presión (hPa, nivel del mar): baja bajo 1009, normal de 1009 a 1022, alta desde 1023
 * (la convención de los barómetros: 29,80 a 30,20 inHg). Los extremos, 980 y 1030, ya estaban en el sitio.
 * La referencia formal es la atmósfera estándar (1013,25 hPa).
 */
export function qnhNote(hpa: number | null): string | null {
  if (hpa === null) return null
  if (hpa < 980) return 'Presión muy baja — depresión profunda'
  if (hpa < 1009) return 'Presión baja — por debajo de lo normal (1009 a 1022 hPa)'
  if (hpa < 1023) return 'Presión normal (1009 a 1022 hPa)'
  if (hpa < 1030) return 'Presión alta — por encima de lo normal (desde 1023 hPa)'
  return 'Presión muy alta — anticiclón intenso'
}

// ------------------------------------------------------------------ hora del reporte

/** "mar 06/10 20:00 (hora de Argentina) · 23:00 UTC". CheckWX a veces manda la hora sin `Z`: es UTC. */
export function observedLabel(observed: string | null | undefined): string | null {
  const date = parseObservedAt(observed)
  if (date === null) return null
  const utc = `${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}`
  return `${formatLocalInstant(date.toISOString())} (hora de Argentina) · ${utc} UTC`
}

// ------------------------------------------------------------------ nubes

export type MetarCloudData = CloudLayerData

const CONVECTIVE_RAW_RE = /\b(?:FEW|SCT|BKN|OVC)\d{3}(CB|TCU)\b/

/**
 * CB y TCU se buscan en el texto del METAR y también en el `type` de cada capa. CheckWX documenta ese
 * `type` como un objeto `{ code, text }`; la respuesta real de SACO (sin convección) no lo trae.
 */
export function cloudNote(clouds: MetarCloudData[] | undefined, rawText: string | undefined): string {
  if (!clouds || clouds.length === 0) return ''
  const fromText = CONVECTIVE_RAW_RE.exec(rawText ?? '')?.[1]
  const kinds = new Set([fromText, ...clouds.map(cloudType)])
  if (kinds.has('CB')) return '⚠️ Cumulonimbus reportado — condición crítica'
  if (kinds.has('TCU')) return '⚠️ Cúmulos en torre (TCU) reportados — condición crítica'

  const ceiling = clouds
    .filter(c => c.code === 'BKN' || c.code === 'OVC' || c.code === 'VV') // VV (visibilidad vertical) también es techo
    .sort((a, b) => (cloudBaseFeet(a) ?? Infinity) - (cloudBaseFeet(b) ?? Infinity))[0]
  if (!ceiling) return 'Sin capa de techo definida'
  const base = cloudBaseText(ceiling)
  return base === null ? 'Techo definido' : `Techo definido a ${base} AGL`
}

/** Valor de la tarjeta de nubes: "SCT 3500 ft (1067 m) · OVC 8000 ft (2438 m)"; sin altura, solo el código. */
export function cloudsDisplay(clouds: MetarCloudData[] | undefined): string {
  return (clouds ?? [])
    .map(c => [c.code ?? '', cloudBaseText(c) ?? ''].filter(part => part !== '').join(' '))
    .filter(label => label !== '')
    .join(' · ')
}
