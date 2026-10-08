/**
 * Cota de nieve: pure logic (bands, thresholds, texts, range and precision of the three methods).
 * No React and no `@/` alias, so `node --test` can load it. The page only draws what this returns.
 *
 * The scale is INFORMATIVE: a high snow line is not "good" and a low one is not "bad". A high line
 * means the rain reaches higher and it snows only above; a low line means it can snow low.
 */

// ── Bands: one source of truth for the thresholds ────────────────────────────

/** Lowest average (m) of each band, except the last one, which takes everything below `medium`. */
export const SNOW_THRESHOLDS = {
  veryHigh: 2500,
  high: 1800,
  medium: 1000,
} as const

export type SnowBandKey = 'veryHigh' | 'high' | 'medium' | 'low'

interface SnowBand {
  key: SnowBandKey
  /** Lowest average (m) that belongs to the band. */
  min: number
  /** Title of the status card. */
  label: string
  /** Short label under the scale bar. */
  scaleLabel: string
  /** Neutral blue gradient, lighter for a higher snow line. */
  color: string
  bg: string
  /** Sentence under the title; `n` is the rounded average with thousands separators, `metres` the rounded number. */
  message: (n: string, metres: number) => string
}

/** From the highest snow line to the lowest. */
const SNOW_BANDS: readonly SnowBand[] = [
  {
    key: 'veryHigh', min: SNOW_THRESHOLDS.veryHigh, label: 'Cota muy alta', scaleLabel: 'Muy alta',
    color: '#b4dcf7', bg: 'rgba(180,220,247,0.07)',
    message: (n) => `Si precipita, la lluvia llega hasta unos ${n} m y nieva por encima.`,
  },
  {
    key: 'high', min: SNOW_THRESHOLDS.high, label: 'Cota alta', scaleLabel: 'Alta',
    color: '#7cc0ec', bg: 'rgba(124,192,236,0.07)',
    message: (n) => `Si precipita, la lluvia llega hasta unos ${n} m y nieva por encima.`,
  },
  {
    key: 'medium', min: SNOW_THRESHOLDS.medium, label: 'Cota media', scaleLabel: 'Media',
    color: '#4f9fd9', bg: 'rgba(79,159,217,0.07)',
    message: (n) => `Si precipita, nieva desde unos ${n} m; por debajo cae como lluvia.`,
  },
  {
    key: 'low', min: Number.NEGATIVE_INFINITY, label: 'Cota baja', scaleLabel: 'Baja',
    color: '#3d8bd0', bg: 'rgba(61,139,208,0.07)',
    message: (n, metres) =>
      metres <= 0
        ? 'La cota está a nivel del mar o por debajo: puede nevar a baja altura.'
        : `La cota ronda los ${n} m: puede nevar a baja altura.`,
  },
]

export interface SnowStatus {
  key: SnowBandKey
  label: string
  scaleLabel: string
  msg: string
  color: string
  bg: string
}

/** One entry of the scale bar, from the highest snow line to the lowest. */
export interface SnowScaleEntry {
  key: SnowBandKey
  label: string
  color: string
}

export const SNOW_SCALE: readonly SnowScaleEntry[] = SNOW_BANDS.map(({ key, scaleLabel, color }) => ({
  key,
  label: scaleLabel,
  color,
}))

/** Thousands with a dot (es-AR), deterministic in any ICU build. */
export function groupThousands(n: number): string {
  const sign = n < 0 ? '-' : ''
  return sign + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

/** Status of the card and the scale bar for an average snow line in metres. */
export function snowStatus(avg: number): SnowStatus {
  // The band is decided on the rounded metres, the same number the card and the message show.
  const metres = Math.round(avg)
  const band = SNOW_BANDS.find((b) => metres >= b.min) ?? SNOW_BANDS[SNOW_BANDS.length - 1]
  return {
    key: band.key,
    label: band.label,
    scaleLabel: band.scaleLabel,
    msg: band.message(groupThousands(metres), metres),
    color: band.color,
    bg: band.bg,
  }
}

/** Accessible name of the scale bar: which of the four bands the average is in. */
export function scaleAriaLabel(avg: number): string {
  return `Cota de nieve: ${snowStatus(avg).scaleLabel.toLowerCase()}, escala de cuatro tramos`
}

// ── Range, difference and precision of the three methods ─────────────────────

/** Total spread (m) under which the estimate is "high" or "medium" precision. */
export const PRECISION_THRESHOLDS = {
  high: 200,
  medium: 500,
} as const

export const RANGE_LABEL = 'Rango de los métodos:'
export const SPREAD_LABEL = 'Diferencia entre métodos:'

export interface MethodsRange {
  min: number
  max: number
  /** Total spread: max minus min of the metres shown (not half, not plus-minus). */
  spread: number
}

/**
 * Range of ALL the available methods (Alcaide, gradient and, when there is one, 850 hPa). Metres are
 * rounded first so the range, the difference and the precision label are computed from the same
 * numbers the page shows.
 */
export function methodsRange(
  alcaide: number,
  gradiente: number,
  m850: number | null | undefined,
): MethodsRange {
  const hasM850 = m850 != null && Number.isFinite(m850)
  const values = [alcaide, gradiente, ...(hasM850 ? [m850] : [])].map((v) => Math.round(v))
  const min = Math.min(...values)
  const max = Math.max(...values)
  return { min, max, spread: max - min }
}

/** "2.593 a 2.935 m", or a single value when every method agrees. */
export function rangeText({ min, max }: MethodsRange): string {
  return min === max ? `${groupThousands(min)} m` : `${groupThousands(min)} a ${groupThousands(max)} m`
}

/** "342 m". */
export function spreadText(spread: number): string {
  return `${groupThousands(spread)} m`
}

export function precisionLabel(
  alcaide: number,
  gradiente: number,
  m850: number | null | undefined,
): { label: string; color: string; spread: number } {
  const { spread } = methodsRange(alcaide, gradiente, m850)
  if (spread < PRECISION_THRESHOLDS.high) return { spread, label: 'Alta precisión', color: '#3ecf7a' }
  if (spread < PRECISION_THRESHOLDS.medium) return { spread, label: 'Precisión media', color: '#f0a030' }
  return { spread, label: 'Estimación variable', color: '#e05545' }
}
