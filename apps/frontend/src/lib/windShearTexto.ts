/**
 * Línea "Ráfaga menos viento sostenido" del resultado de cizalladura. Pura: sin React ni
 * `import.meta.env`, así se testea con `node --test`.
 *
 * Sin ráfaga informada (`surface_gust_kt === null`) el cálculo usa 0 como valor por defecto
 * (`gust_spread_kt`); mostrar "0,0 kt" parecería una medición. Se dice que no se evaluó.
 * Una ráfaga igual al viento sostenido sí es una diferencia medida de 0.
 */

export interface GustSpreadLine {
  /** Texto de la línea. Si `value` es null, es la línea completa. */
  label: string
  /** Cifra con unidad (p. ej. "13,0 kt") o null cuando no se evaluó. */
  value: string | null
}

const ETIQUETA = 'Ráfaga menos viento sostenido:'

/** `spreadFormatted` es la cifra ya formateada (`formatNearThreshold(gust_spread_kt, …)`). */
export function gustSpreadLine(surfaceGustKt: number | null, spreadFormatted: string): GustSpreadLine {
  if (surfaceGustKt === null) {
    return { label: `${ETIQUETA} no evaluada (sin ráfaga informada)`, value: null }
  }
  return { label: ETIQUETA, value: `${spreadFormatted} kt` }
}
