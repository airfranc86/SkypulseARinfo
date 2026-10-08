/**
 * What a day card of "Secado de ropa" shows, decided apart from the JSX so it can be tested.
 * `LaundryDayCard` only draws the `LaundryDayView`. The best-day floor (`isQualifiedBest`,
 * `qualifiedBestDay`) is shared with `TenderRopa` and `LavarCoche`, whose days have the same
 * `label`, `score` and `is_best`.
 */
import type { LaundryDay } from './api.ts'
import { LABEL_COLOR, resolveLabel, type QualityLabel } from './qualityScale.ts'

type LaundryDayInput = Pick<
  LaundryDay,
  'label' | 'score' | 'is_best' | 'day_label' | 'confidence_label'
>

interface LaundryDayView {
  /** Pill, dot and text color: always the scale color of the label, never the gold of the badge. */
  labelColor: string
  /** The "Mejor día" badge and glow. */
  showBestBadge: boolean
  /** Short note for days the backend rates with medium (or low) confidence, or null. */
  confidenceText: string | null
  /** The day, written once ("Sáb 10/10"). */
  dayText: string
}

/** The backend always flags one best day (the top score); it only counts when it is this good. */
const BEST_DAY_LABELS: readonly QualityLabel[] = ['Excelente', 'Bueno']

type BestCandidate = Pick<LaundryDayInput, 'is_best' | 'label' | 'score'>

export function isQualifiedBest(day: BestCandidate): boolean {
  return day.is_best && BEST_DAY_LABELS.includes(resolveLabel(day))
}

/** The day to mark as "Mejor día" (the first flagged one that qualifies), or null. */
export function qualifiedBestDay<T extends BestCandidate>(days: readonly T[]): T | null {
  return days.find(isQualifiedBest) ?? null
}

// The backend curve (75 to 95 %) never rates a day "Baja" today; this keeps it from being silent if it does.
function confidenceText(label: LaundryDay['confidence_label']): string | null {
  if (label === 'Media') return 'Confianza media'
  if (label === 'Baja') return 'Confianza baja'
  return null
}

export function laundryDayView(day: LaundryDayInput): LaundryDayView {
  return {
    labelColor: LABEL_COLOR[resolveLabel(day)],
    showBestBadge: isQualifiedBest(day),
    confidenceText: confidenceText(day.confidence_label),
    dayText: day.day_label,
  }
}
