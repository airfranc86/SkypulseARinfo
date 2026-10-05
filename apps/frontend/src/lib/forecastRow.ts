/**
 * Texts of one row of the 7-day card (FRA-322): the rain line, the trend notice and the
 * per-model detail table. Pure functions (no React) so `node --test` can check each rule.
 */
import { precipKind } from './weatherLabels.ts'
import type { DailyEntry, ForecastModelName, ModelDayDetail } from '@/lib/api'

/** A rain pill shows up above this probability (percent). */
const PILL_MIN_PROB = 15
/** A model "rains" strictly above this daily amount (mm); at or below it, the amount is small. */
const RAIN_MM_THRESHOLD = 0.9

const NO_DATA = 'Sin dato'
const MODEL_MISSING = 'No disponible'
const MISSING_PART = '—'

export const TREND_NOTICE = 'Días 5–7: tendencia, puede cambiar'

const BAND_LABEL: Record<string, string> = {
  '10-40': '10–40',
  '40-60': '40–60',
  '60-100': '60–100',
}

const MODEL_LABEL: Record<ForecastModelName, string> = { gfs: 'GFS', ecmwf: 'ECMWF' }

/** What a row needs from a day; every field may be missing in an incomplete response. */
export type RowDay = Partial<
  Pick<
    DailyEntry,
    | 'icon'
    | 'is_trend'
    | 'precip_prob'
    | 'precip_sum'
    | 'rain_band'
    | 'rain_disagreement'
    | 'temp_max'
    | 'temp_min'
    | 'wind_speed_max'
    | 'models'
  >
>

/** The model whose numbers the row follows: the card's selector, or consensus. */
export type ShownModel = 'consensus' | ForecastModelName

export interface RainText {
  /** Pill text ("Lluvia 40 %", "Lluvia 40–60 % · poca cantidad"), or null when the row shows none. */
  pill: string | null
  /** Show the rain hours next to the pill (only when the amount is above the threshold). */
  showWindow: boolean
  /** "GFS: 0,1 mm · ECMWF: 7,1 mm" when only one model predicts rain, else null. */
  disagreement: string | null
}

export interface DetailRow {
  id: 'temp' | 'rain' | 'prob' | 'wind' | 'cloud'
  label: string
  gfs: string
  ecmwf: string
  /** What the row itself uses (the mean in temperature, the anchor model in the rest). */
  inRow: string
}

function isNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** Millimetres with a decimal comma and one decimal ("0,1"); null when there is no number. */
export function formatMm(value: number | null | undefined): string | null {
  return isNumber(value) ? value.toFixed(1).replace('.', ',') : null
}

function formatDisagreement(day: RowDay): string | null {
  const gfs = formatMm(day.rain_disagreement?.gfs_mm)
  const ecmwf = formatMm(day.rain_disagreement?.ecmwf_mm)
  return gfs !== null && ecmwf !== null ? `GFS: ${gfs} mm · ECMWF: ${ecmwf} mm` : null
}

/** Appends " · poca cantidad" when the amount is known and does not pass the threshold. */
function withAmountNote(text: string, sum: number | null | undefined): string {
  return isNumber(sum) && sum <= RAIN_MM_THRESHOLD ? `${text} · poca cantidad` : text
}

function nearDayRain(day: RowDay, kind: string, disagreement: string | null): RainText {
  // The disagreement text replaces the pill (and the hours that go with it).
  if (disagreement !== null) return { pill: null, showWindow: false, disagreement }
  const prob = day.precip_prob
  if (!isNumber(prob) || prob <= PILL_MIN_PROB) return { pill: null, showWindow: false, disagreement: null }
  return {
    pill: withAmountNote(`${kind} ${Math.round(prob)} %`, day.precip_sum),
    showWindow: isNumber(day.precip_sum) && day.precip_sum > RAIN_MM_THRESHOLD,
    disagreement: null,
  }
}

function trendDayRain(day: RowDay, kind: string, disagreement: string | null): RainText {
  const band = day.rain_band ? BAND_LABEL[day.rain_band] : undefined
  return {
    pill: band ? withAmountNote(`${kind} ${band} %`, day.precip_sum) : null,
    showWindow: false,
    disagreement,
  }
}

/**
 * The rain line of a row. Days 1 to 4 show the exact probability; days 5 to 7 only a band, because
 * the exact figure promises more than a trend can deliver.
 */
export function describeRain(day: RowDay): RainText {
  const kind = precipKind(day.icon ?? '') ?? 'Lluvia'
  const disagreement = formatDisagreement(day)
  return day.is_trend ? trendDayRain(day, kind, disagreement) : nearDayRain(day, kind, disagreement)
}

/** True for the first day of the trend: the notice goes once, right before it. */
export function isFirstTrendDay(days: ReadonlyArray<Pick<RowDay, 'is_trend'>>, index: number): boolean {
  return Boolean(days[index]?.is_trend) && !days.slice(0, index).some((previous) => previous.is_trend)
}

// ── Per-model detail ────────────────────────────────────────────────────────

function whole(value: number | null | undefined, unit: string): string {
  return isNumber(value) ? `${Math.round(value)} ${unit}` : NO_DATA
}

function millimetres(value: number | null | undefined): string {
  const text = formatMm(value)
  return text === null ? NO_DATA : `${text} mm`
}

function temperatures(max: number | null | undefined, min: number | null | undefined): string {
  if (!isNumber(max) && !isNumber(min)) return NO_DATA
  const part = (value: number | null | undefined) => (isNumber(value) ? `${Math.round(value)}°` : MISSING_PART)
  return `${part(max)} / ${part(min)}`
}

type Formatter = (detail: ModelDayDetail) => string

const FORMATTERS: ReadonlyArray<readonly [DetailRow['id'], string, Formatter]> = [
  ['temp', 'Temperatura', (m) => temperatures(m.temp_max, m.temp_min)],
  ['rain', 'Lluvia', (m) => millimetres(m.precip_sum)],
  ['prob', 'Probabilidad de lluvia', (m) => whole(m.precip_prob, '%')],
  ['wind', 'Viento máximo', (m) => whole(m.wind_speed_max, 'km/h')],
  ['cloud', 'Nubosidad', (m) => whole(m.cloud_cover_mean, '%')],
]

/** The numbers the row itself shows, so the column "En la fila" never disagrees with the row. */
function rowDetail(day: RowDay, shown: ShownModel): ModelDayDetail {
  const models = day.models
  const anchor = shown === 'gfs' ? models?.gfs : (models?.ecmwf ?? models?.gfs)
  return {
    temp_max: day.temp_max ?? null,
    temp_min: day.temp_min ?? null,
    precip_sum: day.precip_sum ?? null,
    precip_prob: day.precip_prob ?? null,
    wind_speed_max: day.wind_speed_max ?? null,
    cloud_cover_mean: anchor?.cloud_cover_mean ?? null,
  }
}

/**
 * Rows of the accordion table: GFS | ECMWF | what the row uses. A model that did not answer reads
 * "No disponible"; a number it did not give reads "Sin dato". Never NaN, null or undefined.
 */
export function detailRows(day: RowDay, shown: ShownModel = 'consensus'): DetailRow[] {
  const inRow = rowDetail(day, shown)
  const column = (model: ModelDayDetail | null | undefined, format: Formatter) =>
    model ? format(model) : MODEL_MISSING
  return FORMATTERS.map(([id, label, format]) => ({
    id,
    label,
    gfs: column(day.models?.gfs, format),
    ecmwf: column(day.models?.ecmwf, format),
    inRow: format(inRow),
  }))
}

/** Notice for when one of the two models did not answer; null when both did (or nothing is known). */
export function missingModelNotice(models: ReadonlyArray<ForecastModelName> | null | undefined): string | null {
  if (!models || models.length !== 1) return null
  return `Solo hay datos de ${MODEL_LABEL[models[0]]}: el otro modelo no respondió.`
}
