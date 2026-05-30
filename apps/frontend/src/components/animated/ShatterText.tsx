import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface ShatterTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function ShatterText({ text, fontSize = '1rem', className = '' }: ShatterTextProps): ReactElement {
  const [shattered, setShattered] = useState(false)
  const words = text.split(' ')

  const handleClick = useCallback(() => {
    if (!shattered) setShattered(true)
  }, [shattered])

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        lineHeight: 1.4,
        cursor: shattered ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '0 6px',
        alignItems: 'baseline',
      }}
    >
      {words.map((word, i) => {
        // fallDist always positive → siempre cae hacia abajo
        const fallDist  = randomBetween(140, 300)
        const fallDrift = randomBetween(0, 70) * (Math.random() < 0.5 ? 1 : -1)
        const fallRot   = randomBetween(15, 55) * (Math.random() < 0.5 ? 1 : -1)
        const duration  = randomBetween(550, 850)
        const delay     = randomBetween(0, 160)

        const animStyle: CSSProperties = shattered
          ? {
              '--fall-dist': `${fallDist}px`,
              '--fall-drift': `${fallDrift}px`,
              '--fall-rot': `${fallRot}deg`,
              animationName: 'shatterFall',
              animationDuration: `${duration}ms`,
              animationDelay: `${delay}ms`,
              animationTimingFunction: 'cubic-bezier(0.55, 0, 1, 0.45)',
              animationFillMode: 'forwards',
            } as CSSProperties
          : {}

        return (
          <span
            key={`${word}-${i}`}
            style={{
              display: 'inline-block',
              color: 'var(--color-foreground)',
              fontFamily: 'var(--font-serif)',
              ...animStyle,
            }}
          >
            {word}
          </span>
        )
      })}
    </div>
  )
}
