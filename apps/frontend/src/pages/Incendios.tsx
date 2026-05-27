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

// Condition thresholds that trigger critical styling
function isCriticalCondition(label: string, value: string | number | null): boolean {
  if (value === null || value === undefined) return false
  const n = typeof value === 'string' ? parseFloat(value) : value
  if (label === 'Humedad' && n < 20) return true
  if (label === 'Viento' && n > 60) return true
  if (label === 'Temperatura' && n > 38) return true
  return false
}

// Emoji icons for each condition chip
const CONDITION_ICONS: Record<string, string> = {
  'Temperatura':   '🌡️',
  'Humedad':       '💧',
  'Viento':        '💨',
  'Precipitación': '🌧️',
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

  // Needle angle: map 0–100 score to 180°–0° (left to right)
  const needleAngleDeg = 180 - (score / 100) * 180
  const needleAngleRad = (needleAngleDeg * Math.PI) / 180
  const needleLen = 40
  const needleX = cx + needleLen * Math.cos(needleAngleRad)
  const needleY = cy - needleLen * Math.sin(needleAngleRad)

  return (
    <svg
      viewBox="0 0 140 90"
      aria-label={`Score de riesgo: ${score} de 100`}
      className="w-full max-w-xs mx-auto"
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
      {/* Needle with white stroke for visibility */}
      <line
        x1={cx}
        y1={cy}
        x2={needleX}
        y2={needleY}
        stroke="white"
        strokeWidth="3.5"
        strokeLinecap="round"
        opacity="0.5"
      />
      <line
        x1={cx}
        y1={cy}
        x2={needleX}
        y2={needleY}
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        className="motion-safe:[transition:all_0.6s_ease]"
      />
      {/* Needle pivot */}
      <circle cx={cx} cy={cy} r="4" fill={color} />
      <circle cx={cx} cy={cy} r="2.5" fill="white" opacity="0.8" />

      {/* Score text — background rect for legibility */}
      <rect
        x={cx - 22}
        y={cy - 26}
        width="44"
        height="22"
        rx="5"
        fill="var(--color-card)"
        opacity="0.75"
      />
      <text
        x={cx}
        y={cy - 10}
        textAnchor="middle"
        fontSize="18"
        fontWeight="700"
        fill="var(--color-foreground)"
        fontFamily="var(--font-serif)"
      >
        {score}
      </text>
      <text
        x={cx}
        y={cy + 6}
        textAnchor="middle"
        fontSize="8"
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

/** Chip de condición meteorológica con ícono y alerta crítica. */
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
  const critical = isCriticalCondition(label, value)
  const icon = CONDITION_ICONS[label] ?? '📊'

  return (
    <div
      className="rounded-xl px-4 py-3 flex flex-col gap-1"
      style={{
        background: 'var(--color-card)',
        border: critical
          ? '1.5px solid rgba(224,85,69,0.6)'
          : '1px solid var(--color-border)',
        boxShadow: critical ? '0 0 0 3px rgba(224,85,69,0.08)' : undefined,
      }}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-sm leading-none" aria-hidden="true">{icon}</span>
        <span className="text-[.6rem] uppercase tracking-widest" style={{ color: 'var(--color-muted-foreground)' }}>
          {label}
        </span>
      </div>
      <span
        className="text-base font-semibold"
        style={{ color: critical ? '#e05545' : 'var(--color-foreground)' }}
      >
        {display}
      </span>
    </div>
  )
}

/** Formatea "2026-06-02 09:00" → "Hoy 09:00" / "Mañana 09:00" / "2 jun 09:00" */
function formatPeakTime(raw: string): string {
  const parts = raw.split(' ')
  if (parts.length < 2) return raw
  const [datePart, timePart] = parts
  const today = new Date()
  const todayStr = today.toISOString().slice(0, 10)
  const tomorrow = new Date(today)
  tomorrow.setDate(tomorrow.getDate() + 1)
  const tomorrowStr = tomorrow.toISOString().slice(0, 10)
  if (datePart === todayStr)     return `Hoy ${timePart}`
  if (datePart === tomorrowStr)  return `Mañana ${timePart}`
  const d = new Date(`${datePart}T12:00:00`)
  return `${d.getDate()} ${d.toLocaleDateString('es-AR', { month: 'short' })} ${timePart}`
}

interface RiskGroup {
  hourLabel: string
  maxScore: number
  color: string
  label: string
  isNow: boolean
}

/** Mini timeline de barras de riesgo — 8 grupos de 3h, sin scroll. */
function RiskTimeline({ slots }: { slots: FireDangerSlot[] }) {
  const first24 = slots.slice(0, 24)

  // Group into 8 buckets of 3 slots; each bucket shows the max-score slot's color/label
  const BUCKET = 3
  const groups: RiskGroup[] = Array.from({ length: 8 }, (_, gi) => {
    const chunk = first24.slice(gi * BUCKET, gi * BUCKET + BUCKET)
    if (!chunk.length) return null
    const maxScore = Math.max(...chunk.map(s => s.fire_risk_score))
    const peak = chunk.find(s => s.fire_risk_score === maxScore) ?? chunk[0]
    return {
      hourLabel: chunk[0].hour_label,
      maxScore,
      color: RISK_COLORS[peak.fire_risk_label] ?? '#f0a030',
      label: peak.fire_risk_label,
      isNow: gi === 0,
    } satisfies RiskGroup
  }).filter((g): g is RiskGroup => g !== null)

  const globalMax = Math.max(...groups.map(g => g.maxScore), 1)

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-xs font-medium mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Próximas 24 h
      </p>
      <div className="flex items-end gap-1.5 h-14">
        {groups.map((g, i) => {
          const heightPct = (g.maxScore / globalMax) * 100
          return (
            <div
              key={i}
              className="flex-1 flex flex-col items-center justify-end gap-1 cursor-help"
              title={`${g.hourLabel} — ${g.label} (${g.maxScore})`}
            >
              <div
                className="w-full rounded-sm transition-all"
                style={{
                  height: `${Math.max(heightPct, 5)}%`,
                  background: g.color,
                  opacity: g.isNow ? 1 : 0.72,
                  minHeight: '3px',
                  outline: g.isNow ? `2px solid ${g.color}` : undefined,
                  outlineOffset: g.isNow ? '1px' : undefined,
                }}
              />
            </div>
          )
        })}
      </div>
      {/* Hour labels */}
      <div className="flex items-center mt-1.5">
        {groups.map((g, i) => (
          <div key={i} className="flex-1 text-center">
            <span
              className="text-[.5rem]"
              style={{
                color: g.isNow ? 'var(--color-primary)' : 'var(--color-muted-foreground)',
                fontWeight: g.isNow ? 700 : undefined,
              }}
            >
              {g.hourLabel}
            </span>
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
  const peakColor = RISK_COLORS[data?.peak_label ?? ''] ?? '#f0a030'

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
              {/* Responsive gauge: fills on mobile, capped on desktop */}
              <div className="w-full max-w-xs mx-auto">
                <ScoreGauge score={data.current_score} color={data.current_color} />
              </div>

              {/* Risk label with background for legibility */}
              <div className="flex flex-col items-center gap-2">
                <span
                  className="text-xl font-bold tracking-tight px-3 py-0.5 rounded-lg"
                  style={{
                    color: data.current_color,
                    fontFamily: 'var(--font-serif)',
                    background: `${data.current_color}18`,
                  }}
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

            {/* Pico de riesgo — compact single-row */}
            <div
              className="rounded-xl px-5 py-3 flex items-center justify-between gap-3"
              style={{
                background: 'var(--color-card)',
                border: `1.5px solid ${peakColor}55`,
              }}
            >
              <p
                className="text-[.6rem] font-semibold uppercase tracking-widest"
                style={{ color: 'var(--color-muted-foreground)' }}
              >
                Pico de riesgo
              </p>
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-medium"
                  style={{ color: 'var(--color-foreground)' }}
                >
                  {formatPeakTime(data.peak_hour_label)}
                </span>
                <span
                  className="text-xs font-bold px-2.5 py-0.5 rounded-full"
                  style={{
                    color: peakColor,
                    background: `${peakColor}20`,
                    border: `1.5px solid ${peakColor}55`,
                    fontFamily: 'var(--font-serif)',
                  }}
                >
                  {data.peak_label}
                </span>
              </div>
            </div>

            {/* Footer — compact single line */}
            <p className="text-[.6rem] text-center" style={{ color: 'var(--color-muted-foreground)' }}>
              ⓘ {data.is_estimated ? 'Estimado' : 'Windy'} · Caché 1 h
            </p>
          </div>
        </FadeContent>
      )}
    </div>
  )
}
