import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { BorderGlow } from '@/components/animated/BorderGlow'
import { ModelBadge } from '@/components/ui/ModelBadge'
import type { ModelKey } from '@/components/ui/ModelBadge'
import type { CurrentDetailed } from '@/lib/api'

function sourceToModel(source: string | undefined): ModelKey {
  if (source === 'smn') return 'smn'
  if (source === 'openmeteo' || source === 'openmeteo_fallback') return 'openmeteo'
  if (source === 'windy_gfs') return 'gfs'
  if (source === 'windy_ecmwf') return 'windy_ecmwf'
  return 'smn' // default
}

interface Props {
  current: CurrentDetailed
  locationLabel: string
}

export function WeatherHero({ current, locationLabel }: Props) {
  return (
    <BorderGlow
      animated
      glowColor="40 65 54"
      colors={['#c8a84b', '#f0d060', '#5aaad8']}
      borderRadius={16}
      glowRadius={40}
      glowIntensity={0.8}
      fillOpacity={0.25}
      backgroundColor="#0d1625"
    >
    <div
      className="rounded-2xl p-6"
      style={{ position: 'relative', background: 'var(--color-card)' }}
    >
      {/* Source badge — usa ModelBadge para consistencia visual y popover informativo */}
      <ModelBadge model={sourceToModel(current.source)} variant="inline" />
      {/* Top row: icon + temp + description */}
      <div className="flex items-start gap-5">
        <WeatherIcon code={current.icon} size={72} />

        <div className="flex-1 min-w-0">
          <p
            className="text-6xl sm:text-7xl font-bold leading-none tracking-tight"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            {current.temp_c !== null ? `${Math.round(current.temp_c)}°` : '—'}
          </p>
          <p
            className="mt-2 text-base"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            {current.description}
          </p>
          <p
            className="text-xs mt-1"
            style={{ color: 'rgba(200,168,75,0.7)' }}
          >
            {locationLabel}
          </p>
        </div>
      </div>

      {/* Stats grid */}
      <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Sensación — expanded chip with factor explanation */}
        <div
          className="rounded-xl px-3 py-2.5 flex flex-col gap-0.5 col-span-2 sm:col-span-1"
          style={{ background: 'rgba(200,168,75,0.06)', border: '1px solid rgba(200,168,75,0.12)' }}
        >
          <span className="text-base">🌡️</span>
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>Sensación</span>
          <span className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
            {current.feels_like_c !== null ? `${Math.round(current.feels_like_c)}°C` : '—'}
          </span>
          <span
            className="text-[10px] leading-snug mt-0.5"
            style={{ color: 'var(--color-muted-foreground)', opacity: 0.7 }}
          >
            humedad · viento · rocío
          </span>
        </div>

        <StatChip
          icon="💧"
          label="Humedad"
          value={current.humidity !== null ? `${Math.round(current.humidity)}%` : '—'}
        />
        <StatChip
          icon="💨"
          label="Viento"
          value={
            current.wind_speed_kmh !== null
              ? `${Math.round(current.wind_speed_kmh)} km/h${current.wind_dir_cardinal ? ` ${current.wind_dir_cardinal}` : ''}`
              : '—'
          }
        />
        <StatChip
          icon="☀️"
          label="UV"
          value={current.uv_index !== null ? String(Math.round(current.uv_index)) : '—'}
        />
      </div>
    </div>
    </BorderGlow>
  )
}

function StatChip({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div
      className="rounded-xl px-3 py-2.5 flex flex-col gap-0.5"
      style={{ background: 'rgba(200,168,75,0.06)', border: '1px solid rgba(200,168,75,0.12)' }}
    >
      <span className="text-base">{icon}</span>
      <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>{label}</span>
      <span className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>{value}</span>
    </div>
  )
}
