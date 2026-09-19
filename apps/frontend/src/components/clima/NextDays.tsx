import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { formatShortDate } from '@/lib/dates'
import { describeWeatherIcon, precipKind } from '@/lib/weatherLabels'
import { RainPill } from './RainPill'
import { ConfidenceChip } from './ConfidenceChip'
import type { DailyEntry } from '@/lib/api'

interface NextDaysProps {
  /** Los días que siguen a hoy (el de hoy ya está en el hero). */
  days: DailyEntry[]
  /** Franja con lluvia prevista por fecha, cuando hay horas para calcularla. */
  rainWindows: Record<string, string>
  /** Solo el consenso mide desacuerdo entre modelos (ver ConfidenceChip). */
  showConfidence?: boolean
  /** Se eligió un día: lleva a sus horas o, si no las tiene, a su fila en el pronóstico de 7 días. */
  onSelectDay: (date: string) => void
}

const PILL_MIN_PROB = 15

/** Los próximos días de un vistazo, sin abrir el detalle: un solo panel, una columna por día que se toca. */
export function NextDays({ days, rainWindows, showConfidence = false, onSelectDay }: NextDaysProps) {
  if (days.length === 0) return null

  return (
    <section
      aria-label="Próximos días"
      className="rounded-2xl"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <ul className="grid divide-x" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
        {days.map((day) => {
          const condition = describeWeatherIcon(day.icon)
          const showRain = (day.precip_prob ?? 0) > PILL_MIN_PROB
          return (
            <li key={day.date} className="p-1 min-w-0" style={{ borderColor: 'var(--color-border)' }}>
              <button
                type="button"
                onClick={() => onSelectDay(day.date)}
                className="w-full h-full flex flex-col items-center gap-1.5 rounded-xl px-1 py-3 text-center transition-colors motion-reduce:transition-none hover:bg-[rgba(200,168,75,0.07)] active:bg-[rgba(200,168,75,0.12)]"
              >
                <span className="text-center leading-tight" style={{ color: 'var(--color-muted-foreground)' }}>
                  <span className="sr-only">Ver las horas de </span>
                  <span className="block text-xs font-medium capitalize">{day.day_label}</span>
                  <span className="block text-[11px]">{formatShortDate(day.date)}</span>
                </span>
                <WeatherIcon code={day.icon} size={44} glow />
                {condition && <span className="sr-only">{condition}</span>}
                <span className="tabular-nums leading-none">
                  <span className="sr-only">Máxima </span>
                  <span className="text-lg font-bold" style={{ color: 'var(--color-foreground)' }}>
                    {day.temp_max !== null ? `${Math.round(day.temp_max)}°` : '—'}
                  </span>
                  <span className="sr-only">, mínima </span>{' '}
                  <span className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                    {day.temp_min !== null ? `${Math.round(day.temp_min)}°` : '—'}
                  </span>
                </span>
                {showRain && (
                  <RainPill
                    kind={precipKind(day.icon) ?? 'Lluvia'}
                    pct={day.precip_prob ?? 0}
                    window={rainWindows[day.date]}
                  />
                )}
                {showConfidence && <ConfidenceChip label={day.confidence_label} />}
              </button>
            </li>
          )
        })}
      </ul>
      {/* Un panel de datos no dice que responde al toque: se dice una vez, debajo. */}
      <p
        className="px-3 py-2 text-center text-xs"
        style={{ color: 'var(--color-muted-foreground)', borderTop: '1px solid var(--color-border)' }}
      >
        Elegí un día para ver sus horas
      </p>
    </section>
  )
}
