import { type ReactElement, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface StatCardProps {
  label: string
  value: string | number
  unit?: string
  icon?: ReactNode
  variant?: 'default' | 'highlight'
}

export function StatCard({
  label,
  value,
  unit,
  icon,
  variant = 'default',
}: StatCardProps): ReactElement {
  return (
    <div
      className={cn(
        'relative rounded-xl border p-4',
        variant === 'highlight' && 'border-l-4'
      )}
      style={{
        background: variant === 'highlight'
          ? 'color-mix(in oklch, var(--color-primary) 5%, var(--color-card))'
          : 'var(--color-card)',
        borderColor: 'var(--color-border)',
        ...(variant === 'highlight' && {
          borderLeftColor: 'var(--color-primary)',
        }),
      }}
    >
      <div className="flex items-start justify-between">
        <p
          className="text-xs font-medium uppercase tracking-wide"
          style={{ color: 'var(--color-muted-foreground)' }}
        >
          {label}
        </p>
        {icon && (
          <span style={{ color: 'var(--color-muted-foreground)' }}>
            {icon}
          </span>
        )}
      </div>
      <p className="mt-2 text-2xl font-bold" style={{ color: 'var(--color-foreground)' }}>
        {value}
        {unit && (
          <span
            className="ml-1 text-sm font-normal"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            {unit}
          </span>
        )}
      </p>
    </div>
  )
}
