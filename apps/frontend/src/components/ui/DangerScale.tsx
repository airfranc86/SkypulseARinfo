export type DangerLevel = 1 | 2 | 3 | 4 | 5

export const DANGER_COLORS: Record<DangerLevel, string> = {
  1: '#3ecf7a',
  2: '#a8c820',
  3: '#f0a030',
  4: '#e05545',
  5: '#ff3333',
}

export function DangerScale({ level }: { level: DangerLevel }) {
  if (import.meta.env.DEV && ![1, 2, 3, 4, 5].includes(level as number)) {
    throw new Error(`DangerScale: nivel inválido "${level}". Esperado: 1|2|3|4|5.`)
  }
  const activeColor = DANGER_COLORS[level]
  const hasGlow = level >= 4
  return (
    <div className="flex gap-[3px] items-center mt-0.5">
      {([1, 2, 3, 4, 5] as const).map(i => (
        <span
          key={i}
          className="flex-1 h-1.5 rounded-sm"
          style={{
            background: i <= level ? activeColor : 'var(--color-border)',
            ...(hasGlow && i <= level ? { boxShadow: `0 0 4px 1px ${activeColor}88` } : {}),
          }}
        />
      ))}
    </div>
  )
}
