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
        const fallDist  = randomBetween(80, 220) * (Math.random() < 0.5 ? 1 : -1)
        const fallDrift = randomBetween(0, 60)   * (Math.random() < 0.5 ? 1 : -1)
        const fallRot   = randomBetween(0, 45)   * (Math.random() < 0.5 ? 1 : -1)
        const duration  = randomBetween(700, 1100)
        const delay     = randomBetween(0, 180)

        const animStyle: CSSProperties = shattered
          ? {
              '--fall-dist': `${fallDist}px`,
              '--fall-drift': `${fallDrift}px`,
              '--fall-rot': `${fallRot}deg`,
              animationName: 'shatterFall',
              animationDuration: `${duration}ms`,
              animationDelay: `${delay}ms`,
              animationTimingFunction: 'cubic-bezier(0.36, 0, 0.66, -0.56)',
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
