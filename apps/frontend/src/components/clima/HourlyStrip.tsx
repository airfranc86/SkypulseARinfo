import { useState, useMemo } from 'react'
import type { ReactNode } from 'react'
import { Wind } from 'lucide-react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { cn } from '@/lib/utils'
import { describeWeatherIcon } from '@/lib/weatherLabels'
import { GUST_KMH, entriesFromNow, formatMm, isRainy, rainWindowLabel } from '@/lib/weatherVerdict'
import type { HourlyConsensus, HourlyEntry } from '@/lib/api'

interface Props {
  hourly: HourlyConsensus
  badge?: ReactNode
  /** Hora de referencia (ms): la tira arranca en la hora en curso, no a medianoche. */
  nowMs: number
}

/** Group entries by date */
function groupByDate(entries: HourlyEntry[]): Record<string, HourlyEntry[]> {
  return entries.reduce<Record<string, HourlyEntry[]>>((acc, e) => {
    if (!acc[e.date]) acc[e.date] = []
    acc[e.date].push(e)
    return acc
  }, {})
}

/** "2026-09-18" + 1 día = "2026-09-19", sin pasar por la zona horaria del navegador. */
function nextDate(date: string): string {
  const d = new Date(`${date}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + 1)
  return d.toISOString().slice(0, 10)
}

/** Short label for a date tab: "Hoy" es la fecha de la primera hora del pronóstico, no la primera pestaña. */
function dateTabLabel(date: string, todayDate: string): string {
  if (date === todayDate) return 'Hoy'
  if (date === nextDate(todayDate)) return 'Mañana'
  const d = new Date(date + 'T12:00:00')
  return d.toLocaleDateString('es-AR', { weekday: 'short' })
}

export function HourlyStrip({ hourly, badge, nowMs }: Props) {
  const visible = useMemo(() => entriesFromNow(hourly.entries, nowMs), [hourly.entries, nowMs])
  const groups = useMemo(() => groupByDate(visible), [visible])
  const dates = Object.keys(groups)
  const todayDate = hourly.entries[0]?.date ?? ''
  const [selectedDate, setSelectedDate] = useState(dates[0] ?? '')
  // Si el día elegido ya no está en los datos (p. ej. pasó la medianoche y el pronóstico se
  // refrescó), se vuelve al primero en vez de mostrar "Sin datos" con las pestañas visibles.
  const activeDate = groups[selectedDate] ? selectedDate : (dates[0] ?? '')
  const activeEntries = groups[activeDate] ?? []

  // El resumen sale de los milímetros previstos, no de `precip_prob`: con Windy el backend
  // la aproxima como 100 (llueve) o 0 (no llueve), y eso no es una probabilidad.
  const rainWindow = rainWindowLabel(activeEntries)

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* Resumen de lluvia del día elegido */}
      <div
        className="px-5 py-3 flex items-center justify-between gap-3"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <h2 className="text-sm font-medium shrink-0" style={{ color: 'var(--color-foreground)' }}>
            Pronóstico por hora
          </h2>
          {badge}
        </div>
        <span
          className="text-xs px-2.5 py-1 rounded-full font-medium shrink-0"
          style={
            rainWindow
              ? {
                  background: 'rgba(90,170,216,0.12)',
                  border: '1px solid rgba(90,170,216,0.3)',
                  color: 'var(--color-info)',
                }
              : {
                  background: 'var(--color-secondary)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-muted-foreground)',
                }
          }
        >
          {rainWindow ? `Lluvia prevista: ${rainWindow}` : 'Sin lluvia prevista'}
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
        {dates.map((date) => (
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
            {dateTabLabel(date, todayDate)}
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
          <HourCard key={entry.timestamp} entry={entry} isNow={entry.timestamp * 1000 <= nowMs} />
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

function HourCard({ entry, isNow }: { entry: HourlyEntry; isNow: boolean }) {
  const rainy = isRainy(entry)
  const mm = entry.precip_mm ?? 0
  const gust = entry.wind_gusts_kmh
  const strongGust = gust !== null && gust !== undefined && gust > GUST_KMH

  return (
    <div
      // relative: el .sr-only de adentro es absoluto; sin un ancestro posicionado dentro del
      // scroller, su posición estática (hasta 2000 px a la derecha) ensancha toda la página.
      className="relative shrink-0 flex flex-col items-center gap-1.5 px-3 py-3 rounded-xl"
      style={{
        background: rainy ? 'rgba(90,170,216,0.1)' : 'var(--color-secondary)',
        border: isNow
          ? '1.5px solid rgba(200,168,75,0.55)'
          : rainy ? '1px solid rgba(90,170,216,0.25)' : '1px solid var(--color-border)',
        minWidth: '68px',
        scrollSnapAlign: 'start',
      }}
    >
      <span
        className={cn('text-xs', isNow ? 'font-semibold' : 'font-medium')}
        style={{ color: isNow ? 'var(--color-primary)' : 'var(--color-muted-foreground)' }}
      >
        {isNow ? 'Ahora' : entry.hour_label}
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
      {rainy && (
        <span className="text-xs whitespace-nowrap" style={{ color: 'var(--color-info)' }}>
          <span aria-hidden="true">{formatMm(mm)}</span>
          <span className="sr-only">Lluvia prevista, {formatMm(mm)}</span>
        </span>
      )}
      {strongGust && (
        <span className="text-xs inline-flex items-center gap-1 whitespace-nowrap" style={{ color: 'var(--color-muted-foreground)' }}>
          <Wind size={12} strokeWidth={2} aria-hidden="true" />
          <span aria-hidden="true">{Math.round(gust)}</span>
          <span className="sr-only">Ráfagas de {Math.round(gust)} kilómetros por hora</span>
        </span>
      )}
    </div>
  )
}
