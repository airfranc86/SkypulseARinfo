/**
 * Shared quality-scale (Excelente/Bueno/Regular/No apto) color mapping.
 *
 * Single source of truth for the 4-tier label→color mapping, previously
 * duplicated independently across LavarCoche, LaundryDayCard and SportBlock
 * with diverging results (some collapsed "Regular" and "No apto" into the
 * same color).
 */

export type QualityLabel = 'Excelente' | 'Bueno' | 'Regular' | 'No apto'

// 4 colores distintos, uno por label. Los valores salen de medir, no de mirar: cada par de labels
// consecutivos queda a >= 25 de distancia CIE76 delta E y cada color llega a >= 4,5:1 de contraste
// sobre la tarjeta (#0d1e38). Lo exige tests/qualityScale.test.ts; si cambia un hex, correrlo.
// Regular es naranja y No apto rojo: antes eran casi el mismo rojo (delta E 13, contraste 1,36:1).
export const LABEL_COLOR: Record<QualityLabel, string> = {
  Excelente: '#3ecf7a', // 8,3:1 sobre la tarjeta
  Bueno: '#f0a030', // 7,8:1; delta E 85 con Excelente
  Regular: '#ee6f2f', // 5,5:1; delta E 28 con Bueno
  'No apto': '#ff4d4d', // 5,1:1; delta E 27 con Regular
}

/**
 * Mirrors the backend's own thresholds in
 * apps/backend/app/services/calculators.py::_label_and_color.
 */
export function scoreToLabel(score: number): QualityLabel {
  if (score >= 75) return 'Excelente'
  if (score >= 50) return 'Bueno'
  if (score >= 30) return 'Regular'
  return 'No apto'
}

/**
 * The label of a day as the scale knows it: the backend's label when it is one of the four,
 * otherwise the one its score gives (an unexpected or missing label never reaches a CSS color).
 */
export function resolveLabel(day: { label?: string | null; score: number }): QualityLabel {
  const { label } = day
  return typeof label === 'string' && Object.hasOwn(LABEL_COLOR, label)
    ? (label as QualityLabel)
    : scoreToLabel(day.score)
}
