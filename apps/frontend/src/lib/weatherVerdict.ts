import type { HourlyEntry, SmnAlerta } from '@/lib/api'
import { arDateKey } from './dates.ts'
import { alertLevel, criticalAlertas, vigenciaText, type CriticalLevel } from './smnAlertas.ts'

/**
 * Lluvia = más de 0,1 mm en el tramo. Es el mismo umbral con el que el backend arma
 * `rain_today.has_rain_today` (dashboard_builder). No se usa `precip_prob` de las
 * entradas horarias: con Windy el backend la aproxima como 100 si llueve y 0 si no,
 * así que un "100 %" horario no es una probabilidad.
 */
export const RAIN_MM = 0.1

/** Ráfaga que merece aviso: el mismo umbral con el que la tira horaria ya marcaba las fuertes. */
export const GUST_KMH = 40

/**
 * Clases de intensidad de lluvia (AMS / NWS), en mm por hora: débil hasta 2,5; moderada de 2,5
 * a 7,6; fuerte por encima de 7,6.
 */
export const LIGHT_RAIN_MAX_MM_H = 2.5
export const MODERATE_RAIN_MAX_MM_H = 7.6

const HOUR_MS = 3_600_000
const AHEAD_HOURS = 24
const MIN_SLOT_HOURS = 0.25
const MAX_SLOT_HOURS = 6

/** Espacio de no separación: que "4 mm" o "a las 17:00" no se partan entre dos renglones. */
const NBSP = String.fromCharCode(0xa0)

export type VerdictTone = 'rain' | 'clear' | 'wind' | 'storm' | 'alert'
export type RainIntensity = 'débil' | 'moderada' | 'fuerte'

/** Un tramo de una línea del veredicto; `fact` marca los datos duros (hora, cantidad, velocidad). */
export interface VerdictSegment {
  text: string
  fact?: boolean
}

export interface VerdictLine {
  tone: VerdictTone
  /** Texto plano de la línea (lo que se anuncia): es la unión de `segments`. */
  text: string
  segments: VerdictSegment[]
  /** Nivel del aviso, solo en las líneas de tono "alert": define el color y el ícono. */
  level?: CriticalLevel
}

type LinePart = string | { fact: string }

const fact = (text: string): LinePart => ({ fact: text })

function line(tone: VerdictTone, ...parts: LinePart[]): VerdictLine {
  const segments = parts.map((part): VerdictSegment => (typeof part === 'string' ? { text: part } : { text: part.fact, fact: true }))
  return { tone, text: segments.map((segment) => segment.text).join(''), segments }
}

export interface RainRun {
  date: string
  from: string
  to: string
  totalMm: number
  /** Mayor intensidad horaria de una franja del tramo. */
  peakMmPerHour: number
  intensity: RainIntensity
  /** El tramo ya está en curso a la hora de referencia. */
  startsNow: boolean
}

export function isRainy(entry: HourlyEntry): boolean {
  return (entry.precip_mm ?? 0) > RAIN_MM
}

/** Clase de intensidad de una lluvia de `mmPerHour` mm/h. */
export function rainIntensity(mmPerHour: number): RainIntensity {
  if (mmPerHour > MODERATE_RAIN_MAX_MM_H) return 'fuerte'
  if (mmPerHour >= LIGHT_RAIN_MAX_MM_H) return 'moderada'
  return 'débil'
}

/**
 * Horas que cubre la franja `index`: hoy son 3 h (el backend arma franjas de 3 h con Open-Meteo), pero
 * puede haber franjas de 1 h. Se infiere de la distancia al vecino (la última usa el paso anterior)
 * para convertir milímetros en mm/h.
 */
export function slotHours(entries: HourlyEntry[], index: number): number {
  const current = entries[index]
  const next = entries[index + 1]
  const previous = entries[index - 1]
  const seconds = next
    ? next.timestamp - current.timestamp
    : previous
      ? current.timestamp - previous.timestamp
      : 3600
  const hours = seconds / 3600
  if (!Number.isFinite(hours) || hours <= 0) return 1
  return Math.min(Math.max(hours, MIN_SLOT_HOURS), MAX_SLOT_HOURS)
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
  entries.forEach((entry, index) => {
    if (!isRainy(entry)) {
      open = null
      return
    }
    const mm = entry.precip_mm ?? 0
    const rate = mm / slotHours(entries, index)
    if (open && open.date === entry.date) {
      open.to = entry.hour_label
      open.totalMm += mm
      open.peakMmPerHour = Math.max(open.peakMmPerHour, rate)
      open.intensity = rainIntensity(open.peakMmPerHour)
    } else {
      open = {
        date: entry.date,
        from: entry.hour_label,
        to: entry.hour_label,
        totalMm: mm,
        peakMmPerHour: rate,
        intensity: rainIntensity(rate),
        startsNow: Number.isFinite(nowMs) && entry.timestamp * 1000 <= nowMs,
      }
      runs.push(open)
    }
  })
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

/** Cantidad de lluvia en palabras: "< 1 mm", "3 mm", "12 mm". */
export function formatMm(mm: number): string {
  if (mm < 1) return `<${NBSP}1${NBSP}mm`
  return `${Math.round(mm).toLocaleString('es-AR')}${NBSP}mm`
}

function dayPrefix(date: string, baseDate: string): string {
  return date === baseDate ? '' : ' mañana'
}

/** "≈ 4 mm" o "menos de 1 mm": nunca "≈ < 1 mm". */
function approxAmount(mm: number): string {
  return mm < 1 ? `menos de 1${NBSP}mm` : `≈${NBSP}${formatMm(mm)}`
}

/** Cuándo llueve un tramo, sin el verbo: "ahora, hasta las 15:00", "a las 16:00", "de 16:00 a 18:00". */
function whenText(run: RainRun): string {
  if (run.startsNow) return run.from === run.to ? 'ahora' : `ahora, hasta las${NBSP}${run.to}`
  if (run.from === run.to) return `a las${NBSP}${run.from}`
  return `de${NBSP}${run.from} a${NBSP}${run.to}`
}

/** El tramo con más agua; a igual cantidad, el más próximo. */
function strongest(runs: RainRun[]): RainRun {
  return runs.reduce((a, b) => (b.totalMm > a.totalMm ? b : a))
}

/** Línea del aviso crítico que encabeza el veredicto: "Aviso rojo del SMN: Tormentas · hasta las 21:00". */
function alertLine(alerta: SmnAlerta, others: number, nowMs: number): VerdictLine {
  const level = alertLevel(alerta.nivel) as CriticalLevel
  const vigencia = vigenciaText(alerta, nowMs)
  const parts: LinePart[] = [`Aviso ${level} del SMN: `, fact(alerta.tipo)]
  if (vigencia) parts.push(' · ', fact(keepTogether(vigencia)))
  if (others > 0) parts.push(` · +${others} ${others === 1 ? 'aviso' : 'avisos'} más`)
  return { ...line('alert', ...parts), level }
}

/** Que "hasta las 21:00" o "hasta el sáb 23:00" no se partan entre dos renglones. */
function keepTogether(text: string): string {
  return text.replaceAll('las ', `las${NBSP}`).replace(/\b(lun|mar|mié|jue|vie|sáb|dom) /g, `$1${NBSP}`)
}

/**
 * Lo que viene en las próximas 24 h, en hechos: hora, cantidad e intensidad. Sin porcentajes ni
 * promesas: si el dato no alcanza para decirlo, no se dice.
 *
 * El titular lo manda la gravedad, no el orden en que se calcula cada cosa:
 * 1. Un aviso crítico (naranja o rojo) del SMN vigente: es el titular y **no hay línea de lluvia**.
 *    El aviso y el modelo son fuentes distintas y pueden contradecirse ("Sin lluvia prevista" bajo
 *    un aviso de tormentas severas): con un aviso vigente el héroe habla solo por el aviso, más las
 *    ráfagas y el riesgo de tormentas del modelo. Los avisos amarillos no cambian nada.
 * 2. Sin aviso, un riesgo alto o severo de tormentas encabeza; la lluvia prevista lo acompaña, pero
 *    no se le pone debajo un "sin lluvia" ni un "llovizna posible".
 * 3. Sin nada de eso, la lluvia: el titular es el tramo más fuerte (una llovizna previa no puede
 *    tapar un chaparrón posterior) y una segunda línea nombra al siguiente.
 *
 * @param drizzleHint el backend marcó "Llovizna posible" (humedad y nubosidad altas sin lluvia medida)
 * @param alertas avisos vigentes del SMN
 */
export function buildVerdict(
  entries: HourlyEntry[],
  nowMs: number,
  drizzleHint: boolean,
  alertas: SmnAlerta[] = [],
): VerdictLine[] {
  const critical = criticalAlertas(alertas)
  const alertLines = critical.length > 0 ? [alertLine(critical[0], critical.length - 1, nowMs)] : []

  const horizon = Number.isFinite(nowMs) ? nowMs + AHEAD_HOURS * HOUR_MS : Number.POSITIVE_INFINITY
  const ahead = entriesFromNow(entries, nowMs).filter((entry) => entry.timestamp * 1000 <= horizon)
  if (ahead.length === 0) return alertLines

  // "Mañana" se cuenta desde el día argentino de la hora de referencia. La fecha de la primera franja
  // no sirve: a las 23:30, con franjas de 3 h, la próxima ya es la de las 00:00 del día siguiente.
  const baseDate = Number.isFinite(nowMs) ? arDateKey(nowMs) : ahead[0].date
  const lines: VerdictLine[] = [...alertLines]

  const storm = ahead.find((entry) => entry.convective_risk === 'high' || entry.convective_risk === 'severe')
  if (storm) {
    const level = storm.convective_risk === 'severe' ? 'severo' : 'alto'
    lines.push(
      line('storm', `Riesgo ${level} de tormentas${dayPrefix(storm.date, baseDate)} a las${NBSP}`, fact(storm.hour_label)),
    )
  }

  // Con un aviso crítico vigente no hay línea de lluvia (ver arriba).
  if (critical.length === 0) {
    const runs = rainRuns(ahead, nowMs)
    if (runs.length > 0) {
      const main = strongest(runs)
      lines.push(
        line(
          'rain',
          `Lluvia ${main.intensity} prevista${dayPrefix(main.date, baseDate)} `,
          fact(whenText(main)),
          ' · ',
          fact(approxAmount(main.totalMm)),
          ' en total',
        ),
      )

      const others = runs.filter((run) => run !== main)
      if (others.length > 0) {
        const next = strongest(others)
        const when = runs.indexOf(next) < runs.indexOf(main) ? 'Antes' : 'Después'
        lines.push(
          line(
            'rain',
            `${when}: lluvia ${next.intensity}${dayPrefix(next.date, baseDate)} `,
            fact(whenText(next)),
            ' · ',
            fact(approxAmount(next.totalMm)),
          ),
        )
      }
    } else if (!storm) {
      if (drizzleHint) {
        lines.push(line('rain', 'Llovizna posible, sin lluvia medida en el pronóstico'))
      } else {
        const spanHours = (ahead[ahead.length - 1].timestamp * 1000 - nowMs) / HOUR_MS
        const horizonText = spanHours >= AHEAD_HOURS - 1 ? `en las próximas 24${NBSP}h` : 'en las próximas horas'
        lines.push(line('clear', `Sin lluvia prevista ${horizonText}`))
      }
    }
  }

  if (!storm) {
    const gusty = ahead.filter((entry) => (entry.wind_gusts_kmh ?? 0) > GUST_KMH)
    if (gusty.length > 0) {
      const top = gusty.reduce((a, b) => ((b.wind_gusts_kmh ?? 0) > (a.wind_gusts_kmh ?? 0) ? b : a))
      lines.push(
        line(
          'wind',
          'Ráfagas de hasta ',
          fact(`${Math.round(top.wind_gusts_kmh ?? 0)}${NBSP}km/h`),
          `${dayPrefix(top.date, baseDate)} a las${NBSP}`,
          fact(top.hour_label),
        ),
      )
    }
  }

  return lines
}
