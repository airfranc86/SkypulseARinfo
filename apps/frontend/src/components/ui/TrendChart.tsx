import { type ReactElement } from 'react'

interface TrendChartItem {
  label: string
  value: number | null
  color?: string
}

interface TrendChartProps {
  data: TrendChartItem[]
  unit?: string
  title?: string
}

export function TrendChart({ data, unit = 'm', title }: TrendChartProps): ReactElement {
  const validItems = data.filter((item) => item.value !== null)
  const maxValue = validItems.length > 0
    ? Math.max(...validItems.map((item) => item.value as number))
    : 0

  if (validItems.length === 0) {
    return (
      <div
        className="rounded-xl border p-4"
        style={{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }}
      >
        {title && (
          <p className="mb-3 text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
            {title}
          </p>
        )}
        <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
          Sin datos para la zona seleccionada.
        </p>
      </div>
    )
  }

  return (
    <div
      className="rounded-xl border p-4"
      style={{ background: 'var(--color-card)', borderColor: 'var(--color-border)' }}
    >
      {title && (
        <p className="mb-3 text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
          {title}
        </p>
      )}
      <div className="space-y-3">
        {data.map((item, index) => {
          if (item.value === null) return null
          const pct = maxValue > 0 ? (item.value / maxValue) * 100 : 0
          const barColor = item.color ?? 'var(--color-primary)'

          return (
            <div key={index} className="flex items-center gap-3">
              <span
                className="w-32 min-w-[8rem] truncate text-xs"
                style={{ color: 'var(--color-muted-foreground)' }}
                title={item.label}
              >
                {item.label}
              </span>
              <div className="flex-1">
                <div
                  style={{
                    height: '8px',
                    borderRadius: '9999px',
                    background: 'var(--color-muted)',
                  }}
                >
                  <div
                    style={{
                      height: '8px',
                      borderRadius: '9999px',
                      background: barColor,
                      width: `${pct}%`,
                      transition: 'all 0.5s ease',
                    }}
                  />
                </div>
              </div>
              <span
                className="w-12 text-right text-xs"
                style={{ color: 'var(--color-foreground)' }}
              >
                {item.value}
                <span style={{ color: 'var(--color-muted-foreground)' }}>{unit}</span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
