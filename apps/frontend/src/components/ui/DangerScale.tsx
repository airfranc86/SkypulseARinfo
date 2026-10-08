import { DANGER_COLORS, dangerSummary, type DangerLevel } from '../../lib/dangerScale.ts'

export type { DangerLevel }

export function DangerScale({ level }: { level: DangerLevel }) {
  if (import.meta.env.DEV && ![1, 2, 3, 4, 5].includes(level as number)) {
    throw new Error(`DangerScale: nivel inválido "${level}". Esperado: 1|2|3|4|5.`)
  }
  const activeColor = DANGER_COLORS[level]
  const hasGlow = level >= 4
  return (
    <div role="img" aria-label={dangerSummary(level)} className="mt-0.5">
      <div className="flex gap-[3px] items-center">
        {([1, 2, 3, 4, 5] as const).map(i => (
          <span
            key={i}
            className="flex-1 h-1.5 rounded-sm motion-safe:[transition:all_0.6s_ease]"
            style={{
              background: i <= level ? activeColor : 'var(--color-border)',
              ...(hasGlow && i <= level ? { boxShadow: `0 0 4px 1px ${activeColor}88` } : {}),
            }}
          />
        ))}
      </div>
      <span className="block mt-1 text-xs leading-snug" style={{ color: 'var(--color-muted-foreground)' }}>
        {dangerSummary(level)}
      </span>
    </div>
  )
}
