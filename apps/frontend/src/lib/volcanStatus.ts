import type { AlertLevel, Volcan, VolcanesResponse } from '@/lib/api'

// Lógica de presentación del monitor de volcanes (FRA-343). Pura: sin React,
// testeable con `node --test`. Un volcán 'sin_datos' (OAVV caído o imagen
// ilegible) no se pinta de verde ni de rojo y no cuenta como alerta.

export const VOLCAN_SOURCE_URL = 'https://oavv.segemar.gob.ar/monitoreo-volcanico/'

export interface VolcanLevelStyle {
  label: string
  hex: string
  border: string
  bg: string
}

const LEVEL_STYLE: Record<AlertLevel, VolcanLevelStyle> = {
  verde:     { label: 'Estable',       hex: '#3ecf7a', border: 'rgba(62,207,122,.30)',  bg: 'rgba(62,207,122,.06)'  },
  amarillo:  { label: 'Vigilancia',    hex: '#f0a030', border: 'rgba(240,160,48,.30)',  bg: 'rgba(240,160,48,.06)'  },
  naranja:   { label: 'Preocupación',  hex: '#e05545', border: 'rgba(224,85,69,.35)',   bg: 'rgba(224,85,69,.06)'   },
  rojo:      { label: 'Alerta máxima', hex: '#ff3333', border: 'rgba(255,51,51,.40)',   bg: 'rgba(255,51,51,.07)'   },
  // Gris pizarra neutro, igual al ALERT_HEX del backend: ni "estable" ni alerta.
  sin_datos: { label: 'Sin datos',     hex: '#8b95a5', border: 'rgba(139,149,165,.30)', bg: 'rgba(139,149,165,.06)' },
}

/** Niveles de la escala oficial de alerta (la leyenda). 'sin_datos' no es un nivel. */
export const VOLCAN_LEGEND_LEVELS = ['verde', 'amarillo', 'naranja', 'rojo'] as const satisfies readonly AlertLevel[]

/** Estilo del nivel; uno desconocido (backend más nuevo) cae en el neutro de "sin datos". */
export function volcanLevelStyle(level: AlertLevel): VolcanLevelStyle {
  return LEVEL_STYLE[level] ?? LEVEL_STYLE.sin_datos
}

export function hasVolcanData(volcan: Pick<Volcan, 'alert_level'>): boolean {
  return volcan.alert_level !== 'sin_datos'
}

export function isVolcanAlert(volcan: Pick<Volcan, 'alert_level'>): boolean {
  return volcan.alert_level === 'naranja' || volcan.alert_level === 'rojo'
}

/** Volcanes con dato en naranja o rojo. Los 'sin_datos' nunca cuentan como alerta. */
export function activeVolcanAlerts<T extends Pick<Volcan, 'alert_level'>>(volcanes: readonly T[]): T[] {
  return volcanes.filter(isVolcanAlert)
}

export interface VolcanDataNotice {
  text: string
  href: string
}

const NOTICE_TAIL = 'por ahora. Consultá el sitio de SEGEMAR.'

/** Aviso de datos faltantes, o null si la respuesta está completa (o todavía no llegó). */
export function volcanDataNotice(
  data: Pick<VolcanesResponse, 'volcanes' | 'available'> | undefined,
): VolcanDataNotice | null {
  if (!data) return null
  const missing = data.volcanes.filter(v => !hasVolcanData(v)).length
  if (missing === 0 && data.available !== false) return null

  const allMissing = missing === 0 || missing === data.volcanes.length
  const text = allMissing
    ? `Sin datos de los volcanes ${NOTICE_TAIL}`
    : `Sin datos de ${missing} ${missing === 1 ? 'volcán' : 'volcanes'} ${NOTICE_TAIL}`
  return { text, href: VOLCAN_SOURCE_URL }
}

const NAV_COLOR_NARANJA = '#e05545'
const NAV_COLOR_ROJO = '#ff3333'

/** Punto del menú: se enciende solo con una alerta con dato; rojo si algún volcán está en rojo. */
export function volcanNavBadge(
  data: Pick<VolcanesResponse, 'volcanes'> | undefined,
): { show: boolean; color: string } {
  const active = data ? activeVolcanAlerts(data.volcanes) : []
  const color = active.some(v => v.alert_level === 'rojo') ? NAV_COLOR_ROJO : NAV_COLOR_NARANJA
  return { show: active.length > 0, color }
}
