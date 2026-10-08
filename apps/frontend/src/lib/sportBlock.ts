/**
 * Viento que muestra la tarjeta de deporte: el que usó el puntaje (`data.wind_speed`, de la serie
 * horaria) y no el observado, para que "Viento 24 km/h" no aparezca junto a "viento suave" (< 20).
 * El observado (`current`) solo entra si el puntaje no trae viento.
 */
export function scoredWindSpeed(
  scoredKmh: number | null | undefined,
  observedKmh: number | null | undefined,
): number | null {
  return scoredKmh ?? observedKmh ?? null
}

/** "2 mm", "0,5 mm"; lo que redondea a cero no se muestra como "0 mm". */
function formatMm(mm: number): string {
  const rounded = Math.round(mm * 10) / 10
  if (rounded === 0) return 'menos de 0,1 mm'
  return `${String(rounded).replace('.', ',')} mm`
}

/**
 * Aviso de lluvia de la tarjeta de deporte, a partir de los mm que mandó el backend (`data.precip`):
 * el acumulado de las próximas 12 h, la misma ventana que usa el puntaje. `null` si no hay lluvia.
 */
export function rainIndicatorText(precipMm: number | null | undefined): string | null {
  if (precipMm === null || precipMm === undefined || !Number.isFinite(precipMm) || precipMm <= 0) return null
  return `Lluvia prevista: ${formatMm(precipMm)} en 12 h`
}

/**
 * Humedad que usa la tarjeta de deporte: la del puntaje (`data.humidity`), igual que el viento;
 * la observada solo entra si el puntaje no la trae.
 */
export function scoredHumidity(
  scoredPct: number | null | undefined,
  observedPct: number | null | undefined,
): number | null {
  return scoredPct ?? observedPct ?? null
}

/**
 * Rojo del texto de peligro de la tarjeta (12 px): 5,5:1 sobre `--color-card` y 6,0:1 sobre el fondo
 * de la tarjeta "Excelente". El `#e05545` anterior daba 4,4:1 sobre la tarjeta (< 4,5:1 de WCAG AA).
 */
export const SPORT_DANGER_TEXT = '#f06b5a'

/** Prefijo para lector de pantalla: peligro y atención no se distinguen solo por color. */
export function severityPrefix(severity: 'warning' | 'danger'): string {
  return severity === 'danger' ? 'Peligro:' : 'Atención:'
}

export type SportLabel = 'Excelente' | 'Bueno' | 'Regular' | 'No apto'

/** Qué se muestra en el pie de la tarjeta de deporte. */
export type SportDetail =
  | { kind: 'indicators' }
  | { kind: 'favorable' }
  | { kind: 'reason'; text: string }
  | { kind: 'none' }

/**
 * Decide el pie de la tarjeta. Con indicadores del frontend se muestran ellos. Sin indicadores, el motivo
 * del backend explica el puntaje en cualquier etiqueta que no sea "Excelente" (un "Bueno" por 30 °C o por
 * viento también tiene penalización); "Condiciones favorables" es solo para "Excelente". Sin motivo no se
 * inventa nada.
 */
export function sportDetail(input: {
  label: SportLabel
  reason: string
  indicatorCount: number
}): SportDetail {
  if (input.indicatorCount > 0) return { kind: 'indicators' }
  if (input.label === 'Excelente') return { kind: 'favorable' }
  const text = input.reason.trim()
  return text === '' ? { kind: 'none' } : { kind: 'reason', text }
}
