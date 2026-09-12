/**
 * Shared quality-scale (Excelente/Bueno/Regular/No apto) color mapping.
 *
 * Single source of truth for the 4-tier label→color mapping, previously
 * duplicated independently across LavarCoche, LaundryDayCard and SportBlock
 * with diverging results (some collapsed "Regular" and "No apto" into the
 * same color).
 */

export type QualityLabel = 'Excelente' | 'Bueno' | 'Regular' | 'No apto'

// 4 colores distintos — uno por label, incluido "No apto" ≠ "Regular".
export const LABEL_COLOR: Record<QualityLabel, string> = {
  Excelente: '#3ecf7a',
  Bueno: '#f0a030',
  Regular: '#e05545',
  'No apto': '#ff6b6b', // = --color-crit-soft, ~7:1 sobre navy — el rating más grave debe ser el más legible.
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
