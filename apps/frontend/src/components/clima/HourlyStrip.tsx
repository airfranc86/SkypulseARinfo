import { useState, useMemo } from 'react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { cn } from '@/lib/utils'
import type { HourlyConsensus, HourlyEntry } from '@/lib/api'

interface Props {
  hourly: HourlyConsensus
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

export function HourlyStrip({ hourly }: Props) {
  const groups = useMemo(() => groupByDate(hourly.entries), [hourly.entries])
  const dates = Object.keys(groups)
  const [activeDate, setActiveDate] = useState(dates[0] ?? '')
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
        <p className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
          Pronóstico por hora
        </p>
        <span
          className="text-xs px-2.5 py-1 rounded-full font-medium"
          style={{
            background: rainPct < 20
              ? 'rgba(62,207,122,0.12)'
              : rainPct < 60
                ? 'rgba(240,160,48,0.12)'
                : 'rgba(224,85,69,0.12)',
            color: rainPct < 20 ? '#3ecf7a' : rainPct < 60 ? '#f0a030' : '#e05545',
          }}
        >
          {hourly.rain_consensus_label}
        </span>
      </div>

      {/* Day tabs */}
      <div
        className="flex gap-1 px-4 pt-3 overflow-x-auto"
        style={{ scrollbarWidth: 'none' }}
      >
        {dates.map((date, i) => (
          <button
            key={date}
            onClick={() => setActiveDate(date)}
            className={cn(
              'shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
              date === activeDate
                ? 'text-[var(--color-primary)]'
                : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]'
            )}
            style={date === activeDate
              ? { background: 'rgba(200,168,75,0.12)' }
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
      className="shrink-0 flex flex-col items-center gap-1.5 px-3 py-3 rounded-xl"
      style={{
        background: hasPrecip ? 'rgba(90,170,216,0.08)' : 'rgba(200,168,75,0.04)',
        border: hasPrecip ? '1px solid rgba(90,170,216,0.15)' : '1px solid rgba(200,168,75,0.1)',
        minWidth: '60px',
        scrollSnapAlign: 'start',
      }}
    >
      <span className="text-xs font-medium" style={{ color: 'var(--color-muted-foreground)' }}>
        {entry.hour_label}
      </span>
      <WeatherIcon code={entry.icon} size={28} />
      <span className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
        {entry.temp_c !== null ? `${Math.round(entry.temp_c)}°` : '—'}
      </span>
      {hasPrecip && (
        <span className="text-xs" style={{ color: '#5aaad8' }}>
          {Math.round(entry.precip_prob ?? 0)}%
        </span>
      )}
    </div>
  )
}
