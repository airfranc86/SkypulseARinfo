import { WeatherIcon } from '@/components/ui/WeatherIcon'
import type { DayArcInfo, MoonPhaseInfo } from '@/lib/api'

interface Props {
  dayArc: DayArcInfo
  moonPhase: MoonPhaseInfo
  snowLevelM: number | null
}

/** Converts a time string "HH:MM" to a display label. */
function timeLabel(iso: string): string {
  const t = iso.includes('T') ? iso.split('T')[1] : iso
  return t.slice(0, 5)
}

export function DayArc({ dayArc, moonPhase, snowLevelM }: Props) {
  // Arc geometry (SVG viewBox 0 0 200 110)
  const cx = 100, cy = 100, r = 85

  // Sun position: clamp pct to [0,1] for arc drawing
  const pct = Math.max(0, Math.min(1, dayArc.current_position_pct))
  // Map pct to angle (180° → 0°, left to right through top)
  const angleDeg = 180 - pct * 180
  const angleRad = (angleDeg * Math.PI) / 180
  const sunX = cx + r * Math.cos(angleRad)
  const sunY = cy - r * Math.sin(angleRad)

  // Arc path: semicircle from left to right through top
  const arcPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`

  const isAfterSunset = dayArc.current_position_pct > 1

  return (
    <div
      className="rounded-2xl p-5"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      {/* SVG arc */}
      <svg viewBox="0 0 200 126" className="w-full" style={{ maxHeight: '140px' }}>
        <defs>
          <linearGradient id="arcGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#f0a030" stopOpacity="0.3" />
            <stop offset="50%" stopColor="#c8a84b" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#f0a030" stopOpacity="0.3" />
          </linearGradient>
        </defs>

        {/* Track */}
        <path
          d={arcPath}
          fill="none"
          stroke="rgba(200,168,75,0.15)"
          strokeWidth="3"
          strokeLinecap="round"
        />

        {/* Progress arc up to sun position */}
        {!isAfterSunset && (
          <path
            d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${sunX} ${sunY}`}
            fill="none"
            stroke="url(#arcGrad)"
            strokeWidth="3"
            strokeLinecap="round"
          />
        )}
        {isAfterSunset && (
          <path
            d={arcPath}
            fill="none"
            stroke="url(#arcGrad)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeOpacity="0.4"
          />
        )}

        {/* Sun dot */}
        {!isAfterSunset && (
          <>
            <circle cx={sunX} cy={sunY} r="8" fill="#f0a030" opacity="0.25" />
            <circle cx={sunX} cy={sunY} r="5" fill="#f0a030" />
          </>
        )}

        {/* Moon dot — solo cuando está sobre el horizonte y hay posición calculada */}
        {moonPhase.is_above_horizon && moonPhase.position_pct != null && (
          <>
            {(() => {
              const moonPct = Math.max(0, Math.min(1, moonPhase.position_pct))
              const moonAngleDeg = 180 - moonPct * 180
              const moonAngleRad = (moonAngleDeg * Math.PI) / 180
              const moonX = cx + r * Math.cos(moonAngleRad)
              const moonY = cy - r * Math.sin(moonAngleRad)
              return (
                <>
                  <circle cx={moonX} cy={moonY} r="7" fill="rgba(200,210,230,0.12)" />
                  <circle cx={moonX} cy={moonY} r="4" fill="#c8d8e8" opacity="0.85" />
                </>
              )
            })()}
          </>
        )}

        {/* Sunrise label */}
        <text
          x={cx - r + 2}
          y={cy + 12}
          fontSize="7"
          fill="var(--color-muted-foreground)"
          textAnchor="start"
        >
          {timeLabel(dayArc.sunrise)}
        </text>

        {/* Sunset label */}
        <text
          x={cx + r - 2}
          y={cy + 12}
          fontSize="7"
          fill="var(--color-muted-foreground)"
          textAnchor="end"
        >
          {timeLabel(dayArc.sunset)}
        </text>

        {/* Daylight label centered */}
        <text
          x={cx}
          y={cy + 12}
          fontSize="7"
          fill="var(--color-muted-foreground)"
          textAnchor="middle"
        >
          {dayArc.daylight_label}
        </text>
      </svg>

      {/* Footer: moon + snow */}
      <div className="mt-3 flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
          <WeatherIcon code={moonPhase.icon} size={24} />
          <span style={{ color: 'var(--color-muted-foreground)' }}>
            {moonPhase.name}
          </span>
          <span
            className="text-xs px-1.5 py-0.5 rounded-full"
            style={{ background: 'rgba(200,168,75,0.08)', color: 'var(--color-primary)' }}
          >
            {Math.round(moonPhase.illumination * 100)}%
          </span>
        </div>

        {snowLevelM !== null && (
          <div className="flex items-center gap-1.5">
            <span>❄️</span>
            <span className="text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
              Cota {Math.round(snowLevelM).toLocaleString('es-AR')} m
            </span>
            <span
              title="Cota de nieve: altura aproximada sobre el nivel del mar a partir de la cual puede nevar. Por debajo de este nivel la precipitación cae como lluvia."
              aria-label="¿Qué es la cota de nieve?"
              className="inline-flex items-center justify-center rounded-full text-[9px] font-bold cursor-help select-none"
              style={{
                width: '14px', height: '14px',
                background: 'rgba(200,168,75,0.15)',
                color: 'var(--color-primary)',
                border: '1px solid rgba(200,168,75,0.3)',
              }}
            >
              ?
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
