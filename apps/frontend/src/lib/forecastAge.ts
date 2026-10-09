/**
 * Age of the forecast on screen. The backend can serve the last good copy of the Open-Meteo data (up
 * to 6 hours old) while the provider is saturated, so the "Actualizado" time must be the forecast's own
 * time (`forecast_fetched_at`) and, past a threshold, the page says so. Pure module (no React, no
 * `import.meta.env`) so `node --test` can check every rule; the current time is always injected.
 */
import { formatClock } from './weatherLabels.ts'

const MINUTE_MS = 60_000
const HOUR_MS = 60 * MINUTE_MS

/** A forecast older than this (strictly) triggers the notice. A normal one is at most ~30 min old. */
export const STALE_FORECAST_AFTER_MS = 2 * HOUR_MS

/** The age is shown to the nearest 5 minutes: "2 h 30 min", never "2 h 1 min". */
const AGE_ROUNDING_MIN = 5

function parseMs(iso: string | null | undefined): number {
  return iso ? Date.parse(iso) : Number.NaN
}

/**
 * Short age for the notice: "45 min", "2 h", "2 h 30 min". Rounded to the nearest 5 minutes; whole
 * hours drop the minutes.
 */
export function formatForecastAge(ageMs: number): string {
  const totalMin = Math.round(ageMs / MINUTE_MS / AGE_ROUNDING_MIN) * AGE_ROUNDING_MIN
  const hours = Math.floor(totalMin / 60)
  const minutes = totalMin % 60
  if (hours === 0) return `${minutes} min`
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`
}

/**
 * The notice when the forecast is strictly older than 2 hours; null when it is not (exactly 2 h is not
 * "more than"), when the date is missing or invalid, when `nowMs` is invalid, and for a date in the
 * future (clock skew): an age is never negative.
 */
export function staleForecastNotice(forecastFetchedAt: string | null | undefined, nowMs: number): string | null {
  const fetchedMs = parseMs(forecastFetchedAt)
  if (!Number.isFinite(fetchedMs) || !Number.isFinite(nowMs)) return null
  const ageMs = nowMs - fetchedMs
  if (ageMs <= STALE_FORECAST_AFTER_MS) return null
  return `Mostrando el último pronóstico disponible, de hace ${formatForecastAge(ageMs)}: el servicio de datos está saturado. Se actualiza solo cuando se recupere.`
}

export interface ForecastAge {
  /** Argentine clock time of the forecast ("12:00"). */
  clock: string
  /** The notice with the age, or null while the forecast is recent enough. */
  notice: string | null
}

/** Clock time and notice for `forecast_fetched_at`; null when the date is missing or invalid. */
export function describeForecastAge(forecastFetchedAt: string | null | undefined, nowMs: number): ForecastAge | null {
  const clock = formatClock(forecastFetchedAt)
  if (!clock) return null
  return { clock, notice: staleForecastNotice(forecastFetchedAt, nowMs) }
}

type UpdatedInput = { forecast_fetched_at?: string | null; fetched_at: string }

/**
 * The time to show as "Actualizado": the forecast's own time when the backend sends a readable one
 * (`forecast_fetched_at ?? fetched_at`), the time the server built the response otherwise (old backend,
 * or a stored copy without a date).
 */
export function forecastUpdatedIso(data: UpdatedInput): string {
  const forecast = data.forecast_fetched_at
  return forecast && Number.isFinite(Date.parse(forecast)) ? forecast : data.fetched_at
}
