import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { WindArrow } from '@/components/ui/WindArrow'
import { cn } from '@/lib/utils'
import { formatShortDate } from '@/lib/dates'
import { describeWeatherIcon } from '@/lib/weatherLabels'
import { TREND_NOTICE, describeRain, detailRows, isFirstTrendDay } from '@/lib/forecastRow'
import type { ShownModel } from '@/lib/forecastRow'
import { RainPill } from './RainPill'
import { dayRowId } from './anchors'
import { windColor } from './windColor'
import type { DailyEntry } from '@/lib/api'
import './forecast7dList.css'

interface Props {
  days: DailyEntry[]
  /** Franja con lluvia prevista por fecha, cuando hay horas para calcularla. */
  rainWindows?: Record<string, string>
  /** El modelo de los días en pantalla: decide de qué modelo sale la nubosidad de la columna "En la fila". */
  shownModel?: ShownModel
}

/** Los días, uno debajo del otro: en el celular se lee de corrido, sin deslizar. */
export function Forecast7dList({ days, rainWindows = {}, shownModel = 'consensus' }: Props) {
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
          rainWindow={rainWindows[day.date]}
          shownModel={shownModel}
          showTrendNotice={isFirstTrendDay(days, index)}
        />
      ))}
    </ol>
  )
}

interface DayRowProps {
  day: DailyEntry
  rainWindow?: string
  shownModel: ShownModel
  /** Primer día de tendencia: el aviso va una sola vez, antes de él. */
  showTrendNotice: boolean
}

/** Toda la fila es un botón: tocarla abre y cierra los números de cada modelo. */
function DayRow({ day, rainWindow, shownModel, showTrendNotice }: DayRowProps) {
  const [open, setOpen] = useState(false)
  const isToday = day.day_label === 'Hoy'
  const condition = describeWeatherIcon(day.icon)
  const rain = describeRain(day)
  const wind = windColor(day.wind_intensity)
  const hasWind = day.wind_speed_max !== null
  const showShift = Boolean(day.wind_shift && day.wind_dir_cardinal)
  const hasRain = rain.pill !== null || rain.disagreement !== null
  const hasMeta = hasRain || hasWind || showShift
  const panelId = `${dayRowId(day.date)}-detalle`

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

      <button
        type="button"
        className="day-row__button px-4 py-3"
        data-meta={hasMeta}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
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
          <WeatherIcon code={day.icon} size={40} glow />
        </span>

        {/* La condición en palabras: con la palabra a la vista el ícono queda decorativo */}
        {condition && (
          <span className="day-row__cond text-sm leading-snug" style={{ color: 'var(--color-foreground)' }}>
            {condition}
          </span>
        )}

        {hasMeta && (
          <span className="day-row__meta flex flex-wrap items-center gap-x-3 gap-y-1">
            {rain.pill !== null && <RainPill inline label={rain.pill} window={rain.showWindow ? rainWindow : undefined} />}
            {rain.disagreement !== null && (
              <span className="text-xs" style={{ color: 'var(--color-info)' }}>
                {rain.disagreement}
              </span>
            )}
            {hasWind && (
              <span className="inline-flex items-center gap-1 text-xs" style={{ color: wind }}>
                {day.wind_icon && <WeatherIcon code={day.wind_icon} size={16} />}
                <span className="sr-only">Viento </span>
                {Math.round(day.wind_speed_max ?? 0)} km/h
                {day.wind_dir_dominant_deg !== null && day.wind_dir_dominant_deg !== undefined && (
                  <WindArrow deg={day.wind_dir_dominant_deg} size={12} color={wind} />
                )}
                {day.wind_dir_cardinal && (
                  <span style={{ color: 'var(--color-muted-foreground)' }}>{day.wind_dir_cardinal}</span>
                )}
              </span>
            )}
            {showShift && (
              <span
                className="text-[11px] px-1.5 py-0.5 rounded-full"
                style={{ background: 'rgba(200,168,75,0.12)', color: '#c8a84b' }}
              >
                ↻ Rota al {day.wind_dir_cardinal}
              </span>
            )}
          </span>
        )}

        {/* Máxima y mínima; para un lector de pantalla, con su nombre (antes "23° 13°" sin decir cuál era cuál) */}
        <span className="day-row__temps tabular-nums leading-none text-right">
          <span className="sr-only">Máxima </span>
          <span className="text-lg font-bold" style={{ color: 'var(--color-foreground)' }}>
            {day.temp_max !== null ? `${Math.round(day.temp_max)}°` : '—'}
          </span>
          <span className="sr-only">, mínima </span>{' '}
          <span className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
            {day.temp_min !== null ? `${Math.round(day.temp_min)}°` : '—'}
          </span>
          <span className="sr-only">. Detalle por modelo</span>
          <ChevronDown
            size={16}
            aria-hidden="true"
            className={cn(
              'ml-1.5 inline-block align-middle transition-transform motion-reduce:transition-none',
              open && 'rotate-180',
            )}
            style={{ color: 'var(--color-muted-foreground)' }}
          />
        </span>
      </button>

      <div id={panelId} hidden={!open} className="px-4 pb-3 pt-1">
        {open && <ModelDetailTable day={day} shownModel={shownModel} />}
      </div>
    </li>
  )
}

interface ModelDetailTableProps {
  day: DailyEntry
  shownModel: ShownModel
}

/** Los números de cada modelo para el día; la última columna es lo que usa la fila. */
function ModelDetailTable({ day, shownModel }: ModelDetailTableProps) {
  const rows = detailRows(day, shownModel)
  return (
    <table className="day-detail w-full table-fixed text-xs tabular-nums" style={{ color: 'var(--color-foreground)' }}>
      <caption className="sr-only">Detalle por modelo, {day.day_label_long}</caption>
      <thead style={{ color: 'var(--color-muted-foreground)' }}>
        <tr>
          <th scope="col" className="w-[30%] px-1 py-1.5 text-left font-medium">
            <span className="sr-only">Dato</span>
          </th>
          <th scope="col" className="px-1 py-1.5 text-left font-semibold">GFS</th>
          <th scope="col" className="px-1 py-1.5 text-left font-semibold">ECMWF</th>
          <th scope="col" className="px-1 py-1.5 text-left font-semibold">En la fila</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className="border-t" style={{ borderColor: 'var(--color-border)' }}>
            <th scope="row" className="px-1 py-1.5 text-left align-top font-normal" style={{ color: 'var(--color-muted-foreground)' }}>
              {row.label}
            </th>
            <td className="px-1 py-1.5 align-top">{row.gfs}</td>
            <td className="px-1 py-1.5 align-top">{row.ecmwf}</td>
            <td className="px-1 py-1.5 align-top font-semibold">{row.inRow}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
