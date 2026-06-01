import { type ReactElement } from 'react'
import type { LaundryDay } from '@/lib/api'
import { FadeContent } from '@/components/animated/FadeContent'
import { BorderGlow } from '@/components/animated/BorderGlow'

interface LaundryDayCardProps {
  day: LaundryDay
  index: number
  isOpenMeteoFallback?: boolean
}

function scoreLabelColor(score: number): string {
  if (score >= 70) return '#3ecf7a'
  if (score >= 45) return '#f0a030'
  return '#e05545'
}

export function LaundryDayCard({
  day,
  index,
  isOpenMeteoFallback = false,
}: LaundryDayCardProps): ReactElement {
  const isBest = day.is_best
  const labelColor = isBest ? '#c8a84b' : scoreLabelColor(day.score)
  const showPrecipChip = !isOpenMeteoFallback || day.precip_prob > 0
  const showLowConfidence = !isBest && day.confidence_pct < 70

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
              {day.day_label}{' '}
              <span
                className="text-xs font-normal"
                style={{ color: 'var(--color-muted-foreground)' }}
              >
                {day.date}
              </span>
            </span>

            {isBest ? (
              <span
                className="shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full"
                style={{
                  background: 'rgba(200,168,75,0.15)',
                  color: '#c8a84b',
                  border: '1px solid rgba(200,168,75,0.35)',
                  whiteSpace: 'nowrap',
                }}
              >
                ✦ Mejor día
              </span>
            ) : showLowConfidence ? (
              <span
                className="shrink-0 text-xs px-2 py-0.5 rounded-full"
                style={{
                  background: 'rgba(240,160,48,0.12)',
                  color: '#f0a030',
                  border: '1px solid rgba(240,160,48,0.3)',
                  whiteSpace: 'nowrap',
                }}
              >
                ⚠ Baja confianza
              </span>
            ) : null}
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
