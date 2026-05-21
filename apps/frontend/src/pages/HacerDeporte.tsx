import { Dumbbell, Thermometer, Droplets, Wind, CloudRain } from 'lucide-react'
import { useHacerDeporte } from '@/hooks/useWeather'
import type { LocationState } from '@/hooks/useLocation'
import { IndexGauge } from '@/components/ui/IndexGauge'
import { HourlyTimeline } from '@/components/ui/HourlyTimeline'
import { StatCard } from '@/components/ui/StatCard'
import { FadeContent } from '@/components/animated/FadeContent'
import type { ReactElement } from 'react'

interface Props { location: LocationState | null }

// ─── Condition chip helpers ─────────────────────────────────────────────────

type ChipStatus = 'green' | 'yellow' | 'red'

interface ConditionChip {
  icon: ReactElement
  label: string
  value: string
  status: ChipStatus
}

const STATUS_COLORS: Record<ChipStatus, { bg: string; border: string; text: string; dot: string }> = {
  green: {
    bg: 'rgba(34,197,94,0.08)',
    border: 'rgba(34,197,94,0.25)',
    text: 'oklch(0.723 0.219 142.50)',
    dot: 'rgb(34,197,94)',
  },
  yellow: {
    bg: 'rgba(234,179,8,0.08)',
    border: 'rgba(234,179,8,0.25)',
    text: 'oklch(0.795 0.184 86.05)',
    dot: 'rgb(234,179,8)',
  },
  red: {
    bg: 'rgba(239,68,68,0.08)',
    border: 'rgba(239,68,68,0.25)',
    text: 'oklch(0.627 0.258 29.23)',
    dot: 'rgb(239,68,68)',
  },
}

function getTempStatus(temp: number): ChipStatus {
  if (temp < 5 || temp > 35) return 'red'
  if (temp >= 28) return 'yellow'
  return 'green'
}

function getHumidityStatus(humidity: number): ChipStatus {
  if (humidity > 80) return 'red'
  if (humidity > 60) return 'yellow'
  return 'green'
}

function getWindStatus(wind: number): ChipStatus {
  if (wind > 35) return 'red'
  if (wind >= 20) return 'yellow'
  return 'green'
}

function getPrecipStatus(precip: number): ChipStatus {
  if (precip > 2) return 'red'
  if (precip > 0) return 'yellow'
  return 'green'
}

// ─── Condition Chips Strip ──────────────────────────────────────────────────

function ConditionChip({ chip }: { chip: ConditionChip }): ReactElement {
  const colors = STATUS_COLORS[chip.status]
  return (
    <div
      className="flex flex-col items-center gap-1.5 rounded-xl p-3 flex-1 min-w-0"
      style={{
        background: colors.bg,
        border: `1px solid ${colors.border}`,
      }}
    >
      <div className="flex items-center gap-1" style={{ color: colors.text }}>
        {chip.icon}
      </div>
      <span
        className="text-xs font-semibold tabular-nums leading-none"
        style={{ color: colors.text }}
      >
        {chip.value}
      </span>
      <span
        className="text-xs leading-none text-center"
        style={{ color: 'var(--color-muted-foreground)', fontSize: '10px' }}
      >
        {chip.label}
      </span>
      {/* Status dot */}
      <div
        className="size-1.5 rounded-full mt-0.5"
        style={{ background: colors.dot }}
      />
    </div>
  )
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export function HacerDeporte({ location }: Props) {
  const { data, isLoading, error } = useHacerDeporte(location?.lat ?? null, location?.lon ?? null)

  if (location === null) return <PageSkeleton />

  // Build condition chips from real data
  const buildChips = (): ConditionChip[] => {
    if (!data) return []
    const chips: ConditionChip[] = []

    if (data.temp !== null) {
      chips.push({
        icon: <Thermometer className="size-4" />,
        label: 'Temperatura',
        value: `${data.temp.toFixed(0)}°C`,
        status: getTempStatus(data.temp),
      })
    }
    if (data.humidity !== null) {
      chips.push({
        icon: <Droplets className="size-4" />,
        label: 'Humedad',
        value: `${data.humidity}%`,
        status: getHumidityStatus(data.humidity),
      })
    }
    if (data.wind_speed !== null) {
      chips.push({
        icon: <Wind className="size-4" />,
        label: 'Viento',
        value: `${data.wind_speed} km/h`,
        status: getWindStatus(data.wind_speed),
      })
    }
    if (data.precip !== null) {
      chips.push({
        icon: <CloudRain className="size-4" />,
        label: 'Lluvia',
        value: data.precip === 0 ? 'Sin lluvia' : `${data.precip.toFixed(1)} mm`,
        status: getPrecipStatus(data.precip),
      })
    }
    return chips
  }

  return (
    <div>
      {/* ── Header ── */}
      <header className="mb-8 flex items-start gap-4">
        <div
          className="shrink-0 size-16 rounded-2xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgba(200,168,75,0.22) 0%, rgba(200,168,75,0.06) 100%)',
            border: '1px solid rgba(200,168,75,0.18)',
          }}
        >
          <Dumbbell className="size-8" style={{ color: '#c8a84b' }} />
        </div>
        <div className="flex-1 min-w-0">
          <h1
            className="text-2xl font-semibold leading-tight"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Hacer deporte
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-muted-foreground)' }}>
            {location.label}
          </p>
        </div>
      </header>

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}

      {data && (
        <FadeContent>
          <div className="space-y-5">

            {/* ── Gauge hero card ── */}
            <div
              className="rounded-2xl p-6 flex flex-col items-center gap-3"
              style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
            >
              <IndexGauge value={data.score} label={data.label} size={200} />
              <p
                className="text-base font-medium text-center max-w-xs leading-snug"
                style={{ color: 'var(--color-foreground)' }}
              >
                {data.headline}
              </p>
              <p
                className="text-sm text-center max-w-xs leading-relaxed"
                style={{ color: 'var(--color-muted-foreground)' }}
              >
                {data.reason}
              </p>
            </div>

            {/* ── Condition chips (semáforo) ── */}
            {buildChips().length > 0 && (
              <div className="flex gap-2">
                {buildChips().map((chip) => (
                  <ConditionChip key={chip.label} chip={chip} />
                ))}
              </div>
            )}

            {/* ── Mejor momento card ── */}
            {data.best_window && (
              <div
                className="rounded-2xl p-4"
                style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
              >
                <p
                  className="text-xs font-medium uppercase tracking-wider mb-3"
                  style={{ color: 'var(--color-muted-foreground)' }}
                >
                  Ventana óptima
                </p>
                <HourlyTimeline
                  bestWindow={data.best_window}
                  label="Mejor momento para salir"
                />
              </div>
            )}

            {/* ── Stats grid ── */}
            <div className="grid grid-cols-2 gap-3">
              {data.temp !== null && (
                <StatCard
                  label="Temperatura"
                  value={data.temp.toFixed(1)}
                  unit="°C"
                  icon={<Thermometer className="size-4" />}
                />
              )}
              {data.humidity !== null && (
                <StatCard
                  label="Humedad relativa"
                  value={data.humidity}
                  unit="%"
                  icon={<Droplets className="size-4" />}
                />
              )}
              {data.wind_speed !== null && (
                <StatCard
                  label="Velocidad viento"
                  value={data.wind_speed}
                  unit="km/h"
                  icon={<Wind className="size-4" />}
                />
              )}
              {data.precip !== null && (
                <StatCard
                  label="Precipitación 12h"
                  value={data.precip.toFixed(1)}
                  unit="mm"
                  icon={<CloudRain className="size-4" />}
                />
              )}
            </div>

          </div>
        </FadeContent>
      )}
    </div>
  )
}

// ─── Page states ─────────────────────────────────────────────────────────────

function PageSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      {/* Gauge card skeleton */}
      <div className="h-72 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
      {/* Chips skeleton */}
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex-1 h-20 rounded-xl" style={{ background: 'var(--color-muted)' }} />
        ))}
      </div>
      {/* Timeline card skeleton */}
      <div className="h-20 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
      {/* Stats skeleton */}
      <div className="grid grid-cols-2 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl" style={{ background: 'var(--color-muted)' }} />
        ))}
      </div>
    </div>
  )
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div
      className="rounded-xl p-4 text-sm"
      style={{
        border: '1px solid rgba(224,85,69,0.3)',
        background: 'rgba(224,85,69,0.05)',
        color: 'var(--color-destructive)',
      }}
    >
      Error: {message}
    </div>
  )
}
