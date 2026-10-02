import type { WindShearFieldKey } from '@/lib/windShear'

/** Prefijo `ws-`: no chocar con los ids del formulario de altitud de densidad (`da-`). */
export const FIELD_IDS: Record<WindShearFieldKey, string> = {
  surface_wind_dir_deg: 'ws-surface-dir',
  surface_wind_speed_kt: 'ws-surface-speed',
  surface_gust_kt: 'ws-surface-gust',
  wind_500ft_dir_deg: 'ws-500-dir',
  wind_500ft_speed_kt: 'ws-500-speed',
  wind_1000ft_dir_deg: 'ws-1000-dir',
  wind_1000ft_speed_kt: 'ws-1000-speed',
  surface_temp_c: 'ws-temp-surface',
  temp_1000ft_c: 'ws-temp-1000',
}

export const ICAO_INPUT_ID = 'ws-icao'

/** Campos con signo posible: el teclado decimal de iOS no tiene menos, así que llevan conmutador. */
export const SIGNED_FIELDS: ReadonlySet<WindShearFieldKey> = new Set<WindShearFieldKey>([
  'surface_temp_c',
  'temp_1000ft_c',
])
