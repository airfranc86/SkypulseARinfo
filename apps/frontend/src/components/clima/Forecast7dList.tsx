import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { WindArrow } from '@/components/ui/WindArrow'
import { cn } from '@/lib/utils'
import { formatShortDate } from '@/lib/dates'
import { describeWeatherIcon, precipKind } from '@/lib/weatherLabels'
import { RainPill } from './RainPill'
import { ConfidenceChip } from './ConfidenceChip'
import { dayRowId } from './anchors'
import { windColor } from './windColor'
import type { DailyEntry } from '@/lib/api'
import './forecast7dList.css'

const PILL_MIN_PROB = 15

interface Props {
  days: DailyEntry[]
  /** Franja con lluvia prevista por fecha, cuando hay horas para calcularla. */
  rainWindows?: Record<string, string>
  /** Solo el consenso mide desacuerdo entre modelos: con un modelo suelto, "confianza" no significa nada. */
  showConfidence?: boolean
}

/** Los días, uno debajo del otro: en el celular se lee de corrido, sin deslizar. */
export function Forecast7dList({ days, rainWindows = {}, showConfidence = false }: Props) {
  return (
    <ol
      aria-label={`Pronóstico de ${days.length} días`}
      className="forecast-list divide-y"
      style={{ borderColor: 'var(--color-border)' }}
    >
      {days.map((day) => (
        <DayRow key={day.date} day={day} rainWindow={rainWindows[day.date]} showConfidence={showConfidence} />
      ))}
    </ol>
  )
}

interface DayRowProps {
  day: DailyEntry
  rainWindow?: string
  showConfidence: boolean
}

function DayRow({ day, rainWindow, showConfidence }: DayRowProps) {
  const isToday = day.day_label === 'Hoy'
  const condition = describeWeatherIcon(day.icon)
  const showRain = (day.precip_prob ?? 0) > PILL_MIN_PROB
  const wind = windColor(day.wind_intensity)
  const hasWind = day.wind_speed_max !== null
  const showShift = Boolean(day.wind_shift && day.wind_dir_cardinal)
  // "ALTA" no dice nada (ver ConfidenceChip): sin aviso de confianza no hay chip y la fila puede ser más baja.
  const showChip = showConfidence && day.confidence_label !== 'ALTA'
  const hasMeta = showRain || hasWind || showShift || showChip

  return (
    <li
      // id y tabIndex: los "Próximos días" llevan hasta acá cuando ese día no tiene horas.
      id={dayRowId(day.date)}
      tabIndex={-1}
      data-meta={hasMeta}
      className="day-row scroll-mt-52 outline-none px-4 py-3"
      style={isToday ? { background: 'rgba(200,168,75,0.06)' } : undefined}
    >
      {/* Día y fecha: con siete días seguidos "dom" y "lun" se repiten, la fecha desambigua */}
      <p className="day-row__day leading-tight">
        <span
          className={cn('block text-sm capitalize', isToday ? 'font-semibold' : 'font-medium')}
          style={{ color: isToday ? 'var(--color-primary)' : 'var(--color-foreground)' }}
        >
          {day.day_label}
        </span>
        <span className="block text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
          {formatShortDate(day.date)}
        </span>
      </p>

      <div className="day-row__icon">
        <WeatherIcon code={day.icon} size={40} glow />
      </div>

      {/* La condición en palabras: con la palabra a la vista el ícono queda decorativo */}
      {condition && (
        <p className="day-row__cond text-sm leading-snug" style={{ color: 'var(--color-foreground)' }}>
          {condition}
        </p>
      )}

      {hasMeta && (
        <div className="day-row__meta flex flex-wrap items-center gap-x-3 gap-y-1">
          {showRain && (
            <RainPill inline kind={precipKind(day.icon) ?? 'Lluvia'} pct={day.precip_prob ?? 0} window={rainWindow} />
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
          {showChip && <ConfidenceChip label={day.confidence_label} />}
        </div>
      )}

      {/* Máxima y mínima; para un lector de pantalla, con su nombre (antes "23° 13°" sin decir cuál era cuál) */}
      <p className="day-row__temps tabular-nums leading-none text-right">
        <span className="sr-only">Máxima </span>
        <span className="text-lg font-bold" style={{ color: 'var(--color-foreground)' }}>
          {day.temp_max !== null ? `${Math.round(day.temp_max)}°` : '—'}
        </span>
        <span className="sr-only">, mínima </span>{' '}
        <span className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
          {day.temp_min !== null ? `${Math.round(day.temp_min)}°` : '—'}
        </span>
      </p>
    </li>
  )
}
