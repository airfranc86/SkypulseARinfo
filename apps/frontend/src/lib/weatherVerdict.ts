import type { HourlyEntry } from '@/lib/api'

/**
 * Lluvia = más de 0,1 mm en el tramo. Es el mismo umbral con el que el backend arma
 * `rain_today.has_rain_today` (dashboard_builder). No se usa `precip_prob` de las
 * entradas horarias: con Windy el backend la aproxima como 100 si llueve y 0 si no,
 * así que un "100 %" horario no es una probabilidad.
 */
export const RAIN_MM = 0.1

/** Ráfaga que merece aviso: el mismo umbral con el que la tira horaria ya marcaba las fuertes. */
export const GUST_KMH = 40

const HOUR_MS = 3_600_000
const AHEAD_HOURS = 24

export type VerdictTone = 'rain' | 'clear' | 'wind' | 'storm'

export interface VerdictLine {
  tone: VerdictTone
  text: string
}

export interface RainRun {
  date: string
  from: string
  to: string
  totalMm: number
  /** El tramo ya está en curso a la hora de referencia. */
  startsNow: boolean
}

export function isRainy(entry: HourlyEntry): boolean {
  return (entry.precip_mm ?? 0) > RAIN_MM
}

/** Entradas de la hora en curso en adelante. Sin hora de referencia válida, todas. */
export function entriesFromNow(entries: HourlyEntry[], nowMs: number): HourlyEntry[] {
  if (!Number.isFinite(nowMs)) return entries
  return entries.filter((entry) => entry.timestamp * 1000 > nowMs - HOUR_MS)
}

/** Tramos consecutivos con lluvia dentro de una lista ordenada de entradas. */
export function rainRuns(entries: HourlyEntry[], nowMs: number): RainRun[] {
  const runs: RainRun[] = []
  let open: RainRun | null = null
  for (const entry of entries) {
    if (!isRainy(entry)) {
      open = null
      continue
    }
    if (open && open.date === entry.date) {
      open.to = entry.hour_label
      open.totalMm += entry.precip_mm ?? 0
    } else {
      open = {
        date: entry.date,
        from: entry.hour_label,
        to: entry.hour_label,
        totalMm: entry.precip_mm ?? 0,
        startsNow: Number.isFinite(nowMs) && entry.timestamp * 1000 <= nowMs,
      }
      runs.push(open)
    }
  }
  return runs
}

/** "14–17 h" o "14–17 h · 21–22 h". Con más de dos tramos, los dos primeros y "…". */
export function rainWindowLabel(entries: HourlyEntry[]): string | null {
  const runs = rainRuns(entries, Number.NaN)
  if (runs.length === 0) return null
  const hours = (label: string) => label.slice(0, 2)
  const format = (run: RainRun) =>
    run.from === run.to ? `${hours(run.from)} h` : `${hours(run.from)}–${hours(run.to)} h`
  const shown = runs.slice(0, 2).map(format).join(' · ')
  return runs.length > 2 ? `${shown} …` : shown
}

/** Ventanas de lluvia por fecha, para la pastilla de cada día (solo hay horas de hoy y mañana). */
export function rainWindowsByDate(entries: HourlyEntry[]): Record<string, string> {
  const byDate = new Map<string, HourlyEntry[]>()
  for (const entry of entries) {
    const list = byDate.get(entry.date)
    if (list) list.push(entry)
    else byDate.set(entry.date, [entry])
  }
  const out: Record<string, string> = {}
  for (const [date, list] of byDate) {
    const label = rainWindowLabel(list)
    if (label) out[date] = label
  }
  return out
}

/** Espacio de no separación: que "4 mm" o "a las 17:00" no se partan entre dos renglones. */
const NBSP = ' '

/** Cantidad de lluvia en palabras: "< 1 mm", "3 mm", "12 mm". */
export function formatMm(mm: number): string {
  if (mm < 1) return `<${NBSP}1${NBSP}mm`
  return `${Math.round(mm).toLocaleString('es-AR')}${NBSP}mm`
}

function dayPrefix(date: string, baseDate: string): string {
  return date === baseDate ? '' : ' mañana'
}

/**
 * Lo que viene en las próximas 24 h, en hechos: hora, cantidad y umbral. Sin porcentajes ni
 * promesas: si el dato no alcanza para decirlo, no se dice.
 *
 * @param drizzleHint el backend marcó "Llovizna posible" (humedad y nubosidad altas sin lluvia medida)
 */
export function buildVerdict(entries: HourlyEntry[], nowMs: number, drizzleHint: boolean): VerdictLine[] {
  const horizon = Number.isFinite(nowMs) ? nowMs + AHEAD_HOURS * HOUR_MS : Number.POSITIVE_INFINITY
  const ahead = entriesFromNow(entries, nowMs).filter((entry) => entry.timestamp * 1000 <= horizon)
  if (ahead.length === 0) return []

  const baseDate = ahead[0].date
  const lines: VerdictLine[] = []

  const run = rainRuns(ahead, nowMs)[0]
  if (run) {
    const amount = formatMm(run.totalMm)
    let text: string
    if (run.startsNow) {
      text = run.from === run.to ? 'Lluvia prevista ahora' : `Lluvia prevista ahora, hasta las${NBSP}${run.to}`
    } else if (run.from === run.to) {
      text = `Lluvia prevista${dayPrefix(run.date, baseDate)} a las${NBSP}${run.from}`
    } else {
      text = `Lluvia prevista${dayPrefix(run.date, baseDate)} de${NBSP}${run.from} a${NBSP}${run.to}`
    }
    lines.push({ tone: 'rain', text: `${text} · ≈${NBSP}${amount} en total` })
  } else if (drizzleHint) {
    lines.push({ tone: 'rain', text: 'Llovizna posible, sin lluvia medida en el pronóstico' })
  } else {
    const spanHours = (ahead[ahead.length - 1].timestamp * 1000 - nowMs) / HOUR_MS
    const horizonText = spanHours >= AHEAD_HOURS - 1 ? 'en las próximas 24 h' : 'en las próximas horas'
    lines.push({ tone: 'clear', text: `Sin lluvia prevista ${horizonText}` })
  }

  const storm = ahead.find((entry) => entry.convective_risk === 'high' || entry.convective_risk === 'severe')
  if (storm) {
    const level = storm.convective_risk === 'severe' ? 'severo' : 'alto'
    lines.push({
      tone: 'storm',
      text: `Riesgo ${level} de tormentas${dayPrefix(storm.date, baseDate)} a las${NBSP}${storm.hour_label}`,
    })
  } else {
    const gusty = ahead.filter((entry) => (entry.wind_gusts_kmh ?? 0) > GUST_KMH)
    if (gusty.length > 0) {
      const strongest = gusty.reduce((a, b) => ((b.wind_gusts_kmh ?? 0) > (a.wind_gusts_kmh ?? 0) ? b : a))
      lines.push({
        tone: 'wind',
        text: `Ráfagas de hasta ${Math.round(strongest.wind_gusts_kmh ?? 0)}${NBSP}km/h${dayPrefix(strongest.date, baseDate)} a las${NBSP}${strongest.hour_label}`,
      })
    }
  }

  return lines
}
