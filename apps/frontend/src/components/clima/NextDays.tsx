import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { describeWeatherIcon, precipKind } from '@/lib/weatherLabels'
import { RainPill } from './RainPill'
import type { DailyEntry } from '@/lib/api'

interface NextDaysProps {
  /** Los días que siguen a hoy (el de hoy ya está en el hero). */
  days: DailyEntry[]
  /** Franja con lluvia prevista por fecha, cuando hay horas para calcularla. */
  rainWindows: Record<string, string>
}

const PILL_MIN_PROB = 15

/** Los próximos días de un vistazo, sin abrir el detalle: un solo panel, una columna por día. */
export function NextDays({ days, rainWindows }: NextDaysProps) {
  if (days.length === 0) return null

  return (
    <section
      aria-label="Próximos días"
      className="rounded-2xl grid divide-x"
      style={{
        gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))`,
        background: 'var(--color-card)',
        border: '1px solid var(--color-border)',
      }}
    >
      {days.map((day) => {
        const condition = describeWeatherIcon(day.icon)
        const showRain = (day.precip_prob ?? 0) > PILL_MIN_PROB
        return (
          <div
            key={day.date}
            className="flex flex-col items-center gap-1.5 px-2 py-4 text-center"
            style={{ borderColor: 'var(--color-border)' }}
          >
            <p className="text-xs font-medium capitalize" style={{ color: 'var(--color-muted-foreground)' }}>
              {day.day_label}
            </p>
            <WeatherIcon code={day.icon} size={44} glow />
            {condition && <p className="sr-only">{condition}</p>}
            <p className="tabular-nums leading-none">
              <span className="text-lg font-bold" style={{ color: 'var(--color-foreground)' }}>
                {day.temp_max !== null ? `${Math.round(day.temp_max)}°` : '—'}
              </span>{' '}
              <span className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                {day.temp_min !== null ? `${Math.round(day.temp_min)}°` : '—'}
              </span>
            </p>
            {showRain && (
              <RainPill
                kind={precipKind(day.icon) ?? 'Lluvia'}
                pct={day.precip_prob ?? 0}
                window={rainWindows[day.date]}
              />
            )}
          </div>
        )
      })}
    </section>
  )
}
