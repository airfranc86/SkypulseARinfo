/**
 * Texts of one row of the 7-day card (FRA-334): the headline (rain or sky), the rain note, the wind
 * and the trend notice; plus the card's partial-data notice (FRA-336). No model names and no model disagreement: the row reads like a forecast,
 * not like a model comparison. Pure functions (no React) so `node --test` can check each rule.
 */
import { describeWeatherIcon, precipKind } from './weatherLabels.ts'
import type { DailyEntry } from '@/lib/api'

/** The rain phrase shows up above this probability (percent), on days 1 to 4. */
const RAIN_MIN_PROB = 15
/** At or below this daily amount (mm) the rain is "poca cantidad"; above it, the hours are worth showing. */
const RAIN_MM_THRESHOLD = 0.9
/** The wind is highlighted when it rotates and its maximum rises at least this much (km/h) over the previous day. */
const WIND_RISE_KMH = 10
/** Absorbs floating-point noise in the rise (17.3 − 7.3 must count as 10). */
const EPSILON = 1e-9

/** Keeps a number with its unit and "del" with the direction when the line wraps. */
const NBSP = String.fromCharCode(0xa0)

const SMALL_AMOUNT = 'poca cantidad'
const CALM = 'Calma'
const ROTATES_AND_RISES = 'rota y aumenta'

export const TREND_NOTICE = 'Días 5–7: tendencia, puede cambiar'

/** Shown when the model the rain follows did not answer (FRA-336). Never names a model. */
export const MISSING_ANCHOR_NOTICE = 'Pronóstico con datos parciales: la lluvia puede ser menos precisa.'

/** The model the rain, wind and icon follow; without it the rain comes from the other one. */
const ANCHOR_MODEL = 'ecmwf'

const BAND_LABEL: Record<string, string> = {
  '10-40': '10–40',
  '40-60': '40–60',
  '60-100': '60–100',
}

/** 8-point compass in Spanish, clockwise from the north (same sectors as the backend). */
const COMPASS_ES = ['norte', 'noreste', 'este', 'sudeste', 'sur', 'sudoeste', 'oeste', 'noroeste'] as const

/** What a row needs from a day; every field may be missing in an incomplete response. */
export type RowDay = Partial<
  Pick<
    DailyEntry,
    | 'icon'
    | 'is_trend'
    | 'precip_prob'
    | 'precip_sum'
    | 'rain_band'
    | 'wind_speed_max'
    | 'wind_dir_dominant_deg'
    | 'wind_shift'
  >
>

export interface RainText {
  /** "Llovizna 83 %", "Lluvia 40–60 %"; null when the day shows no rain. */
  label: string | null
  /** "poca cantidad" or the rain hours ("06–18 h"), never both; null when neither applies. */
  note: string | null
}

export interface WindText {
  /** "Viento 17 km/h del sur", "Viento 17 km/h", "Calma"; with " · rota y aumenta" when highlighted. */
  text: string
  /** Rotation of 90° or more and a maximum at least 10 km/h above the previous day's. */
  highlight: boolean
}

export interface RowText {
  /** Line 1: the rain phrase when there is one, else the sky in words; null when the icon says neither. */
  headline: string | null
  /** The headline is about rain (it carries the rain styling). */
  rainy: boolean
  /** Line 2, rain part: "poca cantidad" or the rain hours. */
  rainNote: string | null
  /** Line 2, wind part; null when the day has no wind speed. */
  wind: WindText | null
}

const NO_RAIN: RainText = { label: null, note: null }

function isNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** The exact probability (days 1 to 4) or the band (days 5 to 7), with the unit; null when there is no rain. */
function rainProbability(day: RowDay): string | null {
  if (day.is_trend) {
    const band = day.rain_band ? BAND_LABEL[day.rain_band] : undefined
    return band ? `${band}${NBSP}%` : null
  }
  const prob = day.precip_prob
  return isNumber(prob) && prob > RAIN_MIN_PROB ? `${Math.round(prob)}${NBSP}%` : null
}

/** "poca cantidad" for a small known amount; the hours for a bigger one (days 1 to 4 only). */
function rainNote(day: RowDay, window: string | null | undefined): string | null {
  const sum = day.precip_sum
  if (!isNumber(sum)) return null
  if (sum <= RAIN_MM_THRESHOLD) return SMALL_AMOUNT
  return !day.is_trend && window ? window : null
}

/**
 * The rain of a day. Days 1 to 4 show the exact probability; days 5 to 7 only a band, because the
 * exact figure promises more than a trend can deliver.
 */
export function describeRain(day: RowDay, window?: string | null): RainText {
  const probability = rainProbability(day)
  if (probability === null) return NO_RAIN
  const kind = precipKind(day.icon ?? '') ?? 'Lluvia'
  return { label: `${kind} ${probability}`, note: rainNote(day, window) }
}

/** Where the wind comes from, in Spanish ("sur", "noroeste"); null without a direction. */
export function windDirectionEs(deg: number | null | undefined): string | null {
  if (!isNumber(deg)) return null
  const normalized = ((deg % 360) + 360) % 360
  return COMPASS_ES[Math.floor((normalized + 22.5) / 45) % COMPASS_ES.length]
}

function rotatesAndRises(day: RowDay, previous: RowDay | undefined): boolean {
  const today = day.wind_speed_max
  const before = previous?.wind_speed_max
  if (day.wind_shift !== true || !isNumber(today) || !isNumber(before)) return false
  return today - before >= WIND_RISE_KMH - EPSILON
}

/**
 * The wind of a day: whole km/h and where it comes from. `previous` is the day before in the list;
 * without it (the first day) the wind is never highlighted.
 */
export function describeWind(day: RowDay, previous?: RowDay): WindText | null {
  const speed = day.wind_speed_max
  if (!isNumber(speed)) return null
  const kmh = Math.round(speed)
  if (kmh === 0) return { text: CALM, highlight: false }
  const direction = windDirectionEs(day.wind_dir_dominant_deg)
  const base = `Viento ${kmh}${NBSP}km/h${direction ? ` del${NBSP}${direction}` : ''}`
  const highlight = rotatesAndRises(day, previous)
  return { text: highlight ? `${base} · ${ROTATES_AND_RISES}` : base, highlight }
}

/** Every text of the row at `index`; `window` is that day's rain hours, when known. */
export function describeRow(days: ReadonlyArray<RowDay>, index: number, window?: string | null): RowText {
  const day = days[index] ?? {}
  const rain = describeRain(day, window)
  return {
    headline: rain.label ?? describeWeatherIcon(day.icon ?? ''),
    rainy: rain.label !== null,
    rainNote: rain.note,
    wind: describeWind(day, index > 0 ? days[index - 1] : undefined),
  }
}

/**
 * The partial-data notice, only when the response lists models and the anchor is not among them.
 * A missing, null or empty list (older responses) never warns; a missing GFS never warns either.
 */
export function missingAnchorNotice(forecastModels: ReadonlyArray<string> | null | undefined): string | null {
  if (!forecastModels || forecastModels.length === 0) return null
  return forecastModels.includes(ANCHOR_MODEL) ? null : MISSING_ANCHOR_NOTICE
}

/** True for the first day of the trend: the notice goes once, right before it. */
export function isFirstTrendDay(days: ReadonlyArray<Pick<RowDay, 'is_trend'>>, index: number): boolean {
  return Boolean(days[index]?.is_trend) && !days.slice(0, index).some((previous) => previous.is_trend)
}
