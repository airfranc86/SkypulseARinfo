import type { ReactNode } from 'react'
import { Thermometer, Droplets, Sun, Wind, CloudRain, CloudLightning, type LucideIcon } from 'lucide-react'
import { WeatherIcon } from '@/components/ui/WeatherIcon'
import { WindArrow } from '@/components/ui/WindArrow'
import { BorderGlow } from '@/components/animated/BorderGlow'
import type { VerdictLine, VerdictTone } from '@/lib/weatherVerdict'
import type { CurrentDetailed, DailyEntry } from '@/lib/api'

const WIND_COLOR: Record<string, string> = {
  moderada: '#c8a84b',
  intensa:  '#e03535',
}

function minutesAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diffMs / 60_000)
  if (mins < 2) return 'Ahora'
  if (mins < 60) return `Hace ${mins} min`
  const h = Math.floor(mins / 60)
  return `Hace ${h}h`
}

const TONE: Record<VerdictTone, { Icon: LucideIcon; color: string }> = {
  rain:  { Icon: CloudRain,      color: 'var(--color-info)' },
  clear: { Icon: Sun,            color: 'var(--color-safe)' },
  wind:  { Icon: Wind,           color: 'var(--color-watch)' },
  storm: { Icon: CloudLightning, color: 'var(--color-warn)' },
}

interface Props {
  current: CurrentDetailed
  /** Hoy en el pronóstico de 7 días: de ahí salen la máxima y la mínima. */
  today?: DailyEntry
  /** Lo que viene en las próximas 24 h, ya redactado (ver lib/weatherVerdict). */
  verdict: VerdictLine[]
}

function formatDegrees(value: number | null): string {
  return value !== null ? `${Math.round(value)}°` : '—'
}

export function WeatherHero({ current, today, verdict }: Props) {
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
      className="rounded-2xl p-7 sm:p-10"
      style={{ position: 'relative', background: 'var(--color-card)' }}
    >
      {/* Top row: icon + temp + description — el primer viewport es esto */}
      <div className="flex items-start gap-6">
        <WeatherIcon code={current.icon} size={96} isDay={current.is_day} />

        <div className="flex-1 min-w-0">
          <p
            className="text-7xl sm:text-8xl md:text-9xl font-bold leading-none tracking-tight"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            {current.temp_c !== null ? Math.round(current.temp_c) : '—'}
            {/* El ° de Playfair a este cuerpo es un aro casi tan alto como el número: se compone
                aparte, en la sans y a escala de símbolo. */}
            {current.temp_c !== null && (
              <span
                aria-hidden="true"
                className="align-top ml-1 text-[0.42em] font-medium"
                style={{ fontFamily: 'var(--font-sans)' }}
              >
                °
              </span>
            )}
            {current.temp_c !== null && <span className="sr-only"> grados</span>}
          </p>
          <p
            className="mt-3 text-lg sm:text-xl"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            {current.description}
          </p>
          {today && (today.temp_max !== null || today.temp_min !== null) && (
            <p className="mt-2 text-base font-medium tabular-nums" style={{ color: 'var(--color-foreground)' }}>
              <span>Máx {formatDegrees(today.temp_max)}</span>
              <span aria-hidden="true" style={{ color: 'var(--color-muted-foreground)' }}> · </span>
              <span style={{ color: 'var(--color-muted-foreground)' }}>Mín {formatDegrees(today.temp_min)}</span>
            </p>
          )}
          {current.observed_at && (
            <p
              className="text-xs mt-0.5"
              style={{ color: 'var(--color-muted-foreground)' }}
            >
              {minutesAgo(current.observed_at)}
            </p>
          )}
        </div>
      </div>

      {/* Lo que viene: hora, cantidad y umbral, sin porcentajes ni promesas */}
      {verdict.length > 0 && (
        <div role="group" aria-label="Lo que viene en las próximas 24 horas" className="mt-6 space-y-2">
          {verdict.map(({ tone, text }) => {
            const { Icon, color } = TONE[tone]
            return (
              <p
                key={text}
                className="flex items-start gap-2.5 text-base leading-snug"
                style={{ color: 'var(--color-foreground)' }}
              >
                <Icon size={20} strokeWidth={1.75} className="mt-0.5 shrink-0" style={{ color }} aria-hidden="true" />
                <span>{text}</span>
              </p>
            )
          })}
        </div>
      )}

      {/* Stats grid */}
      <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Sensación — expanded chip with factor explanation */}
        <div
          className="rounded-xl px-3 py-2.5 flex flex-col gap-0.5 col-span-2 sm:col-span-1"
          style={{ background: 'rgba(200,168,75,0.06)', border: '1px solid rgba(200,168,75,0.12)' }}
        >
          <Thermometer size={18} strokeWidth={1.75} style={{ color: 'var(--color-primary)' }} />
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>Sensación</span>
          <span className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
            {current.feels_like_c !== null ? `${Math.round(current.feels_like_c)}°C` : '—'}
          </span>
          <span
            className="text-[11px] leading-snug mt-0.5"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            humedad · viento · rocío
          </span>
        </div>

        <StatChip
          icon={<Droplets size={18} strokeWidth={1.75} style={{ color: 'var(--color-primary)' }} />}
          label="Humedad"
          value={current.humidity !== null ? `${Math.round(current.humidity)}%` : '—'}
        />
        <WindChip current={current} />
        <StatChip
          icon={<Sun size={18} strokeWidth={1.75} style={{ color: 'var(--color-primary)' }} />}
          label="UV"
          value={current.uv_index !== null ? String(Math.round(current.uv_index)) : '—'}
        />
      </div>
    </div>
    </BorderGlow>
  )
}

function StatChip({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div
      className="rounded-xl px-3 py-2.5 flex flex-col gap-0.5"
      style={{ background: 'rgba(200,168,75,0.06)', border: '1px solid rgba(200,168,75,0.12)' }}
    >
      {icon}
      <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>{label}</span>
      <span className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>{value}</span>
    </div>
  )
}

function WindChip({ current }: { current: CurrentDetailed }) {
  const tier = current.wind_intensity
  const color = tier ? (WIND_COLOR[tier] ?? 'var(--color-foreground)') : 'var(--color-foreground)'
  const speedText = current.wind_speed_kmh !== null
    ? `${Math.round(current.wind_speed_kmh)} km/h`
    : '—'

  return (
    <div
      className="rounded-xl px-3 py-2.5 flex flex-col gap-0.5"
      style={{ background: 'rgba(200,168,75,0.06)', border: '1px solid rgba(200,168,75,0.12)' }}
    >
      {current.wind_icon
        ? <WeatherIcon code={current.wind_icon} size={24} />
        : <Wind size={18} strokeWidth={1.75} style={{ color: 'var(--color-primary)' }} />}
      <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>Viento</span>
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-sm font-medium" style={{ color }}>{speedText}</span>
        {current.wind_dir_deg !== null && current.wind_dir_deg !== undefined && (
          <WindArrow deg={current.wind_dir_deg} size={14} color={color} />
        )}
        {current.wind_dir_cardinal && (
          <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
            {current.wind_dir_cardinal}
          </span>
        )}
      </div>
    </div>
  )
}
