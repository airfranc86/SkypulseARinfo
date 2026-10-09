/**
 * Texts and decisions for the landing "now" (FRA-333): which city and whether it is the fallback,
 * which state to show for the dashboard request, the plain-language source and update time, the
 * one-line headline and the decision shortcuts. No model or technical source names reach the user.
 * Pure module (no React, no `import.meta.env`) so `node --test` can check every rule.
 */
import type { LocationState } from '@/hooks/useLocation'
import type { CurrentDetailed, WeatherDashboardResponse } from '@/lib/api'
import { isColdStart, isProviderSaturated } from './apiErrors.ts'
import { forecastUpdatedIso } from './forecastAge.ts'
import { formatClock } from './weatherLabels.ts'
import { buildVerdict, type VerdictLine } from './weatherVerdict.ts'

// ── City and fallback ────────────────────────────────────────────────────────

/** City used when the location is denied or unavailable and nothing was saved before. */
export const FALLBACK_LOCATION: LocationState = {
  lat: -34.6037,
  lon: -58.3816,
  label: 'Buenos Aires',
  source: 'fallback',
}

/** After a failed or denied geolocation: the saved location wins; without one, Buenos Aires. */
export function locationAfterGeoFailure(prev: LocationState | null): LocationState {
  return prev ?? FALLBACK_LOCATION
}

/**
 * Whether the location on screen is the Buenos Aires fallback. Only an explicit `fallback` source
 * counts: old saved entries without `source` have an unknown origin and are treated as chosen.
 */
export function isFallbackLocation(location: Pick<LocationState, 'source'> | null): boolean {
  return location?.source === 'fallback'
}

export const CHANGE_CITY_LABEL = 'Cambiar ciudad'

export interface FallbackNotice {
  /** "Mostrando Buenos Aires" */
  lead: string
  /** The action that opens the city search. */
  action: string
  /** Whole line, as read aloud. */
  text: string
}

/** Line above the "now" when the city is the fallback; null with a saved city. */
export function fallbackNotice(location: LocationState | null, isFallback: boolean): FallbackNotice | null {
  if (!location || !isFallback) return null
  const lead = `Mostrando ${location.label}`
  return { lead, action: CHANGE_CITY_LABEL, text: `${lead} · ${CHANGE_CITY_LABEL}` }
}

// ── State shown ──────────────────────────────────────────────────────────────

export type NowState = 'loading' | 'waking' | 'retrying' | 'error' | 'data'

/** The parts of the dashboard query that decide what the "now" shows. */
export interface NowQueryInput {
  hasLocation: boolean
  hasData: boolean
  isFetching: boolean
  failureCount: number
  failureReason: unknown
  hasError: boolean
}

/**
 * Same rules as /prevision (PrevisionClima): data always wins; while the query retries, a cold start
 * or a silent provider gets its own notice and any other failure keeps the skeleton; the error shows
 * only once the retries are over. `isFetching` matters: `failureReason` is not cleared when the
 * retries run out, only on success.
 */
export function nowState(input: NowQueryInput): NowState {
  if (input.hasData) return 'data'
  if (!input.hasLocation) return 'loading'
  const isRetrying = input.isFetching && input.failureCount > 0
  if (isRetrying && isColdStart(input.failureReason)) return 'waking'
  if (isRetrying && isProviderSaturated(input.failureReason)) return 'retrying'
  if (input.hasError) return 'error'
  return 'loading'
}

export const NOW_STATE_TEXT = {
  loading: 'Cargando el tiempo de ahora…',
  waking: 'Despertando el servidor: puede tardar unos segundos, es solo la primera vez del día.',
  retrying: 'Los datos del clima tardan en llegar. Seguimos intentando…',
  error: 'No pudimos cargar el tiempo de ahora. Probá de nuevo en unos segundos.',
  retryLabel: 'Reintentar',
} as const

// ── Source and update time ───────────────────────────────────────────────────

type SourceInput = Partial<Pick<CurrentDetailed, 'source' | 'station'>>

/**
 * Where the "now" comes from, in plain words: an airport, the national service or the forecast.
 * The airport name already says it is an airport ("Aeroparque", "Ezeiza"), so the word is used only
 * when the name is missing.
 */
export function describeNowSource(current: SourceInput): string {
  if (current.source === 'metar') {
    return current.station?.name ? `Medido en ${current.station.name}` : 'Medido en el aeropuerto más cercano'
  }
  if (current.source === 'smn') return 'Medido por el Servicio Meteorológico Nacional'
  return 'Estimado por el pronóstico'
}

/**
 * Credit line for airport data (AWC feed), required by the project (see `sourceAttribution` in
 * currentObservation). On the landing it reads as a plain source, without the word "METAR".
 */
export function nowAttribution(current: Pick<SourceInput, 'source'>): string | null {
  return current.source === 'metar' ? 'Fuente: aviationweather.gov (NOAA)' : null
}

/** Non-breaking space: the clock never wraps away from "Actualizado". */
const NBSP = ' '

/** "Actualizado 19:47" (Argentine clock) from the backend time; null when it is missing or invalid. */
export function describeUpdatedAt(fetchedAt: string | null | undefined): string | null {
  const clock = formatClock(fetchedAt)
  return clock ? `Actualizado${NBSP}${clock}` : null
}

/** "Medido por el Servicio Meteorológico Nacional · Actualizado 19:47" */
export function nowFooter(current: SourceInput, fetchedAt: string | null | undefined): string {
  const updated = describeUpdatedAt(fetchedAt)
  const source = describeNowSource(current)
  return updated ? `${source} · ${updated}` : source
}

/**
 * The footer for a dashboard response. "Actualizado" is the forecast's own time (`forecast_fetched_at`),
 * not when the server built the response: a stored copy served during an outage would read "now".
 */
export function nowFooterFor(data: Pick<WeatherDashboardResponse, 'current' | 'fetched_at' | 'forecast_fetched_at'>): string {
  return nowFooter(data.current, forecastUpdatedIso(data))
}

// ── Headline ─────────────────────────────────────────────────────────────────

type HeadlineInput = Pick<WeatherDashboardResponse, 'fetched_at' | 'hourly' | 'rain_today'>

/**
 * The first line of the /prevision verdict ("Sin lluvia prevista en las próximas 24 h", the next
 * rain, the storm risk): the same rules, measured from when the server built the forecast.
 * SMN warnings are not passed (out of scope for the landing, FRA-333).
 */
export function nowHeadline(data: HeadlineInput): VerdictLine | null {
  const nowMs = Date.parse(data.fetched_at)
  const drizzleHint = data.rain_today.status_text.toLowerCase().includes('llovizna')
  return buildVerdict(data.hourly.entries, nowMs, drizzleHint)[0] ?? null
}

// ── Shortcuts ────────────────────────────────────────────────────────────────

export interface LandingShortcut {
  id: 'sport' | 'laundry' | 'carwash' | 'quake'
  to: string
  label: string
}

/** From the data to the decision. Same destinations and names as the menu (App.tsx, NAV_TOOLS_BASE). */
export const DECISION_SHORTCUTS: readonly LandingShortcut[] = [
  { id: 'sport', to: '/hacer-deporte', label: 'Hacer deporte' },
  { id: 'laundry', to: '/tender-ropa', label: 'Secado de ropa' },
  { id: 'carwash', to: '/lavar-auto', label: 'Lavar el auto' },
]

export const QUAKE_SHORTCUT: LandingShortcut & { hint: string } = {
  id: 'quake',
  to: '/terremotos',
  label: '¿Sentiste un temblor?',
  hint: 'Ver sismos recientes',
}
