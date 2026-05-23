function getActiveLevelIndex(mag: number): number {
  if (mag >= 7) return 5
  if (mag >= 6) return 4
  if (mag >= 5) return 3
  if (mag >= 4) return 2
  if (mag >= 3) return 1
  return 0
}

interface MagnitudeScaleBarProps {
  /** Highlight the band corresponding to this magnitude value */
  activeMagnitude?: number
}

const LEVELS = [
  {
    label: 'M2',
    name: 'Micro',
    emoji: '🟢',
    /** Qué pasa en tu casa */
    comparison: 'Se siente acostado, difícil de notar de pie',
    color: '#3ecf7a',
  },
  {
    label: 'M3',
    name: 'Menor',
    emoji: '🟡',
    comparison: 'Tiemblan cuadros y puertas entornadas',
    color: '#a8d060',
  },
  {
    label: 'M4',
    name: 'Ligero',
    emoji: '🟠',
    comparison: 'Caen objetos de estantes y se abren cajones',
    color: '#f0d060',
  },
  {
    label: 'M5',
    name: 'Moderado',
    emoji: '🔶',
    comparison: 'Grietas en paredes, muebles se desplazan',
    color: '#f0a030',
  },
  {
    label: 'M6',
    name: 'Fuerte',
    emoji: '🔴',
    comparison: 'Daño estructural grave, paredes derrumbadas',
    color: '#e05545',
  },
  {
    label: 'M7+',
    name: 'Mayor',
    emoji: '🟥',
    comparison: 'Destrucción extensa, difícil mantenerse de pie',
    color: '#aa2222',
  },
] as const

export function MagnitudeScaleBar({ activeMagnitude }: MagnitudeScaleBarProps) {
  const n = LEVELS.length
  const activeIdx = activeMagnitude != null ? getActiveLevelIndex(activeMagnitude) : -1

  return (
    <div
      className="rounded-xl p-4 space-y-3"
      style={{
        background: 'var(--color-card)',
        border: '1px solid var(--color-border)',
      }}
    >
      {/* Title */}
      <p
        className="text-xs uppercase tracking-wide"
        style={{ color: 'var(--color-muted-foreground)' }}
      >
        Escala de magnitud (Mw) · qué pasa en tu casa
      </p>

      {/* Gradient bar + label ticks */}
      <div className="relative pb-5">
        {/* Gradient bar */}
        <div
          className="h-2 rounded-full w-full"
          style={{
            background:
              'linear-gradient(to right, #3ecf7a, #a8d060, #f0d060, #f0a030, #e05545, #aa2222)',
          }}
        />

        {/* Active magnitude dot on the bar */}
        {activeIdx >= 0 && (
          <div
            aria-label={`Magnitud activa: ${LEVELS[activeIdx].label}`}
            style={{
              position: 'absolute',
              left: `${(activeIdx / (n - 1)) * 100}%`,
              top: '-5px',
              transform: 'translateX(-50%)',
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              background: LEVELS[activeIdx].color,
              boxShadow: `0 0 8px 2px ${LEVELS[activeIdx].color}88`,
              border: '2px solid var(--color-background)',
            }}
          />
        )}

        {/* Tick marks + labels debajo */}
        {LEVELS.map((level, i) => {
          const pct = (i / (n - 1)) * 100
          return (
            <div
              key={level.label}
              className="absolute"
              style={{ left: `${pct}%`, top: 0, transform: 'translateX(-50%)' }}
            >
              {/* tick */}
              <div
                style={{
                  width: '1px',
                  height: '10px',
                  marginTop: '0px',
                  background: level.color,
                  opacity: 0.85,
                  marginLeft: 'auto',
                  marginRight: 'auto',
                }}
              />
              {/* label debajo del tick */}
              <span
                style={{
                  display: 'block',
                  fontSize: '9px',
                  fontWeight: 600,
                  color: level.color,
                  textAlign: 'center',
                  marginTop: '2px',
                  whiteSpace: 'nowrap',
                }}
              >
                {level.label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Level chips */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {LEVELS.map((level, i) => {
          const isActive = i === activeIdx
          return (
          <div
            key={level.label}
            className="rounded-lg px-2 py-2 flex flex-col gap-0.5"
            style={{
              background: isActive ? `${level.color}28` : `${level.color}14`,
              border: `1px solid ${isActive ? level.color : `${level.color}33`}`,
              outline: isActive ? `1px solid ${level.color}55` : undefined,
              outlineOffset: isActive ? '1px' : undefined,
            }}
          >
            <div className="flex items-center gap-1">
              <span style={{ fontSize: '10px' }}>{level.emoji}</span>
              <span className="text-xs font-bold" style={{ color: level.color }}>
                {level.label}
              </span>
              <span
                className="text-xs"
                style={{ color: 'var(--color-muted-foreground)' }}
              >
                · {level.name}
              </span>
            </div>
            <span
              className="text-xs leading-tight"
              style={{ color: 'var(--color-foreground)', marginTop: '2px' }}
            >
              {level.comparison}
            </span>
          </div>
          )
        })}
      </div>
    </div>
  )
}
