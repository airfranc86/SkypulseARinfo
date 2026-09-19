import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { WindArrow } from '@/components/ui/WindArrow'
import { describeWeatherIcon, precipKind } from '@/lib/weatherLabels'
import { RainPill } from './RainPill'
import { ConfidenceChip } from './ConfidenceChip'
import type { DailyEntry } from '@/lib/api'

const HIGHLIGHT_COLOR = '200,168,75' // primary gold (RGB para componer alpha)

interface Props {
  days: DailyEntry[]
  /** Franja con lluvia prevista por fecha (solo hoy y mañana tienen horas). */
  rainWindows?: Record<string, string>
  /** Solo el consenso mide desacuerdo entre modelos: con un modelo suelto, "confianza" no significa nada. */
  showConfidence?: boolean
}

export function Forecast7dCards({ days, rainWindows = {}, showConfidence = false }: Props) {
  return (
    <div className="flex gap-3 overflow-x-auto pt-2 pb-1 pr-20" style={{ scrollbarWidth: 'thin', scrollSnapType: 'x mandatory' }}>
      {days.map((day, idx) => {
        const isHighlight = idx === 0
        return (
          <DayCard
            key={day.date}
            day={day}
            highlighted={isHighlight}
            rainWindow={rainWindows[day.date]}
            showConfidence={showConfidence}
          />
        )
      })}
      {/* Espacio al final del scroll para que la última card no quede tapada
          por ScrollToTopBubble (fixed, bottom-right, ocupa los últimos 68px). */}
    </div>
  )
}

interface DayCardProps {
  day: DailyEntry
  highlighted?: boolean
  rainWindow?: string
  showConfidence: boolean
}

function DayCard({ day, highlighted = false, rainWindow, showConfidence }: DayCardProps) {
  const hasPrecip = (day.precip_prob ?? 0) > 15
  const condition = describeWeatherIcon(day.icon)
  // El tipo sale del ícono: con nieve, "🌧 40%" contaba otra historia.
  const precipLabel = precipKind(day.icon) ?? 'Lluvia'

  return (
    <div
      className="relative shrink-0 flex flex-col items-center gap-2 rounded-2xl px-4 py-4"
      style={{
        minWidth: '112px',
        scrollSnapAlign: 'start',
        background: 'var(--color-card)',
        border: highlighted
          ? `1.5px solid rgba(${HIGHLIGHT_COLOR},0.55)`
          : '1px solid var(--color-border)',
        boxShadow: highlighted ? `0 0 18px rgba(${HIGHLIGHT_COLOR},0.18)` : 'none',
      }}
    >
      {highlighted && (
        <span
          className="absolute -top-2 text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full"
          style={{ background: 'var(--color-primary)', color: 'var(--color-primary-foreground)' }}
        >
          Hoy
        </span>
      )}

      {/* Day label */}
      <p className="text-xs font-medium capitalize" style={{ color: 'var(--color-muted-foreground)' }}>
        {day.day_label}
      </p>

      {/* Icon + condición en palabras (el ícono solo no llega a lectores de pantalla;
          con la palabra visible al lado, el ícono queda decorativo) */}
      <WeatherIcon code={day.icon} size={56} glow />
      {condition && (
        <p
          className="text-xs text-center leading-tight min-h-[2rem]"
          style={{ color: 'var(--color-muted-foreground)' }}
        >
          {condition}
        </p>
      )}

      {/* Max / Min */}
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold" style={{ color: 'var(--color-foreground)' }}>
          {day.temp_max !== null ? `${Math.round(day.temp_max)}°` : '—'}
        </span>
        <span className="text-sm font-normal" style={{ color: 'var(--color-muted-foreground)' }}>
          {day.temp_min !== null ? `${Math.round(day.temp_min)}°` : '—'}
        </span>
      </div>

      {/* Precip prob */}
      {hasPrecip && <RainPill kind={precipLabel} pct={day.precip_prob ?? 0} window={rainWindow} />}

      {showConfidence && <ConfidenceChip label={day.confidence_label} />}

      {/* Viento — siempre visible si hay dato */}
      {day.wind_speed_max !== null && (
        <div className="flex flex-col items-center gap-0.5">
          <div className="flex items-center gap-1 flex-wrap justify-center">
            {day.wind_icon && <WeatherIcon code={day.wind_icon} size={18} />}
            <span
              className="text-xs"
              style={{
                color: day.wind_intensity === 'intensa'
                  ? '#e03535'
                  : day.wind_intensity === 'moderada'
                    ? '#c8a84b'
                    : 'var(--color-muted-foreground)',
              }}
            >
              {Math.round(day.wind_speed_max)} km/h
            </span>
            {day.wind_dir_dominant_deg !== null && day.wind_dir_dominant_deg !== undefined && (
              <WindArrow
                deg={day.wind_dir_dominant_deg}
                size={12}
                color={
                  day.wind_intensity === 'intensa' ? '#e03535'
                  : day.wind_intensity === 'moderada' ? '#c8a84b'
                  : 'var(--color-muted-foreground)'
                }
              />
            )}
            {day.wind_dir_cardinal && (
              <span className="text-[11px]" style={{ color: 'var(--color-muted-foreground)' }}>
                {day.wind_dir_cardinal}
              </span>
            )}
          </div>
          {day.wind_shift && day.wind_dir_cardinal && (
            <span
              className="text-[11px] px-1.5 py-0.5 rounded-full"
              style={{ background: 'rgba(200,168,75,0.12)', color: '#c8a84b' }}
            >
              ↻ Rota al {day.wind_dir_cardinal}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
