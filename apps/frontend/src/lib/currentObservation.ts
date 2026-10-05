import type { CurrentDetailed, CurrentNotice, PossibleChangeReason } from '@/lib/api'

/**
 * Texts for the dashboard "now" (FRA-320): whether it is an airport observation or a model estimate,
 * how old the data is, the wind reading and the notices. Pure module (no React, no `import.meta.env`)
 * so it can be tested with `node --test`; `nowMs` is injected.
 */

const MS_PER_MIN = 60_000
const METAR_ATTRIBUTION = 'METAR: aviationweather.gov (NOAA)'

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** "1,3": one decimal with a decimal comma, as the rest of the app writes millimetres. */
function formatOneDecimal(value: number): string {
  return value.toFixed(1).replace('.', ',')
}

// ── Age of the data ──────────────────────────────────────────────────────────

/** "hace 25 min", "hace 1 h", "hace 1 h 5 min"; null when the time is missing or invalid. */
export function describeAge(observedAt: string | null | undefined, nowMs: number): string | null {
  if (!observedAt || !Number.isFinite(nowMs)) return null
  const observedMs = Date.parse(observedAt)
  if (Number.isNaN(observedMs)) return null
  const minutes = Math.floor((nowMs - observedMs) / MS_PER_MIN)
  if (minutes < 1) return 'hace menos de 1 min'
  if (minutes < 60) return `hace ${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `hace ${hours} h` : `hace ${hours} h ${rest} min`
}

// ── Source footer ────────────────────────────────────────────────────────────

type SourceInput = Pick<CurrentDetailed, 'source' | 'station' | 'observed_at'>

function joinParts(parts: ReadonlyArray<string | null>): string {
  return parts.filter((part): part is string => part !== null).join(' · ')
}

function stationLabel(station: SourceInput['station']): string | null {
  if (!station) return null
  const distance = isFiniteNumber(station.distance_km) ? `, a ${Math.round(station.distance_km)} km` : ''
  return `Aeropuerto ${station.name} (${station.icao})${distance}`
}

/**
 * Footer line that says what the "now" is: an observation (METAR airport or SMN station) or the
 * model estimate, and how old it is.
 */
export function describeSourceFooter(current: SourceInput, nowMs: number): string {
  const age = describeAge(current.observed_at, nowMs)
  if (current.source === 'metar') return joinParts(['Observación', stationLabel(current.station), age])
  if (current.source === 'smn') return joinParts(['Observación', 'estación del SMN', age])
  return joinParts(['Estimación del modelo', age])
}

/** Data attribution required when the "now" comes from the AWC METAR feed. */
export function sourceAttribution(current: Pick<CurrentDetailed, 'source'>): string | null {
  return current.source === 'metar' ? METAR_ATTRIBUTION : null
}

// ── Wind ─────────────────────────────────────────────────────────────────────

export interface WindReading {
  calm: boolean
  /** "20 km/h", or "Calma" when there is no wind. */
  speed: string
  /** Cardinal point, "variable" (VRB) or null when calm. */
  direction: string | null
  /** Only when there is a direction in degrees to point the arrow at. */
  showArrow: boolean
  gust: string | null
}

type WindInput = Pick<CurrentDetailed, 'wind_speed_kmh' | 'wind_dir_deg' | 'wind_dir_cardinal' | 'wind_gust_kmh'>

function describeGust(gust: number | null | undefined): string | null {
  return isFiniteNumber(gust) ? `Ráfagas de ${Math.round(gust)} km/h` : null
}

/** Wind as it is painted in the hero; null when there is no speed to show. */
export function describeWind(current: WindInput): WindReading | null {
  if (!isFiniteNumber(current.wind_speed_kmh)) return null
  const speed = Math.round(current.wind_speed_kmh)
  const gust = describeGust(current.wind_gust_kmh)
  if (speed === 0) return { calm: true, speed: 'Calma', direction: null, showArrow: false, gust }
  return {
    calm: false,
    speed: `${speed} km/h`,
    direction: current.wind_dir_cardinal ?? 'variable',
    showArrow: isFiniteNumber(current.wind_dir_deg),
    gust,
  }
}

// ── Notices ──────────────────────────────────────────────────────────────────

export interface NoticeLine {
  code: CurrentNotice['code']
  text: string
  /** Something may be happening now (moderate attention tone); false for plain context. */
  attention: boolean
}

type PossibleChange = Extract<CurrentNotice, { code: 'possible_change' }>

function maxFinite(values: ReadonlyArray<number | null | undefined>): number | null {
  const finite = values.filter(isFiniteNumber)
  return finite.length > 0 ? Math.max(...finite) : null
}

function possibleChangePart(reason: PossibleChangeReason, notice: PossibleChange): string | null {
  if (reason === 'wind') {
    const wind = maxFinite([notice.model_wind_speed_kmh, notice.model_wind_gust_kmh])
    return wind === null ? null : `viento de ${Math.round(wind)} km/h`
  }
  if (reason === 'rain') {
    const rain = notice.model_precip_1h_mm
    return isFiniteNumber(rain) ? `lluvia de ${formatOneDecimal(rain)} mm en la hora en curso` : null
  }
  if (reason === 'storm') return 'tormenta'
  return null
}

function describePossibleChange(notice: PossibleChange): string | null {
  const parts = (notice.reasons ?? [])
    .map((reason) => possibleChangePart(reason, notice))
    .filter((part): part is string => part !== null)
  if (parts.length === 0) return null
  return `Desde la observación pudo cambiar: el modelo indica ${parts.join(' y ')}`
}

const PHENOMENON_LABEL: Record<string, string> = { rain: 'lluvia', storm: 'tormenta' }

function describeNotice(notice: CurrentNotice): NoticeLine | null {
  switch (notice.code) {
    case 'model_temp_differs':
      return isFiniteNumber(notice.model_temp_c)
        ? { code: notice.code, text: `El modelo estimaba ${Math.round(notice.model_temp_c)} °C`, attention: false }
        : null
    case 'possible_change': {
      const text = describePossibleChange(notice)
      return text === null ? null : { code: notice.code, text, attention: true }
    }
    case 'reported_phenomenon': {
      const label = PHENOMENON_LABEL[notice.kind]
      return label ? { code: notice.code, text: `Reportado en el aeropuerto: ${label}`, attention: true } : null
    }
    default:
      return null
  }
}

/** Notice lines in the backend order; unknown codes or notices without usable values are dropped. */
export function describeNotices(notices: ReadonlyArray<CurrentNotice> | null | undefined): NoticeLine[] {
  return (notices ?? []).map(describeNotice).filter((line): line is NoticeLine => line !== null)
}
