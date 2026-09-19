/**
 * Color del viento según su intensidad, el mismo en el héroe, la lista y la tabla.
 * Intensa: #ff7a66 (6,5:1 sobre la tarjeta); el rojo que usaban la lista y la tabla, #e03535, llegaba a 3,75:1.
 */
const WIND_COLOR: Record<string, string> = {
  moderada: '#c8a84b',
  intensa: '#ff7a66',
}

/** Color de un viento; sin intensidad conocida, el que se pase de respaldo. */
export function windColor(intensity: string | null | undefined, fallback = 'var(--color-muted-foreground)'): string {
  return (intensity ? WIND_COLOR[intensity] : undefined) ?? fallback
}
