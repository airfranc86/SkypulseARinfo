const LEVELS = [
  {
    label: 'M2',
    name: 'Micro',
    comparison: 'camión pesado',
    color: '#3ecf7a',
  },
  {
    label: 'M3',
    name: 'Menor',
    comparison: 'explosión lejana',
    color: '#a8d060',
  },
  {
    label: 'M4',
    name: 'Ligero',
    comparison: 'colapso estructura',
    color: '#f0d060',
  },
  {
    label: 'M5',
    name: 'Moderado',
    comparison: 'explosión industrial',
    color: '#f0a030',
  },
  {
    label: 'M6',
    name: 'Fuerte',
    comparison: 'derrumbe edificio',
    color: '#e05545',
  },
  {
    label: 'M7+',
    name: 'Mayor',
    comparison: 'catastrófico',
    color: '#aa2222',
  },
] as const

export function MagnitudeScaleBar() {
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
        Escala de magnitud (Mw)
      </p>

      {/* Gradient bar with tick marks */}
      <div className="relative">
        {/* Gradient bar */}
        <div
          className="h-2 rounded-full w-full"
          style={{
            background:
              'linear-gradient(to right, #3ecf7a, #a8d060, #f0d060, #f0a030, #e05545, #aa2222)',
          }}
        />

        {/* Tick marks — positioned at the 6 equal segment boundaries */}
        <div className="absolute inset-0 flex items-center pointer-events-none">
          {LEVELS.map((level, i) => (
            <div
              key={level.label}
              className="absolute"
              style={{
                left: `${(i / (LEVELS.length - 1)) * 100}%`,
                transform: 'translateX(-50%)',
              }}
            >
              <div
                className="w-px"
                style={{
                  height: '12px',
                  marginTop: '-5px',
                  background: level.color,
                  opacity: 0.9,
                }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Level chips */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {LEVELS.map((level) => (
          <div
            key={level.label}
            className="rounded-lg px-2 py-2 flex flex-col gap-0.5"
            style={{
              background: `${level.color}14`,
              border: `1px solid ${level.color}33`,
            }}
          >
            <span className="text-xs font-bold" style={{ color: level.color }}>
              {level.label}
            </span>
            <span
              className="text-xs font-medium"
              style={{ color: 'var(--color-foreground)' }}
            >
              {level.name}
            </span>
            <span
              className="text-xs leading-tight"
              style={{ color: 'var(--color-muted-foreground)' }}
            >
              {level.comparison}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
