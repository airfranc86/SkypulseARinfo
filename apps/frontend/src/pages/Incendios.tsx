import type { FireDangerSlot } from '@/lib/api'
import { useFireDanger } from '@/hooks/useWeather'
import { ErrorMessage } from '@/components/ui/ErrorMessage'
import { FadeContent } from '@/components/animated/FadeContent'
import { PageHeader } from '@/components/ui/PageHeader'
import { ModelBadge } from '@/components/ui/ModelBadge'
import { BurnText } from '@/components/animated/BurnText'

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

const RISK_SCALE = [
  { label: 'Muy bajo', color: '#3ecf7a' },
  { label: 'Bajo',     color: '#7ec855' },
  { label: 'Moderado', color: '#f0a030' },
  { label: 'Alto',     color: '#e05545' },
  { label: 'Muy alto', color: '#e03535' },
  { label: 'Extremo',  color: '#ff3333' },
] as const

const HIGH_RISK_LABELS = new Set(['Alto', 'Muy alto', 'Extremo'])

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
        background: critical ? 'rgba(224,85,69,0.07)' : 'var(--color-card)',
        border: critical
          ? '1.5px solid rgba(224,85,69,0.55)'
          : '1px solid var(--color-border)',
        boxShadow: critical ? '0 0 18px rgba(224,85,69,0.12)' : undefined,
      }}
    >
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5">
          <span className="text-sm leading-none" aria-hidden="true">{icon}</span>
          <span className="text-[.6rem] uppercase tracking-widest" style={{ color: 'var(--color-muted-foreground)' }}>
            {label}
          </span>
        </div>
        {critical && (
          <span className="text-[.5rem] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: 'var(--color-warn)', background: 'rgba(224,85,69,0.12)' }}>
            ⚠ crítico
          </span>
        )}
      </div>
      <span
        className="text-base font-semibold"
        style={{ color: critical ? 'var(--color-warn)' : 'var(--color-foreground)' }}
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
        {groups.map((g) => {
          const heightPct = (g.maxScore / globalMax) * 100
          return (
            <div
              key={g.hourLabel}
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
        {groups.map((g) => (
          <div key={g.hourLabel} className="flex-1 text-center">
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

/** Barra segmentada que muestra los 6 niveles de riesgo con el nivel actual resaltado. */
function RiskScaleBar({ currentLabel }: { currentLabel: string }) {
  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-[.55rem] uppercase tracking-widest mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Escala de riesgo
      </p>
      <div className="flex gap-[3px] h-[10px]">
        {RISK_SCALE.map((r) => (
          <div
            key={r.label}
            className="flex-1 rounded-full transition-opacity"
            style={{
              background: r.color,
              opacity: r.label === currentLabel ? 1 : 0.25,
              outline: r.label === currentLabel ? `2px solid ${r.color}` : undefined,
              outlineOffset: r.label === currentLabel ? '2px' : undefined,
            }}
          />
        ))}
      </div>
      <div className="flex mt-2.5">
        {RISK_SCALE.map((r) => (
          <div key={r.label} className="flex-1 text-center">
            <span
              className="text-[.48rem] leading-tight block"
              style={{
                color: r.label === currentLabel ? r.color : 'var(--color-muted-foreground)',
                fontWeight: r.label === currentLabel ? 700 : undefined,
              }}
            >
              {r.label}
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
  const isHighRisk = HIGH_RISK_LABELS.has(data?.current_label ?? '')

  return (
    <div>
      <PageHeader
        icon={<img src="/icons/icon-incendios.png" width={48} height={48} style={{ objectFit: 'contain' }} alt="" />}
        title="Incendios"
        titleNode={<BurnText text="Incendios" fontSize="1.5rem" />}
        subtitle="Riesgo de incendio forestal por ubicación"
        accentColor="#e05545"
        modelBadge={data ? <ModelBadge model={data.is_estimated ? 'gfs' : 'windy_ecmwf'} variant="header" /> : undefined}
      />

      {isLoading && <PageSkeleton />}
      {error && <ErrorMessage message={(error as Error).message} />}

      {data && (
        <FadeContent>
          <div className="space-y-5">
            {/* Hero callout — solo cuando el riesgo es Alto o superior */}
            {isHighRisk && (
              <div
                className="rounded-xl px-5 py-4 flex items-start gap-4"
                style={{
                  background: `${data.current_color}0f`,
                  border: `1.5px solid ${data.current_color}45`,
                }}
              >
                <div className="relative flex-shrink-0 mt-1">
                  <span
                    className="absolute inset-0 rounded-full animate-ping opacity-50"
                    style={{ background: data.current_color }}
                  />
                  <span
                    className="relative block w-3 h-3 rounded-full"
                    style={{ background: data.current_color }}
                  />
                </div>
                <div>
                  <p className="text-sm font-bold leading-tight" style={{ color: data.current_color }}>
                    Riesgo {data.current_label}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-muted-foreground)' }}>
                    Las condiciones actuales favorecen la propagación de incendios forestales.
                  </p>
                </div>
              </div>
            )}

            {/* Escala de referencia */}
            <RiskScaleBar currentLabel={data.current_label} />

            {/* Score gauge + label central */}
            <div
              className="rounded-2xl p-6 flex flex-col items-center gap-3"
              style={{
                background: 'var(--color-card)',
                border: `1px solid ${isHighRisk ? `${data.current_color}40` : 'var(--color-border)'}`,
                boxShadow: isHighRisk ? `0 0 48px ${data.current_color}15` : undefined,
              }}
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
                    color: data.is_estimated ? 'var(--color-watch)' : 'var(--color-safe)',
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
              className="rounded-xl px-5 py-4 flex items-center justify-between gap-3"
              style={{
                background: `${peakColor}08`,
                border: `1.5px solid ${peakColor}45`,
              }}
            >
              <div>
                <p
                  className="text-[.55rem] font-semibold uppercase tracking-widest mb-1"
                  style={{ color: 'var(--color-muted-foreground)' }}
                >
                  Pico de riesgo
                </p>
                <span
                  className="text-sm font-medium"
                  style={{ color: 'var(--color-foreground)' }}
                >
                  {formatPeakTime(data.peak_hour_label)}
                </span>
              </div>
              <span
                className="text-sm font-bold px-3 py-1 rounded-full"
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
