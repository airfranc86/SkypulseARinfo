import { Car } from 'lucide-react'
import { useLavarCoche } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import type { CarWashDay } from '@/lib/api'
import { FadeContent } from '@/components/animated/FadeContent'
import { GlowCard } from '@/components/animated/GlowCard'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorMessage } from '@/components/ui/ErrorMessage'

interface Props { location: LocationState | null }

const COLOR_MAP: Record<CarWashDay['color'], string> = {
  green: '#3ecf7a',
  yellow: '#f0a030',
  red: '#e05545',
}

function DayRow({ day }: { day: CarWashDay }) {
  const barColor = COLOR_MAP[day.color]

  const row = (
    <div
      className="flex items-center gap-4 rounded-xl px-4 py-3"
      style={{ background: 'var(--color-card)' }}
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
              <span className="ml-1 text-[#f0a030]" title="Mejor día">★</span>
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

      {/* Barra de índice + titular + condiciones */}
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
              style={{
                width: `${day.score}%`,
                background: `linear-gradient(90deg, ${barColor}99, ${barColor})`,
              }}
            />
          </div>
          <span
            className="text-xs font-semibold tabular-nums shrink-0"
            style={{ color: barColor, minWidth: '2.5rem', textAlign: 'right' }}
          >
            {day.score}
          </span>
        </div>
        <div className="flex gap-2 mt-1 flex-wrap">
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            🌡 {day.temp_max_c.toFixed(0)}°
          </span>
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            💧 {day.humidity}%
          </span>
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            💨 {day.wind_speed_kmh.toFixed(0)}km/h
          </span>
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

export function LavarCoche({ location }: Props) {
  const { data, isLoading, error } = useLavarCoche(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  return (
    <div>
      <PageHeader
        icon={<Car className="size-8" style={{ color: '#5aaad8' }} />}
        title="¿Cuándo lavar el auto?"
        subtitle={location.label}
        accentColor="#5aaad8"
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}
      {data && (
        <FadeContent>
          <div className="space-y-3">
            {data.days.map((day) => (
              <DayRow key={day.date} day={day} />
            ))}
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

