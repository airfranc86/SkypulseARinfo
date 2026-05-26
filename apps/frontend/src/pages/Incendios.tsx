import type { FireDangerSlot } from '@/lib/api'
import { useFireDanger } from '@/hooks/useWeather'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { FadeContent } from '@/components/animated/FadeContent'
import { PageHeader } from '@/components/ui/PageHeader'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  location: { lat: number; lon: number } | null
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RISK_COLORS: Record<string, string> = {
  'Muy bajo': '#3ecf7a',
  'Bajo':     '#7ec855',
  'Moderado': '#f0a030',
  'Alto':     '#e05545',
  'Muy alto': '#e03535',
  'Extremo':  '#ff3333',
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** SVG semicircular gauge showing score 0–100. */
function ScoreGauge({ score, color }: { score: number; color: string }) {
  const radius = 54
  const cx = 70
  const cy = 70
  // Semicircle: from 180° to 0° (left to right, top half)
  const circumference = Math.PI * radius  // half-circle arc length
  const progress = (score / 100) * circumference

  // Arc path: start at left (180°), end at right (0°)
  const startX = cx - radius
  const startY = cy
  const endX   = cx + radius
  const endY   = cy

  return (
    <svg
      viewBox="0 0 140 80"
      aria-label={`Score de riesgo: ${score} de 100`}
      className="w-full max-w-[220px]"
    >
      {/* Track */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth="10"
        strokeLinecap="round"
      />
      {/* Progress */}
      <path
        d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
        fill="none"
        stroke={color}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${progress} ${circumference}`}
        className="motion-safe:[transition:stroke-dasharray_0.6s_ease]"
      />
      {/* Score text */}
      <text
        x={cx}
        y={cy - 6}
        textAnchor="middle"
        fontSize="22"
        fontWeight="700"
        fill="var(--color-foreground)"
        fontFamily="var(--font-serif)"
      >
        {score}
      </text>
      <text
        x={cx}
        y={cy + 10}
        textAnchor="middle"
        fontSize="9"
        fill="var(--color-muted-foreground)"
        fontFamily="var(--font-sans)"
      >
        / 100
      </text>
      {/* Min/Max labels */}
      <text x={startX + 2} y={cy + 18} fontSize="8" fill="var(--color-muted-foreground)">0</text>
      <text x={endX - 10} y={cy + 18} fontSize="8" fill="var(--color-muted-foreground)">100</text>
    </svg>
  )
}

/** Chip de condición meteorológica. */
function ConditionChip({
  label,
  value,
  unit,
}: {
  label: string
  value: string | number | null
  unit?: string
}) {
  const display = value !== null && value !== undefined
    ? `${value}${unit ? ` ${unit}` : ''}`
    : '—'

  return (
    <div
      className="rounded-xl px-4 py-3 flex flex-col gap-0.5"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <span className="text-[.6rem] uppercase tracking-widest" style={{ color: 'var(--color-muted-foreground)' }}>
        {label}
      </span>
      <span className="text-base font-semibold" style={{ color: 'var(--color-foreground)' }}>
        {display}
      </span>
    </div>
  )
}

/** Mini timeline de barras de riesgo (próximas 24h). */
function RiskTimeline({ slots }: { slots: FireDangerSlot[] }) {
  const first24 = slots.slice(0, 24)
  const maxScore = Math.max(...first24.map(s => s.fire_risk_score), 1)

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-xs font-medium mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Próximas 24 h
      </p>
      <div className="flex items-end gap-1 h-16">
        {first24.map((slot, i) => {
          const heightPct = (slot.fire_risk_score / maxScore) * 100
          const color = RISK_COLORS[slot.fire_risk_label] ?? '#f0a030'
          return (
            <div
              key={i}
              className="flex-1 flex flex-col items-center justify-end gap-0.5 group cursor-help"
              title={`${slot.hour_label} — ${slot.fire_risk_label} (${slot.fire_risk_score})`}
            >
              <div
                className="w-full rounded-sm transition-all"
                style={{
                  height: `${Math.max(heightPct, 4)}%`,
                  background: color,
                  opacity: 0.85,
                  minHeight: '3px',
                }}
              />
            </div>
          )
        })}
      </div>
      {/* Hour labels — solo cada 4 slots para no saturar */}
      <div className="flex items-center mt-1.5">
        {first24.map((slot, i) => (
          <div key={i} className="flex-1 text-center">
            {i % 4 === 0 && (
              <span className="text-[.5rem]" style={{ color: 'var(--color-muted-foreground)' }}>
                {slot.hour_label}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Skeleton de carga. */
function PageSkeleton() {
  return (
    <div className="space-y-5 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-start gap-4 mb-8">
        <div className="shrink-0 size-16 rounded-2xl" style={{ background: 'var(--color-muted)' }} />
        <div className="flex-1 space-y-2">
          <div className="h-7 rounded-lg w-48" style={{ background: 'var(--color-muted)' }} />
          <div className="h-4 rounded w-32" style={{ background: 'var(--color-muted)' }} />
        </div>
      </div>
      {/* Gauge skeleton */}
      <div className="flex justify-center">
        <div className="h-32 w-56 rounded-xl" style={{ background: 'var(--color-muted)' }} />
      </div>
      {/* Chips skeleton */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 rounded-xl" style={{ background: 'var(--color-muted)' }} />
        ))}
      </div>
      {/* Timeline skeleton */}
      <div className="h-28 rounded-xl" style={{ background: 'var(--color-muted)' }} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Incendios({ location }: Props) {
  const { data, isLoading, error } = useFireDanger(
    location?.lat ?? null,
    location?.lon ?? null,
  )

  if (location === null) return <PageSkeleton />

  const current = data?.slots[0] ?? null

  return (
    <div>
      <PageHeader
        icon={<span className="text-3xl">🔥</span>}
        title="Incendios"
        subtitle="Riesgo de incendio forestal por ubicación"
        accentColor="#e05545"
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}

      {data && (
        <FadeContent>
          <div className="space-y-5">
            {/* Score gauge + label central */}
            <div
              className="rounded-2xl p-6 flex flex-col items-center gap-3"
              style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
            >
              <ScoreGauge score={data.current_score} color={data.current_color} />

              {/* Risk label */}
              <div className="flex flex-col items-center gap-2">
                <span
                  className="text-xl font-bold tracking-tight"
                  style={{ color: data.current_color, fontFamily: 'var(--font-serif)' }}
                >
                  {data.current_label}
                </span>

                {/* Source badge */}
                <span
                  className="text-[.6rem] font-semibold uppercase tracking-wide px-2.5 py-1 rounded"
                  style={{
                    color: data.is_estimated ? '#f0a030' : '#3ecf7a',
                    background: data.is_estimated ? 'rgba(240,160,48,.08)' : 'rgba(62,207,122,.08)',
                    border: `1px solid ${data.is_estimated ? 'rgba(240,160,48,.25)' : 'rgba(62,207,122,.25)'}`,
                  }}
                >
                  {data.is_estimated ? 'Estimado' : 'Modelo Windy FWI'}
                </span>
              </div>
            </div>

            {/* Chips de condiciones */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <ConditionChip
                label="Temperatura"
                value={current?.temp_c !== null && current?.temp_c !== undefined
                  ? Math.round(current.temp_c)
                  : null}
                unit="°C"
              />
              <ConditionChip
                label="Humedad"
                value={current?.humidity !== null && current?.humidity !== undefined
                  ? Math.round(current.humidity)
                  : null}
                unit="%"
              />
              <ConditionChip
                label="Viento"
                value={current?.wind_kmh !== null && current?.wind_kmh !== undefined
                  ? Math.round(current.wind_kmh)
                  : null}
                unit="km/h"
              />
              <ConditionChip
                label="Precipitación"
                value={current?.precip_mm !== null && current?.precip_mm !== undefined
                  ? current.precip_mm.toFixed(1)
                  : null}
                unit="mm"
              />
            </div>

            {/* Timeline de riesgo */}
            {data.slots.length > 1 && <RiskTimeline slots={data.slots} />}

            {/* Pico de riesgo */}
            <div
              className="rounded-xl px-5 py-4 flex items-center justify-between gap-4"
              style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
            >
              <div>
                <p
                  className="text-[.6rem] font-semibold uppercase tracking-widest mb-0.5"
                  style={{ color: 'var(--color-muted-foreground)' }}
                >
                  Pico de riesgo
                </p>
                <p
                  className="text-sm font-medium"
                  style={{ color: 'var(--color-foreground)' }}
                >
                  {data.peak_hour_label}
                </p>
              </div>
              <div className="text-right">
                <span
                  className="text-lg font-bold"
                  style={{
                    color: RISK_COLORS[data.peak_label] ?? '#f0a030',
                    fontFamily: 'var(--font-serif)',
                  }}
                >
                  {data.peak_label}
                </span>
                <p className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                  Score {data.peak_score}
                </p>
              </div>
            </div>

            {/* Footer */}
            <p className="text-[.6rem] text-center" style={{ color: 'var(--color-muted-foreground)' }}>
              {data.is_estimated
                ? 'Índice estimado a partir de temperatura, humedad, viento y precipitación'
                : 'Fire Weather Index (FWI) — Canadian Forest Fire Danger Rating System'
              }
              {' · '}Caché 1 h
            </p>
          </div>
        </FadeContent>
      )}
    </div>
  )
}
