import type { SmnAlerta } from '@/lib/api'

export type AlertLevel = 'rojo' | 'naranja' | 'amarillo' | 'verde' | 'otro'
export type CriticalLevel = 'rojo' | 'naranja'

/** Orden de gravedad: menor número = más grave. "otro" (nivel que no reconocemos) va al final. */
const RANK: Record<AlertLevel, number> = { rojo: 0, naranja: 1, amarillo: 2, verde: 3, otro: 4 }

/**
 * Colores de cada nivel, elegidos para texto de 12–14 px sobre la tarjeta (#0d1e38) y sobre el
 * mismo color al 12 %: todos superan 4,8:1. Naranja y rojo se separan también por tono, no solo
 * por brillo (antes #e05545 y #ff3333 casi no se distinguían).
 */
export const LEVEL_COLOR: Record<AlertLevel, string> = {
  rojo: '#ff5a5a',
  naranja: '#ff9142',
  amarillo: '#f5c542',
  verde: '#3ecf7a',
  otro: '#90aabb',
}

/** Nivel reconocido de un aviso del SMN; cualquier otra cosa es "otro". */
export function alertLevel(nivel: string): AlertLevel {
  const normalized = nivel.trim().toLowerCase()
  return Object.hasOwn(RANK, normalized) && normalized !== 'otro' ? (normalized as AlertLevel) : 'otro'
}

/** Avisos de más a menos graves. Estable dentro del mismo nivel y sin mutar la entrada. */
export function sortAlertas(alertas: SmnAlerta[]): SmnAlerta[] {
  return alertas
    .map((alerta, index) => ({ alerta, index }))
    .sort((a, b) => RANK[alertLevel(a.alerta.nivel)] - RANK[alertLevel(b.alerta.nivel)] || a.index - b.index)
    .map(({ alerta }) => alerta)
}

/** El nivel crítico más alto entre los avisos (solo naranja y rojo cambian el peso del héroe). */
export function criticalLevel(alertas: SmnAlerta[]): CriticalLevel | null {
  const levels = alertas.map((alerta) => alertLevel(alerta.nivel))
  if (levels.includes('rojo')) return 'rojo'
  if (levels.includes('naranja')) return 'naranja'
  return null
}

const AR_ZONE = 'America/Argentina/Buenos_Aires'

const parts = new Intl.DateTimeFormat('es-AR', {
  timeZone: AR_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

interface ArClock {
  day: string
  weekday: string
  time: string
}

function arClock(ms: number): ArClock {
  const get = (type: Intl.DateTimeFormatPartTypes) => parts.formatToParts(ms).find((p) => p.type === type)?.value ?? ''
  return {
    day: `${get('year')}-${get('month')}-${get('day')}`,
    weekday: get('weekday').replace('.', ''),
    time: `${get('hour')}:${get('minute')}`,
  }
}

/** Fecha con zona horaria explícita ("Z" u offset). Sin ella la hora es ambigua y no se muestra. */
function parseZoned(value: string | null): number | null {
  if (!value || !/(Z|[+-]\d{2}:?\d{2})$/i.test(value.trim())) return null
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? null : ms
}

/** "las 21:00" si es hoy (hora argentina), "el sáb 23:00" si es otro día. */
function whenAr(ms: number, nowMs: number): string {
  const clock = arClock(ms)
  return clock.day === arClock(nowMs).day ? `las ${clock.time}` : `el ${clock.weekday} ${clock.time}`
}

/**
 * Vigencia del aviso en palabras ("hasta las 21:00", "desde las 18:00 hasta las 21:00"), o null
 * si la fuente no la trae o la trae sin zona horaria: no se inventa una hora.
 */
export function vigenciaText(alerta: SmnAlerta, nowMs: number): string | null {
  if (!Number.isFinite(nowMs)) return null
  const desde = parseZoned(alerta.fecha_desde)
  const hasta = parseZoned(alerta.fecha_hasta)
  const notStarted = desde !== null && desde > nowMs
  if (notStarted && hasta !== null) return `desde ${whenAr(desde, nowMs)} hasta ${whenAr(hasta, nowMs)}`
  if (notStarted) return `desde ${whenAr(desde, nowMs)}`
  if (hasta !== null) return `hasta ${whenAr(hasta, nowMs)}`
  return null
}
