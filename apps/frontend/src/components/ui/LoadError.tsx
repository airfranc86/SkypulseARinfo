import { Hourglass } from 'lucide-react'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { COLD_START_NOTICE, classifyLoadError, type LoadErrorCategory } from '@/lib/loadError'

interface LoadErrorProps {
  /** Whatever the query or fetch threw: it is classified, never shown raw. */
  error: unknown
  /** Shown as "Reintentar" only when retrying can change the outcome. */
  onRetry?: () => void
  /** Page-specific wording for a category (e.g. METAR names the ICAO code on "invalid"). */
  messages?: Partial<Record<LoadErrorCategory, string>>
}

/**
 * Final load failure in plain Spanish (FRA-340): the cause decides the text and whether the
 * retry button makes sense. Built on ErrorMessage, so it keeps the amber look and role="alert".
 */
export function LoadError({ error, onRetry, messages }: LoadErrorProps) {
  const online = typeof navigator === 'undefined' ? undefined : navigator.onLine
  const info = classifyLoadError(error, { online })
  return (
    <ErrorMessage
      message={messages?.[info.category] ?? info.message}
      onRetry={info.retryable ? onRetry : undefined}
    />
  )
}

/**
 * Waiting notice while the bounded cold-start retries run: a status, not an error. Static icon
 * on purpose (no new animation, so nothing to opt out of with prefers-reduced-motion).
 */
export function ColdStartNotice() {
  return (
    <div
      className="rounded-xl px-4 py-3 flex items-center gap-3 text-sm"
      role="status"
      style={{ border: '1px solid rgba(240,160,48,0.3)', background: 'rgba(240,160,48,0.06)', color: 'var(--color-foreground)' }}
    >
      <Hourglass size={18} strokeWidth={2} className="shrink-0" style={{ color: 'var(--color-watch)' }} aria-hidden="true" />
      <span>{COLD_START_NOTICE}</span>
    </div>
  )
}
