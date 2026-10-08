import { uvCategory } from './uvScale.ts'

/**
 * Texto del chip "Sol" de la tarjeta de deporte, o `null` si no hay nada honesto que decir
 * (de día y sin dato de UV: el chip se oculta en vez de inventar un "moderado").
 * Los tramos 3-5 y 6+ conservan su redacción de siempre; solo el UV bajo (0-2) cambió.
 */
export function sunChipLabel(isDay: boolean, uv: number | null): string | null {
  if (!isDay) return 'Sin sol'
  const category = uvCategory(uv)
  if (category === null || uv === null) return null
  if (category.level === 'bajo') return 'UV bajo'
  if (category.level === 'moderado') return 'Sol directo'
  return `UV ${Math.round(uv)} — alto`
}
