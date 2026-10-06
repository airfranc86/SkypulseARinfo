/**
 * Visibility scale for the Niebla page — official METAR/SMN definitions.
 *
 * Niebla (FG)          visibility < 1 km
 * Neblina o bruma (BR) 1 km to < 5 km (in Argentina "neblina" and "bruma" are the same thing)
 * Buena                5 km to < 10 km
 * Despejada            >= 10 km
 *
 * Dry haze (HZ: dust, smoke, pollution) is NOT a category of this scale.
 * Boundaries and colors mirror `_classify_visibility` in
 * apps/backend/app/services/openmeteo.py — keep both in sync.
 */

export interface FogLevel {
  /** Same numeric level as the backend `fog_level` (0 = despejada … 3 = niebla). */
  readonly level: 0 | 1 | 2 | 3
  readonly label: string
  readonly range: string
  readonly color: string
  readonly note: string
}

/** Worst → best. */
export const FOG_SCALE: readonly FogLevel[] = [
  { level: 3, label: 'Niebla',          range: '< 1 km',   color: '#e03535', note: 'Gotas de agua (FG)' },
  { level: 2, label: 'Neblina o bruma', range: '1 – 5 km', color: '#f0a020', note: 'Gotas de agua (BR)' },
  { level: 1, label: 'Buena',           range: '5 – 10 km', color: '#5aaad8', note: '' },
  { level: 0, label: 'Despejada',       range: '≥ 10 km',  color: '#3ecf7a', note: '' },
]

const FOG_BY_LEVEL: Record<FogLevel['level'], FogLevel> = {
  0: FOG_SCALE[3],
  1: FOG_SCALE[2],
  2: FOG_SCALE[1],
  3: FOG_SCALE[0],
}

/** Classifies visibility in meters; null/undefined when there is no data. */
export function classifyVisibility(m: number | null | undefined): FogLevel | null {
  if (m == null || Number.isNaN(m)) return null
  if (m >= 10_000) return FOG_BY_LEVEL[0]
  if (m >= 5_000) return FOG_BY_LEVEL[1]
  if (m >= 1_000) return FOG_BY_LEVEL[2]
  return FOG_BY_LEVEL[3]
}

const DEFAULT_FOG_COLOR = '#3ecf7a'

/** The backend sends the scale colors; this only supplies the green default when missing. */
export function normalizeFogColor(c: string | null | undefined): string {
  return c || DEFAULT_FOG_COLOR
}
