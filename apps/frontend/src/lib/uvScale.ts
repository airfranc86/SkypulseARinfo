/** Categorías de la escala del índice UV de la OMS. */
export type UvLevel = 'bajo' | 'moderado' | 'alto' | 'muy-alto' | 'extremo'

export interface UvCategory {
  level: UvLevel
  /** La palabra tal como se lee junto al número ("UV 7 · alto"). */
  label: string
}

/** Límite superior (inclusive) de cada categoría, sobre el índice ya redondeado. */
const UV_STEPS: ReadonlyArray<readonly [number, UvCategory]> = [
  [2, { level: 'bajo', label: 'bajo' }],
  [5, { level: 'moderado', label: 'moderado' }],
  [7, { level: 'alto', label: 'alto' }],
  [10, { level: 'muy-alto', label: 'muy alto' }],
]

const UV_EXTREME: UvCategory = { level: 'extremo', label: 'extremo' }

/**
 * Categoría de un índice UV. Se clasifica el número que se muestra (el backend manda decimales):
 * si la pantalla dice "UV 7", la palabra es la de 7. Sin dato, o con un valor imposible, es `null`.
 */
export function uvCategory(index: number | null | undefined): UvCategory | null {
  if (index === null || index === undefined || !Number.isFinite(index) || index < 0) return null
  const shown = Math.round(index)
  return UV_STEPS.find(([max]) => shown <= max)?.[1] ?? UV_EXTREME
}
