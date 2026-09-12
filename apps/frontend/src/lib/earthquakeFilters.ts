import type { EarthquakeEvent } from '@/lib/api'

export interface EarthquakeFilterState {
  nearby: boolean
  periodDays: 1 | 7 | 30 | null
  minMagnitude: number
  depth: 'all' | 'shallow' | 'intermediate' | 'deep'
  source: 'all' | 'usgs' | 'emsc'
  place: string
}

export const defaultEarthquakeFilters: EarthquakeFilterState = {
  nearby: false,
  periodDays: null,
  minMagnitude: 0,
  depth: 'all',
  source: 'all',
  place: '',
}

const NEARBY_RADIUS_KM = 300

function depthBucket(depthKm: number): 'shallow' | 'intermediate' | 'deep' {
  if (depthKm < 70) return 'shallow'
  if (depthKm < 300) return 'intermediate'
  return 'deep'
}

/** `now` viene de `dataUpdatedAt` del fetch — evita leer el reloj durante el render. */
export function applyEarthquakeFilters(
  events: EarthquakeEvent[],
  f: EarthquakeFilterState,
  now: number
): EarthquakeEvent[] {
  return events.filter((e) => {
    if (f.nearby && e.distance_km > NEARBY_RADIUS_KM) return false
    if (f.periodDays !== null) {
      const ageMs = now - new Date(e.occurred_at).getTime()
      if (ageMs > f.periodDays * 86_400_000) return false
    }
    if (e.magnitude < f.minMagnitude) return false
    if (f.depth !== 'all' && depthBucket(e.depth_km) !== f.depth) return false
    if (f.source !== 'all' && (e.source ?? 'usgs') !== f.source) return false
    if (f.place.trim() && !e.place.toLowerCase().includes(f.place.trim().toLowerCase())) return false
    return true
  })
}

export function isDefaultFilterState(f: EarthquakeFilterState): boolean {
  return (
    !f.nearby &&
    f.periodDays === null &&
    f.minMagnitude === 0 &&
    f.depth === 'all' &&
    f.source === 'all' &&
    f.place.trim() === ''
  )
}
