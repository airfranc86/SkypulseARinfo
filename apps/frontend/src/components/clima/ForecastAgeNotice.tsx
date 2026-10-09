import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'
import { staleForecastNotice } from '@/lib/forecastAge'

const CLOCK_TICK_MS = 60_000

/** Current time, refreshed every minute so the notice appears and its age keeps counting while the page stays open. */
function useMinuteClock(): number {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), CLOCK_TICK_MS)
    return () => window.clearInterval(id)
  }, [])
  return nowMs
}

interface Props {
  /** `forecast_fetched_at` of the dashboard response (ISO); null or absent = unknown age, no notice. */
  forecastFetchedAt: string | null | undefined
  className?: string
}

/**
 * "Mostrando el último pronóstico disponible, de hace 3 h: ...". Renders only while the forecast is older
 * than 2 hours, i.e. while the backend serves a stored copy during an outage (see `staleForecastNotice`).
 * Same amber box as the other notices of the site (RetryNotice, SourceNotes); the text wraps, so it never
 * overflows a 390 px screen.
 */
export function ForecastAgeNotice({ forecastFetchedAt, className = '' }: Props) {
  const nowMs = useMinuteClock()
  const text = staleForecastNotice(forecastFetchedAt, nowMs)
  if (!text) return null
  return (
    <div
      role="status"
      className={`flex items-start gap-2.5 rounded-xl px-4 py-3 text-sm leading-snug ${className}`}
      style={{ border: '1px solid rgba(240,160,48,0.3)', background: 'rgba(240,160,48,0.06)', color: 'var(--color-foreground)' }}
    >
      <Clock size={18} strokeWidth={1.75} className="mt-0.5 shrink-0" style={{ color: 'var(--color-watch)' }} aria-hidden="true" />
      <p className="min-w-0">{text}</p>
    </div>
  )
}
