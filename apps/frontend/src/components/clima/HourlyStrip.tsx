import { useState, useMemo } from 'react'
import type { ReactNode } from 'react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { cn } from '@/lib/utils'
import { describeWeatherIcon } from '@/lib/weatherLabels'
import type { HourlyConsensus, HourlyEntry } from '@/lib/api'

interface Props {
  hourly: HourlyConsensus
  badge?: ReactNode
}

/** Group entries by date */
function groupByDate(entries: HourlyEntry[]): Record<string, HourlyEntry[]> {
  return entries.reduce<Record<string, HourlyEntry[]>>((acc, e) => {
    if (!acc[e.date]) acc[e.date] = []
    acc[e.date].push(e)
    return acc
  }, {})
}

/** Short label for a date tab */
function dateTabLabel(date: string, index: number): string {
  if (index === 0) return 'Hoy'
  if (index === 1) return 'Mañana'
  const d = new Date(date + 'T12:00:00')
  return d.toLocaleDateString('es-AR', { weekday: 'short' })
}

export function HourlyStrip({ hourly, badge }: Props) {
  const groups = useMemo(() => groupByDate(hourly.entries), [hourly.entries])
  const dates = Object.keys(groups)
  const [selectedDate, setSelectedDate] = useState(dates[0] ?? '')
  // Si el día elegido ya no está en los datos (p. ej. pasó la medianoche y el pronóstico se
  // refrescó), se vuelve al primero en vez de mostrar "Sin datos" con las pestañas visibles.
  const activeDate = groups[selectedDate] ? selectedDate : (dates[0] ?? '')
  const activeEntries = groups[activeDate] ?? []

  const rainPct = Math.round(hourly.rain_probability_pct)

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* Rain consensus banner */}
      <div
        className="px-5 py-3 flex items-center justify-between gap-3"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <p className="text-sm font-medium shrink-0" style={{ color: 'var(--color-foreground)' }}>
            Pronóstico por hora
          </p>
          {badge}
        </div>
        <span
          className="text-xs px-2.5 py-1 rounded-full font-medium shrink-0"
          style={{
            background: rainPct < 20
              ? 'rgba(62,207,122,0.12)'
              : rainPct < 60
                ? 'rgba(240,160,48,0.12)'
                : 'rgba(224,85,69,0.12)',
            border: `1px solid ${rainPct < 20 ? 'rgba(62,207,122,0.3)' : rainPct < 60 ? 'rgba(240,160,48,0.3)' : 'rgba(224,85,69,0.3)'}`,
            color: rainPct < 20 ? 'var(--color-safe)' : rainPct < 60 ? 'var(--color-watch)' : 'var(--color-warn)',
          }}
        >
          {hourly.rain_consensus_label}
        </span>
      </div>

      {/* Day tabs — segmented control con fondo sólido y estado activo de alto contraste */}
      <div
        className="flex gap-0.5 mx-4 mt-3 p-0.5 rounded-xl overflow-x-auto"
        style={{
          scrollbarWidth: 'none',
          background: 'var(--color-secondary)',
          border: '1px solid var(--color-border)',
        }}
      >
        {dates.map((date, i) => (
          <button
            key={date}
            type="button"
            onClick={() => setSelectedDate(date)}
            aria-pressed={date === activeDate}
            className={cn(
              'shrink-0 px-3.5 py-2 min-h-[44px] rounded-lg text-sm font-medium transition-colors',
              date === activeDate
                ? 'text-[var(--color-primary-foreground)] font-semibold'
                : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
            )}
            style={date === activeDate
              ? { background: 'var(--color-primary)', boxShadow: '0 1px 4px rgba(0,0,0,0.35)' }
              : { background: 'transparent' }
            }
          >
            {dateTabLabel(date, i)}
          </button>
        ))}
      </div>

      {/* Hourly cards — scroll-snap + right fade hint */}
      <div
        className="flex gap-3 px-4 py-4 overflow-x-auto"
        style={{
          scrollbarWidth: 'thin',
          scrollSnapType: 'x mandatory',
          WebkitOverflowScrolling: 'touch',
          maskImage: 'linear-gradient(to right, black calc(100% - 40px), transparent 100%)',
          WebkitMaskImage: 'linear-gradient(to right, black calc(100% - 40px), transparent 100%)',
        }}
      >
        {activeEntries.map((entry) => (
          <HourCard key={entry.timestamp} entry={entry} />
        ))}
        {activeEntries.length === 0 && (
          <p className="text-sm py-4 px-2" style={{ color: 'var(--color-muted-foreground)' }}>
            Sin datos para este día.
          </p>
        )}
      </div>
    </div>
  )
}

function HourCard({ entry }: { entry: HourlyEntry }) {
  const hasPrecip = (entry.precip_prob ?? 0) > 20

  return (
    <div
      // relative: el .sr-only de adentro es absoluto; sin un ancestro posicionado dentro del
      // scroller, su posición estática (hasta 2000 px a la derecha) ensancha toda la página.
      className="relative shrink-0 flex flex-col items-center gap-1.5 px-3 py-3 rounded-xl"
      style={{
        background: hasPrecip ? 'rgba(90,170,216,0.1)' : 'var(--color-secondary)',
        border: hasPrecip ? '1px solid rgba(90,170,216,0.25)' : '1px solid var(--color-border)',
        minWidth: '68px',
        scrollSnapAlign: 'start',
      }}
    >
      <span className="text-xs font-medium" style={{ color: 'var(--color-muted-foreground)' }}>
        {entry.hour_label}
      </span>
      <WeatherIcon
        code={entry.icon}
        size={44}
        isDay={entry.is_day}
        glow
        label={describeWeatherIcon(entry.icon) ?? undefined}
      />
      <span className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
        {entry.temp_c !== null ? `${Math.round(entry.temp_c)}°` : '—'}
      </span>
      {hasPrecip && (
        <span className="text-xs" style={{ color: 'var(--color-info)' }}>
          <span aria-hidden="true">{Math.round(entry.precip_prob ?? 0)}%</span>
          <span className="sr-only">
            Probabilidad de precipitación {Math.round(entry.precip_prob ?? 0)} por ciento
          </span>
        </span>
      )}
      {entry.wind_gusts_kmh !== null && entry.wind_gusts_kmh !== undefined && entry.wind_gusts_kmh > 40 && (
        <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
          <span aria-hidden="true">💨 {Math.round(entry.wind_gusts_kmh)}</span>
          <span className="sr-only">Ráfagas de {Math.round(entry.wind_gusts_kmh)} kilómetros por hora</span>
        </span>
      )}
    </div>
  )
}
