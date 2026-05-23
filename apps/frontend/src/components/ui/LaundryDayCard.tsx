import type { ReactElement } from 'react'
import type { LaundryDay } from '@/lib/api'
import { IndexGauge } from '@/components/ui/IndexGauge'
import { FadeContent } from '@/components/animated/FadeContent'
import { BorderGlow } from '@/components/animated/BorderGlow'

interface LaundryDayCardProps {
  day: LaundryDay
  index: number
}

function confidenceBadgeColor(pct: number): string {
  if (pct >= 85) return '#3ecf7a'
  if (pct >= 70) return '#f0a030'
  return '#e07b30'
}

export function LaundryDayCard({ day, index }: LaundryDayCardProps): ReactElement {
  const isBest = day.is_best
  const borderColor = 'var(--color-border)'
  const badgeColor = isBest ? '#c8a84b' : confidenceBadgeColor(day.confidence_pct)

  const cardContent = (
    <div
      className="rounded-2xl px-4 py-3 cursor-pointer"
      style={{
        background: 'var(--color-card)',
        border: isBest ? 'none' : `1px solid ${borderColor}`,
        transition: 'transform 0.18s ease',
      }}
      onMouseEnter={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.transform = 'scale(1.01)'
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLDivElement).style.transform = 'scale(1)'
      }}
    >
      <div className="flex items-center gap-4">
        {/* Mini gauge */}
        <div className="shrink-0">
          <IndexGauge value={day.score} label={day.label} size={80} />
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

            {/* Badge: best day OR confidence */}
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
            ) : (
              <div className="shrink-0 flex flex-col items-end gap-0.5">
                <span
                  className="text-xs font-medium px-2 py-0.5 rounded-full"
                  style={{
                    background: `${badgeColor}1a`,
                    color: badgeColor,
                    border: `1px solid ${badgeColor}55`,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {Math.round(day.confidence_pct)}% {day.confidence_label}
                </span>
                <span style={{ fontSize: '9px', color: 'var(--color-muted-foreground)', paddingRight: '2px' }}>
                  Pronóstico
                </span>
              </div>
            )}
          </div>

          {/* Headline */}
          <p
            className="text-xs mb-2 truncate"
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
            <span
              className="text-xs"
              style={{ color: 'var(--color-muted-foreground)' }}
            >
              🌡 {day.temp_max_c.toFixed(0)}°C
            </span>
            <span
              className="text-xs"
              style={{ color: 'var(--color-muted-foreground)' }}
            >
              💧 {day.humidity}%
            </span>
            <span
              className="text-xs"
              style={{ color: 'var(--color-muted-foreground)' }}
            >
              💨 {day.wind_speed_kmh.toFixed(0)} km/h
            </span>
            <span
              className="text-xs"
              style={{ color: 'var(--color-muted-foreground)' }}
            >
              🌧 {day.precip_prob}%
            </span>
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
