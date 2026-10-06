import type { WindShearDriverCode, WindShearRequest } from '@/lib/api'
import { ApiError } from './apiErrors.ts'

/**
 * Helpers puros de la cizalladura (LLWS) que viven aparte de windShear.ts para no pasar el tope de
 * tamaño de archivo: redondeo y formato de magnitudes, antigüedad de la observación del METAR y las
 * líneas de "Por qué". Solo módulos puros (sin `import.meta.env`) para poder testearlos con `node --test`.
 */

// ── Redondeo y formato de magnitudes ─────────────────────────────────────────

/**
 * Decimales con los que se redondea cada magnitud (cizalladura por capa, ráfaga − sostenido, gradiente
 * térmico) UNA vez, donde se calcula. Sin esto el ruido de coma flotante cae sobre los umbrales
 * (10 → 30 kt da 3,999999999999999 y no 4) y esta estimación decide distinto del servidor. El nivel,
 * los drivers y el valor mostrado usan siempre el mismo número ya redondeado.
 * Debe coincidir con _MEASURE_DECIMALS de app/services/wind_shear.py.
 */
export const MEASURE_DECIMALS = 6
const MEASURE_SCALE = 10 ** MEASURE_DECIMALS

export const roundMeasure = (value: number): number => Math.round(value * MEASURE_SCALE) / MEASURE_SCALE

/** Diferencia mínima con un umbral para que el redondeo a 1 decimal pueda sugerir el nivel equivocado. */
const NEAR_THRESHOLD_EPS = 0.05
const NUM_1DEC = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const NUM_PRECISE = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: MEASURE_DECIMALS })

/**
 * 1 decimal, salvo cuando el valor está apenas por encima o por debajo de un umbral: el nivel se
 * decide con el valor sin redondear a 1 decimal, y "4,0" en verde (en realidad 3,996) contradiría al
 * nivel. Cerca de un umbral se muestran todos los decimales con los que se decidió (hasta MEASURE_DECIMALS).
 */
export function formatNearThreshold(value: number, thresholds: readonly number[]): string {
  const ambiguous = thresholds.some(t => value !== t && Math.abs(value - t) < NEAR_THRESHOLD_EPS)
  return (ambiguous ? NUM_PRECISE : NUM_1DEC).format(value)
}

// ── Antigüedad de la observación del METAR ───────────────────────────────────

/** Un METAR más viejo que esto (o sin hora verificable) no se presenta como el viento actual. */
export const METAR_STALE_AFTER_MIN = 60
/** Un reloj del dispositivo apenas atrasado no invalida la hora; más que esto no se puede verificar la edad. */
const CLOCK_SKEW_TOLERANCE_MIN = 5
const MS_PER_MIN = 60_000
const MIN_PER_HOUR = 60

/** ISO sin designador de zona (`2026-10-02T14:48:00`): CheckWX informa UTC, `new Date` lo leería en hora local. */
const ISO_WITHOUT_ZONE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/

export const STALE_METAR_WARNING = 'Puede no reflejar el viento actual.'

export interface ObservationNotice {
  /** Instante de emisión del METAR; null si falta o no se pudo interpretar. */
  observedAt: Date | null
  /** Minutos enteros desde la emisión; null si no hay una hora verificable. */
  ageMin: number | null
  /** Más vieja que METAR_STALE_AFTER_MIN, o sin hora verificable: no hay que tomarla como actual. */
  stale: boolean
}

export function parseObservedAt(raw: string | null | undefined): Date | null {
  if (typeof raw !== 'string' || raw.trim() === '') return null
  const text = raw.trim()
  const date = new Date(ISO_WITHOUT_ZONE_RE.test(text) ? `${text}Z` : text)
  return Number.isNaN(date.getTime()) ? null : date
}

/** `now` entra por parámetro para poder testear la edad sin depender del reloj. */
export function observationNotice(observed: string | null | undefined, now: Date): ObservationNotice {
  const observedAt = parseObservedAt(observed)
  if (observedAt === null) return { observedAt: null, ageMin: null, stale: true }
  const ageMs = now.getTime() - observedAt.getTime()
  // Emitido "en el futuro" por más que la tolerancia: el reloj del dispositivo no sirve para medir la edad.
  if (ageMs < -CLOCK_SKEW_TOLERANCE_MIN * MS_PER_MIN) return { observedAt, ageMin: null, stale: true }
  return {
    observedAt,
    ageMin: Math.floor(Math.max(0, ageMs) / MS_PER_MIN),
    stale: ageMs > METAR_STALE_AFTER_MIN * MS_PER_MIN,
  }
}

/** Hora local del dispositivo (24 h); `timeZone` solo se usa en los tests para no depender de la máquina. */
export function formatObservedTime(date: Date, timeZone?: string): string {
  return new Intl.DateTimeFormat('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone }).format(date)
}

export function formatObservationAge(ageMin: number): string {
  if (ageMin < 1) return 'menos de 1 min'
  if (ageMin < MIN_PER_HOUR) return `${ageMin} min`
  const hours = Math.floor(ageMin / MIN_PER_HOUR)
  const minutes = ageMin % MIN_PER_HOUR
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`
}

/** "observado a las 14:40 (hace 12 min)"; sin hora verificable lo dice en vez de omitirlo. */
export function describeObservation(notice: ObservationNotice, timeZone?: string): string {
  if (notice.observedAt === null) return 'sin hora de observación'
  const at = `observado a las ${formatObservedTime(notice.observedAt, timeZone)}`
  return notice.ageMin === null
    ? `${at} (no pudimos verificar hace cuánto)`
    : `${at} (hace ${formatObservationAge(notice.ageMin)})`
}

/** Mensaje de la precarga aplicada: hora y edad del METAR, y la advertencia explícita si no es actual. */
export function prefillAppliedMessage(icao: string, variable: boolean, notice: ObservationNotice, timeZone?: string): string {
  const observation = describeObservation(notice, timeZone)
  const lead = variable
    ? `El METAR de ${icao} informa viento variable (VRB): cargá la dirección a mano. Velocidad y ráfaga quedaron precargadas, ${observation}.`
    : `Superficie precargada del METAR de ${icao}, ${observation}.`
  const warning = notice.stale ? ` ${STALE_METAR_WARNING}` : ''
  return `${lead}${warning} Revisá los datos antes de calcular.`
}

// ── "Por qué": qué se evaluó y qué no ────────────────────────────────────────

export const LAYER_LOW_LABEL = '0–500 ft'
export const LAYER_HIGH_LABEL = '500–1.000 ft'

type EvaluatedInputs = Pick<WindShearRequest, 'surface_gust_kt' | 'wind_1000ft_dir_deg' | 'wind_1000ft_speed_kt'>

/**
 * Líneas de explicación según lo que se informó. Sin drivers (verde) dice qué capas y qué diferencia se
 * evaluaron y que ninguna alcanza un umbral; siempre aclara lo que NO se evaluó (sin ráfaga la diferencia
 * ráfaga − sostenido vale 0 por defecto, sin viento a 1.000 ft no hay capa alta): un verde no puede
 * tranquilizar sobre algo que no se miró.
 */
export function explanationLines(inputs: EvaluatedInputs, drivers: readonly WindShearDriverCode[]): string[] {
  const hasGust = inputs.surface_gust_kt !== null
  const hasUpperLayer = inputs.wind_1000ft_dir_deg !== null && inputs.wind_1000ft_speed_kt !== null
  const lines: string[] = []
  if (drivers.length === 0) {
    lines.push(
      hasUpperLayer
        ? `Se evaluó la cizalladura de las capas ${LAYER_LOW_LABEL} y ${LAYER_HIGH_LABEL}: ninguna alcanza un umbral de alerta.`
        : `Se evaluó la cizalladura de la capa ${LAYER_LOW_LABEL}: no alcanza un umbral de alerta.`,
    )
    if (hasGust) lines.push('La diferencia entre ráfaga y viento sostenido tampoco alcanza el umbral de alerta.')
  }
  if (!hasGust) lines.push('No se evaluó la diferencia entre ráfaga y viento sostenido: no se informó ráfaga.')
  if (!hasUpperLayer) lines.push(`No se evaluó la capa ${LAYER_HIGH_LABEL}: no se informó viento a 1.000 ft.`)
  return lines
}

// ── Errores del servidor ─────────────────────────────────────────────────────

/** Copy del fallo de red en lenguaje del producto; nunca el "HTTP 502" crudo. */
export function describeServerError(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) {
    return error.retryAfter
      ? `Demasiadas consultas seguidas. Reintentá en ${error.retryAfter} s.`
      : 'Demasiadas consultas seguidas.'
  }
  if (error instanceof ApiError && error.status >= 500) return 'El servidor no respondió.'
  // Un 4xx (422…) es el servidor rechazando los datos: no es una falla de red.
  if (error instanceof ApiError && error.status >= 400) return 'El servidor no aceptó los datos: revisá los valores.'
  if (error instanceof DOMException && error.name === 'AbortError') return 'El servidor tardó demasiado.'
  return 'No pudimos contactar al servidor.'
}
