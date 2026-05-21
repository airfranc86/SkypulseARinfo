import { Clock } from 'lucide-react'
import { type ReactElement } from 'react'

interface HourlyTimelineProps {
  bestWindow?: string | null
  label?: string
}

export function HourlyTimeline({
  bestWindow,
  label = 'Mejor momento',
}: HourlyTimelineProps): ReactElement | null {
  if (!bestWindow) return null

  return (
    <div
      className="flex items-center gap-3 rounded-xl border border-l-2 p-4"
      style={{
        background: 'var(--color-card)',
        borderColor: 'var(--color-border)',
        borderLeftColor: 'var(--color-primary)',
      }}
    >
      <Clock
        size={18}
        style={{ color: 'var(--color-primary)', flexShrink: 0 }}
        aria-hidden="true"
      />
      <span
        className="text-sm"
        style={{ color: 'var(--color-muted-foreground)' }}
      >
        {label}
      </span>
      <span className="ml-auto text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
        {bestWindow}
      </span>
    </div>
  )
}
