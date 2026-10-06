import { Droplets } from 'lucide-react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { cn } from '@/lib/utils'
import { formatShortDate } from '@/lib/dates'
import { TREND_NOTICE, describeRow, isFirstTrendDay } from '@/lib/forecastRow'
import type { RowText } from '@/lib/forecastRow'
import { dayRowId } from './anchors'
import type { DailyEntry } from '@/lib/api'
import './forecast7dList.css'

interface Props {
  days: DailyEntry[]
  /** Franja con lluvia prevista por fecha, cuando hay horas para calcularla. */
  rainWindows?: Record<string, string>
}

/** Los días, uno debajo del otro: en el celular se lee de corrido, sin deslizar. */
export function Forecast7dList({ days, rainWindows = {} }: Props) {
  return (
    <ol
      aria-label={`Pronóstico de ${days.length} días`}
      className="forecast-list divide-y"
      style={{ borderColor: 'var(--color-border)' }}
    >
      {days.map((day, index) => (
        <DayRow
          key={day.date}
          day={day}
          row={describeRow(days, index, rainWindows[day.date])}
          showTrendNotice={isFirstTrendDay(days, index)}
        />
      ))}
    </ol>
  )
}

interface DayRowProps {
  day: DailyEntry
  /** The row's texts: headline, rain note and wind (see describeRow). */
  row: RowText
  /** Primer día de tendencia: el aviso va una sola vez, antes de él. */
  showTrendNotice: boolean
}

/**
 * One day, read only (no detail to open). Reading order for a screen reader: day, condition with its
 * rain, temperatures, wind; the grid puts the wind line visually under the condition.
 */
function DayRow({ day, row, showTrendNotice }: DayRowProps) {
  const isToday = day.day_label === 'Hoy'
  const hasMeta = row.rainNote !== null || row.wind !== null

  return (
    <li
      // id y tabIndex: los "Próximos días" llevan hasta acá cuando ese día no tiene horas.
      id={dayRowId(day.date)}
      tabIndex={-1}
      className="scroll-mt-52 outline-none"
      style={isToday ? { background: 'rgba(200,168,75,0.06)' } : undefined}
    >
      {showTrendNotice && (
        <p className="px-4 pt-3 text-xs font-medium" style={{ color: 'var(--color-muted-foreground)' }}>
          {TREND_NOTICE}
        </p>
      )}

      <div className="day-row px-4 py-3" data-meta={hasMeta}>
        {/* Día y fecha: con siete días seguidos "dom" y "lun" se repiten, la fecha desambigua */}
        <span className="day-row__day leading-tight">
          <span
            className={cn('block text-sm capitalize', isToday ? 'font-semibold' : 'font-medium')}
            style={{ color: isToday ? 'var(--color-primary)' : 'var(--color-foreground)' }}
          >
            {day.day_label}
          </span>
          <span className="block text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            {formatShortDate(day.date)}
          </span>
        </span>

        <span className="day-row__icon">
          <WeatherIcon code={day.icon} size={32} glow />
        </span>

        {row.headline !== null && <Headline row={row} />}

        {/* Máxima y mínima; para un lector de pantalla, con su nombre */}
        <span className="day-row__temps tabular-nums leading-none text-right whitespace-nowrap">
          <span className="sr-only">Máxima </span>
          <span className="text-lg font-bold" style={{ color: 'var(--color-foreground)' }}>
            {day.temp_max !== null ? `${Math.round(day.temp_max)}°` : '—'}
          </span>
          <span className="sr-only">, mínima </span>{' '}
          <span className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
            {day.temp_min !== null ? `${Math.round(day.temp_min)}°` : '—'}
          </span>
        </span>

        {hasMeta && <MetaLine row={row} />}
      </div>
    </li>
  )
}

/** Line 1: one rain element (phrase with its probability) or the sky in words. */
function Headline({ row }: { row: RowText }) {
  return (
    <span className="day-row__cond text-sm leading-snug">
      {row.rainy ? (
        <span className="font-medium" style={{ color: 'var(--color-info)' }}>
          <Droplets size={12} strokeWidth={2} aria-hidden="true" className="mr-1 inline-block align-[-1px]" />
          {row.headline}
        </span>
      ) : (
        <span style={{ color: 'var(--color-muted-foreground)' }}>{row.headline}</span>
      )}
      {/* The rain note is read with the rain, not after the temperatures */}
      {row.rainNote !== null && <span className="sr-only">, {row.rainNote}</span>}
    </span>
  )
}

/** Line 2, grey: the rain hours or "poca cantidad", then the wind (amber, with words, when it rotates and rises). */
function MetaLine({ row }: { row: RowText }) {
  const { rainNote, wind } = row
  return (
    <p className="day-row__meta text-xs leading-snug" style={{ color: 'var(--color-muted-foreground)' }}>
      {rainNote !== null && <span aria-hidden="true">{rainNote}</span>}
      {rainNote !== null && wind !== null && <span aria-hidden="true"> · </span>}
      {wind !== null && (
        <span
          className={wind.highlight ? 'font-medium' : undefined}
          style={wind.highlight ? { color: 'var(--color-watch)' } : undefined}
        >
          {wind.text}
        </span>
      )}
    </p>
  )
}
