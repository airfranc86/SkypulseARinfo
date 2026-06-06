import { Car } from '@phosphor-icons/react'
import { useLavarCoche } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import type { CarWashDay } from '@/lib/api'
import { FadeContent } from '@/components/animated/FadeContent'
import { GlowCard } from '@/components/animated/GlowCard'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { ModelBadge } from '@/components/ui/ModelBadge'

interface Props { location: LocationState | null }

const COLOR_MAP: Record<CarWashDay['color'], string> = {
  green: '#3ecf7a',
  yellow: '#f0a030',
  red:    '#e05545',
}

// 4 colores distintos — uno por label, incluido "No apto" ≠ "Regular"
const LABEL_COLOR: Record<string, string> = {
  Excelente: '#3ecf7a',
  Bueno:     '#f0a030',
  Regular:   '#e05545',
  'No apto': '#b91c1c',  // rojo sangre — visible a 25% opacidad, claramente distinto de Regular
}

const QUALITY_SCALE = [
  { label: 'Excelente', color: LABEL_COLOR['Excelente'] },
  { label: 'Bueno',     color: LABEL_COLOR['Bueno'] },
  { label: 'Regular',   color: LABEL_COLOR['Regular'] },
  { label: 'No apto',   color: LABEL_COLOR['No apto'] },
] as const

interface ScoreInfo {
  rowBg: string
  fontSize: string
  fontWeight: number
}

function scoreInfo(color: CarWashDay['color'], score: number): ScoreInfo {
  if (color === 'green' && score >= 80) return { rowBg: 'rgba(62,207,122,0.08)', fontSize: '1.15rem', fontWeight: 700 }
  if (color === 'green')               return { rowBg: 'rgba(62,207,122,0.04)', fontSize: '1.0rem',  fontWeight: 600 }
  if (color === 'yellow')              return { rowBg: 'transparent',            fontSize: '0.9rem',  fontWeight: 500 }
  if (score < 30)                      return { rowBg: 'rgba(155,32,32,0.10)',   fontSize: '0.75rem', fontWeight: 400 }
  return                                      { rowBg: 'rgba(224,85,69,0.07)',   fontSize: '0.8rem',  fontWeight: 400 }
}

// ---------------------------------------------------------------------------
// QualityScaleBar
// ---------------------------------------------------------------------------

function QualityScaleBar({ bestLabel }: { bestLabel: string }) {
  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-[.55rem] uppercase tracking-widest mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Escala de aptitud
      </p>
      <div className="flex gap-[3px] h-[10px]">
        {QUALITY_SCALE.map((q) => (
          <div
            key={q.label}
            className="flex-1 rounded-full"
            style={{ background: q.color, opacity: 0.55 }}
          />
        ))}
      </div>
      <div className="flex mt-2.5">
        {QUALITY_SCALE.map((q) => (
          <div key={q.label} className="flex-1 text-center">
            <span
              className="text-[.48rem] leading-tight block"
              style={{
                color: q.color,
                fontWeight: q.label === bestLabel ? 700 : undefined,
              }}
            >
              {q.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DayRow
// ---------------------------------------------------------------------------

function DayRow({ day }: { day: CarWashDay }) {
  const barColor = LABEL_COLOR[day.label] ?? COLOR_MAP[day.color]
  const info = scoreInfo(day.color, day.score)

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
            {day.is_best && (
              <span className="ml-1" style={{ color: 'var(--color-watch)' }} title="Mejor día">★</span>
            )}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
            style={{
              background: `${barColor}20`,
              color: barColor,
              border: `1px solid ${barColor}40`,
            }}
          >
            {day.label}
          </span>
        </div>
        <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
          {day.date}
        </p>
      </div>

      {/* Score bar + headline + condiciones */}
      <div className="flex-1 min-w-0">
        <p
          className="text-xs truncate mb-1"
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

  if (day.is_best) {
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
  const { data, isLoading, error } = useLavarCoche(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  const bestDay = data?.days.find(d => d.is_best) ?? null
  const bestColor = bestDay ? COLOR_MAP[bestDay.color] : '#3ecf7a'

  return (
    <div>
      <PageHeader
        icon={<Car size={32} weight="duotone" style={{ color: '#5aaad8' }} />}
        title="¿Cuándo lavar el auto?"
        subtitle={location.label}
        accentColor="#5aaad8"
        modelBadge={<ModelBadge model="gfs" variant="header" />}
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}

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
                    className="absolute inset-0 rounded-full animate-ping opacity-50"
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
            <QualityScaleBar bestLabel={bestDay?.label ?? ''} />

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
