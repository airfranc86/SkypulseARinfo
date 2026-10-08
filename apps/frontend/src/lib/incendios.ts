/**
 * Lógica pura de la página de Incendios: la altura de las barras de "Próximas 24 h" y el rótulo del
 * pico de riesgo. Sin React ni `import.meta.env`, así `node --test` prueba cada regla sin DOM.
 */
import { addDays, arDateKey, dayLabel } from './dates.ts'

/** Mínimo visible de una barra: un puntaje bajo (o 0) tiene que verse como una barra, no desaparecer. */
export const BAR_MIN_HEIGHT_PX = 3

export interface RiskBarHeight {
  /** Alto de la barra en % de la pista (0 a 100). */
  heightPct: number
  /** Alto mínimo en px, para que los puntajes muy bajos no queden invisibles. */
  minHeightPx: number
}

/**
 * Altura de cada barra en escala absoluta: el alto es el puntaje (0 a 100), no relativo al máximo
 * del conjunto. Un día entero "Muy bajo" se ve bajo, y un puntaje de 40 mide lo mismo cualquiera
 * sea el resto de las franjas. Un puntaje fuera de 0..100 (o NaN) se acota.
 */
export function riskBarHeights(scores: readonly number[]): RiskBarHeight[] {
  return scores.map((score) => ({
    heightPct: Number.isNaN(score) ? 0 : Math.min(Math.max(score, 0), 100),
    minHeightPx: BAR_MIN_HEIGHT_PX,
  }))
}

const PEAK_DATE = /^\d{4}-\d{2}-\d{2}$/

/** ¿Es un día que existe en el calendario? ("2026-13-45" o "2026-02-30" tienen la forma pero no existen). */
function isRealDate(key: string): boolean {
  const [year, month, day] = key.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day
}

/**
 * "2026-06-02 09:00" → "Hoy 09:00" / "Mañana 09:00" / "2 jun 09:00".
 *
 * `raw` (`peak_hour_label` de la API) viene en hora de Buenos Aires, así que "hoy" también se mide en
 * hora argentina y no en UTC: desde las 21:00 locales la fecha UTC ya es la de mañana. `now` (ms) se
 * inyecta para poder probarlo; un texto que no es "fecha hora" vuelve tal cual.
 */
export function formatPeakTime(raw: string, now: number = Date.now()): string {
  const parts = raw.split(' ')
  if (parts.length < 2) return raw
  const [datePart, timePart] = parts
  if (!PEAK_DATE.test(datePart) || !isRealDate(datePart)) return raw
  const today = arDateKey(now)
  if (datePart === today) return `Hoy ${timePart}`
  if (datePart === addDays(today, 1)) return `Mañana ${timePart}`
  return `${dayLabel(datePart, today).date} ${timePart}`
}
