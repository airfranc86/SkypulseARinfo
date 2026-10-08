import { Car } from 'lucide-react'
import { useLavarCoche } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import type { CarWashDay } from '@/lib/api'
import { LABEL_COLOR, resolveLabel, type QualityLabel } from '@/lib/qualityScale'
import { isQualifiedBest, qualifiedBestDay } from '@/lib/laundryDay'
import { FadeContent } from '@/components/animated/FadeContent'
import { GlowCard } from '@/components/animated/GlowCard'
import { QualityScaleBar } from '@/components/ui/QualityScaleBar'
import { PageHeader } from '@/components/ui/PageHeader'
import { ColdStartNotice, LoadError } from '@/components/ui/LoadError'
import { isWaitingForColdStart } from '@/lib/loadError'

interface Props { location: LocationState | null }

interface ScoreInfo {
  rowBg: string
  fontSize: string
  fontWeight: number
}

// Row tints are the scale colors with an alpha (hex 14 = 8 %, 0a = 4 %, 1a = 10 %, 12 = 7 %).
function scoreInfo(label: QualityLabel, score: number): ScoreInfo {
  if (label === 'Excelente' && score >= 80) return { rowBg: `${LABEL_COLOR['Excelente']}14`, fontSize: '1.15rem', fontWeight: 700 }
  if (label === 'Excelente')               return { rowBg: `${LABEL_COLOR['Excelente']}0a`, fontSize: '1.0rem',  fontWeight: 600 }
  if (label === 'Bueno')                   return { rowBg: 'transparent',                    fontSize: '0.9rem',  fontWeight: 500 }
  if (label === 'No apto')                 return { rowBg: `${LABEL_COLOR['No apto']}1a`,   fontSize: '0.75rem', fontWeight: 400 }
  return                                          { rowBg: `${LABEL_COLOR['Regular']}12`,   fontSize: '0.8rem',  fontWeight: 400 }
}

// ---------------------------------------------------------------------------
// DayRow
// ---------------------------------------------------------------------------

function DayRow({ day }: { day: CarWashDay }) {
  const label = resolveLabel(day)
  const barColor = LABEL_COLOR[label]
  const info = scoreInfo(label, day.score)
  const isBest = isQualifiedBest(day)

  const row = (
    <div
      className="flex items-center gap-4 rounded-xl px-4 py-3"
      style={{
        background: info.rowBg !== 'transparent' ? info.rowBg : 'var(--color-card)',
      }}
    >
      {/* Day label + quality badge */}
      <div className="w-24 shrink-0">
        <div className="flex items-center flex-wrap gap-x-1">
          <span
            className="text-sm font-medium capitalize"
            style={{ color: 'var(--color-foreground)' }}
          >
            {day.day_label}
            {isBest && (
              <span className="ml-1" style={{ color: 'var(--color-watch)' }} title="Mejor día">★</span>
            )}
          </span>
          <span
            className="text-xs px-1.5 py-0.5 rounded-full font-medium"
            style={{
              background: 'var(--color-card)',
              color: barColor,
              border: `1px solid ${barColor}66`,
            }}
          >
            {label}
          </span>
        </div>
        <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
          {day.date}
        </p>
      </div>

      {/* Score bar + headline + condiciones */}
      <div className="flex-1 min-w-0">
        <p
          className="text-xs line-clamp-2 mb-1"
          style={{ color: 'var(--color-muted-foreground)' }}
        >
          {day.headline}
        </p>
        <div className="flex items-center gap-2">
          <div
            className="flex-1 h-1.5 rounded-full overflow-hidden"
            style={{ background: 'var(--color-muted)' }}
          >
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${day.score}%`, background: barColor }}
            />
          </div>
          <span
            className="tabular-nums shrink-0"
            style={{
              color: barColor,
              minWidth: '2.5rem',
              textAlign: 'right',
              fontSize: info.fontSize,
              fontWeight: info.fontWeight,
            }}
          >
            {day.score}
          </span>
        </div>
        <div className="flex gap-2 mt-1 flex-wrap">
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            🌡 {day.temp_max_c.toFixed(0)}°
          </span>
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            💧 {Math.round(day.humidity)}%
          </span>
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            💨 {day.wind_speed_kmh.toFixed(0)}km/h
          </span>
          {day.precip_mm > 0 && (
            <span className="text-xs" style={{ color: 'var(--color-info)' }}>
              🌧 {day.precip_mm.toFixed(1)}mm
            </span>
          )}
        </div>
      </div>
    </div>
  )

  if (isBest) {
    return (
      <GlowCard glowColor={barColor} borderRadius={12} glowSize={280}>
        {row}
      </GlowCard>
    )
  }

  return row
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function LavarCoche({ location }: Props) {
  const { data, isFetching, error, refetch, failureCount, failureReason } = useLavarCoche(location?.lat ?? null, location?.lon ?? null)

  // While the cold-start retries run there is a waiting notice instead of an error; during
  // any other load (first one or a manual "Reintentar") the skeleton, and the error only
  // once the query stopped fetching (FRA-340).
  const waitingColdStart = isWaitingForColdStart({ hasData: Boolean(data), isFetching, failureCount, failureReason })
  const showSkeleton = !data && isFetching && !waitingColdStart
  const showError = Boolean(error) && !isFetching

  if (location === null) return <PageSkeleton />

  const bestDay = data ? qualifiedBestDay(data.days) : null
  const bestColor = LABEL_COLOR[bestDay ? resolveLabel(bestDay) : 'Excelente']

  return (
    <div>
      <PageHeader
        icon={<Car size={32} style={{ color: '#5aaad8' }} />}
        title="Lavar el auto"
        subtitle={location.label}
        accentColor="#5aaad8"
      />

      {showSkeleton && <PageSkeleton />}
      {waitingColdStart && <ColdStartNotice />}
      {showError && <LoadError error={error} onRetry={() => { void refetch() }} />}

      {data && (
        <FadeContent>
          <div className="space-y-4">
            {/* Hero callout — mejor día */}
            {bestDay && (
              <div
                className="rounded-xl px-5 py-4 flex items-start gap-4"
                style={{
                  background: `${bestColor}0f`,
                  border: `1.5px solid ${bestColor}45`,
                }}
              >
                <div className="relative flex-shrink-0 mt-1">
                  <span
                    className="absolute inset-0 rounded-full motion-safe:animate-ping opacity-50"
                    style={{ background: bestColor }}
                  />
                  <span
                    className="relative block w-3 h-3 rounded-full"
                    style={{ background: bestColor }}
                  />
                </div>
                <div>
                  <p className="text-sm font-bold leading-tight" style={{ color: bestColor }}>
                    {bestDay.day_label} — mejor oportunidad
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-muted-foreground)' }}>
                    {bestDay.headline}
                  </p>
                </div>
              </div>
            )}

            {/* Escala de referencia */}
            <QualityScaleBar bestLabel={bestDay ? resolveLabel(bestDay) : ''} />

            {/* Lista de días */}
            <div className="space-y-3">
              {data.days.map((day) => (
                <DayRow key={day.date} day={day} />
              ))}
            </div>
          </div>
        </FadeContent>
      )}
    </div>
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-16 rounded-xl" style={{ background: 'var(--color-muted)' }} />
      ))}
    </div>
  )
}
