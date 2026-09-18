import type { DensityFormValues } from '@/lib/densityAltitude'

export type NumericKey = 'elev_ft' | 'qnh_hpa' | 'oat_c' | 'td_c' | 'ias_kt'
export type FieldKey = Exclude<keyof DensityFormValues, 'aircraft_model'>

/** Orden visual del formulario: define cuál es el "primer" campo con error. */
export const FIELD_ORDER: FieldKey[] = ['elev_ft', 'qnh_hpa', 'oat_c', 'td_c', 'wl_nom', 'ias_kt']

export const FIELD_IDS: Record<FieldKey, string> = {
  elev_ft: 'da-elev',
  qnh_hpa: 'da-qnh',
  oat_c: 'da-oat',
  td_c: 'da-td',
  wl_nom: 'da-wl',
  ias_kt: 'da-ias',
}

export const FIELD_LABELS: Record<FieldKey, string> = {
  elev_ft: 'Elevación',
  qnh_hpa: 'QNH',
  oat_c: 'Temperatura',
  td_c: 'Punto de rocío',
  wl_nom: 'Wing loading',
  ias_kt: 'Velocidad indicada',
}

/** Anillo de foco del tema (dorado) en vez del `outline: auto` del navegador. */
export const FOCUS_RING = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--color-ring)'
