/**
 * Danger scale (1 to 5) drawn by `components/ui/DangerScale.tsx`. Pure data and wording, so Node tests
 * can import it: the colour of each level and the word that names it. The scale measures DANGER; a
 * signal that only announces a change of weather (cirrus) sits at the bottom.
 */
export type DangerLevel = 1 | 2 | 3 | 4 | 5

export const DANGER_COLORS: Record<DangerLevel, string> = {
  1: '#3ecf7a',
  2: '#a8c820',
  3: '#f0a030',
  4: '#e05545',
  5: '#ff3333',
}

const DANGER_LABELS: Record<DangerLevel, string> = {
  1: 'bajo',
  2: 'moderado',
  3: 'considerable',
  4: 'alto',
  5: 'extremo',
}

/** The word for a level: "bajo", "moderado", "considerable", "alto" or "extremo". */
export function dangerLabel(level: DangerLevel): string {
  return DANGER_LABELS[level]
}

/** The whole reading, as shown and as announced: "Peligro: bajo, 1 de 5". */
export function dangerSummary(level: DangerLevel): string {
  return `Peligro: ${dangerLabel(level)}, ${level} de 5`
}
