import { type ReactElement } from 'react'
import type { LaundryDay } from '@/lib/api'
import { laundryDayView } from '@/lib/laundryDay'
import { FadeContent } from '@/components/animated/FadeContent'
import { BorderGlow } from '@/components/animated/BorderGlow'

interface LaundryDayCardProps {
  day: LaundryDay
  index: number
}

export function LaundryDayCard({
  day,
  index,
}: LaundryDayCardProps): ReactElement {
  const view = laundryDayView(day)
  const isBest = view.showBestBadge
  const labelColor = view.labelColor
  const showPrecipChip = day.precip_prob > 0

  const cardContent = (
    <div
      className="rounded-2xl px-4 py-3"
      style={{
        background: 'var(--color-card)',
        border: isBest ? 'none' : `1px solid var(--color-border)`,
      }}
    >
      <div className="flex items-center gap-3">
        {/* Score label pill */}
        <div
          className="shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-full"
          style={{
            background: `${labelColor}1a`,
            border: `1px solid ${labelColor}55`,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              color: labelColor,
              textShadow: `0 0 6px ${labelColor}55`,
              fontSize: '0.55rem',
              lineHeight: 1,
            }}
          >
            ●
          </span>
          <span
            className="text-xs font-semibold whitespace-nowrap"
            style={{ color: labelColor }}
          >
            {day.label ?? ''}
          </span>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Row: day label + badge */}
          <div className="flex items-start justify-between gap-2 mb-1">
            <span
              className="text-sm font-semibold capitalize"
              style={{ color: 'var(--color-foreground)' }}
            >
              {view.dayText}
            </span>

            <div className="shrink-0 flex flex-col items-end gap-1">
              {isBest && (
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded-full"
                  style={{
                    background: 'rgba(200,168,75,0.15)',
                    color: '#c8a84b',
                    border: '1px solid rgba(200,168,75,0.35)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <span aria-hidden="true">✦</span> Mejor día
                </span>
              )}
              {view.confidenceText && (
                <span
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{
                    background: 'var(--color-muted)',
                    color: 'var(--color-muted-foreground)',
                    border: '1px solid var(--color-border)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {view.confidenceText}
                </span>
              )}
            </div>
          </div>

          {/* Headline */}
          <p
            className="text-xs mb-2"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            {day.headline}
          </p>

          {/* Divider */}
          <div
            className="mb-2"
            style={{ height: '1px', background: 'var(--color-border)' }}
          />

          {/* Condition chips */}
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
              🌡 {day.temp_max_c.toFixed(0)}°C
            </span>
            <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
              💧 {Math.round(day.humidity)}%
            </span>
            <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
              💨 {day.wind_speed_kmh.toFixed(0)} km/h
            </span>
            {showPrecipChip && (
              <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                🌧 {day.precip_prob}%
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )

  if (isBest) {
    return (
      <FadeContent delay={index * 60}>
        <BorderGlow
          animated
          glowColor="40 65 54"
          backgroundColor="#0d1625"
          borderRadius={16}
          glowRadius={32}
          glowIntensity={1.0}
          colors={['#c8a84b', '#f0d060', '#3ecf7a']}
          fillOpacity={0.3}
        >
          {cardContent}
        </BorderGlow>
      </FadeContent>
    )
  }

  return (
    <FadeContent delay={index * 60}>
      {cardContent}
    </FadeContent>
  )
}
