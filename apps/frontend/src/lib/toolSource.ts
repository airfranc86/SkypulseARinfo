import type { ModelKey } from '@/components/ui/ModelBadge'

/**
 * Badge de modelo de una herramienta (secado de ropa, deporte, lavar el auto, cota de nieve,
 * incendios) según el `source` que manda el backend. Salen de Open-Meteo: sin `source` (cargando) o
 * con uno desconocido tampoco se dice GFS. Los de Windy y "respaldo" solo los manda un backend
 * anterior, hasta que se despliegue el nuevo.
 */
export function toolSourceToModel(source?: string): ModelKey {
  if (source === 'windy_gfs' || source === 'windy_gfs_estimated') return 'gfs'
  if (source === 'windy_ecmwf' || source === 'windy_firedanger') return 'windy_ecmwf'
  if (source === 'openmeteo_fallback') return 'openmeteo'
  return 'openmeteo_forecast'
}
