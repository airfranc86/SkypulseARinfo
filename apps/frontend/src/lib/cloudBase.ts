// Altura de la base de una capa de nubes del METAR de CheckWX, como funciones puras.
//
// La capa documentada (y la respuesta real de SACO del 2026-10-08) trae `code`, `feet`, `meters` y
// `text`; `type` es opcional y, cuando viene, es un objeto `{ code, text }` (CB, TCU). `base_feet_agl` es
// un campo que CheckWX no manda: queda solo como respaldo.

const METERS_PER_FOOT = 0.3048

export interface CloudLayerData {
  code?: string
  feet?: number
  meters?: number
  text?: string
  base_feet_agl?: number
  type?: string | { code?: string; text?: string } | null
}

const isHeight = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0

/** Altura de la base en pies: `feet`, o `base_feet_agl` si no viene. `null` si no hay una altura usable. */
export function cloudBaseFeet(layer: CloudLayerData): number | null {
  if (isHeight(layer.feet)) return layer.feet
  if (isHeight(layer.base_feet_agl)) return layer.base_feet_agl
  return null
}

/** Altura de la base en metros: los que manda la API, o los pies × 0,3048 redondeados. */
export function cloudBaseMeters(layer: CloudLayerData): number | null {
  const feet = cloudBaseFeet(layer)
  if (feet === null) return null
  if (isHeight(layer.feet) && isHeight(layer.meters)) return Math.round(layer.meters)
  return Math.round(feet * METERS_PER_FOOT)
}

/** "3500 ft (1067 m)", o `null` si la capa no trae altura. */
export function cloudBaseText(layer: CloudLayerData): string | null {
  const feet = cloudBaseFeet(layer)
  const meters = cloudBaseMeters(layer)
  if (feet === null || meters === null) return null
  return `${Math.round(feet)} ft (${meters} m)`
}

/** Tipo de la capa (CB, TCU) en mayúsculas: acepta un string o el objeto `{ code, text }` de CheckWX. */
export function cloudType(layer: CloudLayerData): string | undefined {
  const raw = typeof layer.type === 'string' ? layer.type : (layer.type?.code ?? layer.type?.text)
  const type = typeof raw === 'string' ? raw.trim().toUpperCase() : ''
  return type === '' ? undefined : type
}
