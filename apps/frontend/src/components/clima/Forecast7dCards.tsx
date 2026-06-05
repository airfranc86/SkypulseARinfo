import { WeatherIcon } from '@/components/ui/WeatherIcon'
import type { DailyEntry } from '@/lib/api'
import { confidenceColor } from '@/lib/confidence'

interface Props {
  days: DailyEntry[]
}

export function Forecast7dCards({ days }: Props) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-1" style={{ scrollbarWidth: 'thin', scrollSnapType: 'x mandatory' }}>
      {days.map((day, idx) => {
        const isHighlight = idx === 0 || day.confidence_label === 'ALTA'
        return <DayCard key={day.date} day={day} highlighted={isHighlight} />
      })}
    </div>
  )
}

function DayCard({ day, highlighted = false }: { day: DailyEntry; highlighted?: boolean }) {
  const confColor = confidenceColor(day.confidence_label)
  const hasPrecip = (day.precip_prob ?? 0) > 15

  return (
    <div
      className="shrink-0 flex flex-col items-center gap-2 rounded-2xl px-4 py-4"
      style={{
        minWidth: '100px',
        scrollSnapAlign: 'start',
        background: 'var(--color-card)',
        border: highlighted
          ? `1px solid ${confColor}55`
          : '1px solid var(--color-border)',
        boxShadow: highlighted ? `0 0 14px ${confColor}14` : 'none',
      }}
    >
      {/* Day label */}
      <p className="text-xs font-medium capitalize" style={{ color: 'var(--color-muted-foreground)' }}>
        {day.day_label}
      </p>

      {/* Icon */}
      <WeatherIcon code={day.icon} size={40} />

      {/* Max / Min */}
      <div className="flex items-baseline gap-1">
        <span className="text-base font-bold" style={{ color: 'var(--color-foreground)' }}>
          {day.temp_max !== null ? `${Math.round(day.temp_max)}°` : '—'}
        </span>
        <span className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
          {day.temp_min !== null ? `${Math.round(day.temp_min)}°` : '—'}
        </span>
      </div>

      {/* Precip prob */}
      {hasPrecip && (
        <span className="text-xs" style={{ color: '#5aaad8' }}>
          🌧 {Math.round(day.precip_prob ?? 0)}%
        </span>
      )}

      {/* Viento — siempre visible si hay dato */}
      {day.wind_speed_max !== null && (
        <div className="flex flex-col items-center gap-0.5">
          <div className="flex items-center gap-1">
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
              {Math.round(day.wind_speed_max)} km/h{day.wind_dir_cardinal ? ` ${day.wind_dir_cardinal}` : ''}
            </span>
          </div>
          {day.wind_shift && day.wind_dir_cardinal && (
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-full"
              style={{ background: 'rgba(200,168,75,0.12)', color: '#c8a84b' }}
            >
              ↻ Rota al {day.wind_dir_cardinal}
            </span>
          )}
        </div>
      )}

      {/* Confidence badge */}
      <span
        className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
        style={{ background: `${confColor}18`, color: confColor }}
      >
        {day.confidence_label}
      </span>
    </div>
  )
}
