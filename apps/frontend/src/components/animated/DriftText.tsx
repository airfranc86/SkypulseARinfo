import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface DriftTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function DriftText({ text, fontSize = '1rem', className = '' }: DriftTextProps): ReactElement {
  const [drifting, setDrifting] = useState(false)
  const chars = [...text]

  const handleClick = useCallback(() => {
    if (!drifting) setDrifting(true)
  }, [drifting])

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        cursor: drifting ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'inline-flex',
        flexWrap: 'wrap',
        fontFamily: 'var(--font-serif)',
        color: 'var(--color-foreground)',
      }}
    >
      {chars.map((char, i) => {
        const isSpace = char === ' '
        // negative → upward
        const driftRise = -randomBetween(20, 45)
        const driftX = randomBetween(5, 10) * (Math.random() < 0.5 ? 1 : -1)
        const duration = randomBetween(1400, 1900)
        // random stagger — clouds drift at their own pace
        const delay = randomBetween(0, 400)

        const animStyle: CSSProperties =
          drifting && !isSpace
            ? {
                '--drift-rise': `${driftRise}px`,
                '--drift-x': `${driftX}px`,
                animationName: 'charDrift',
                animationDuration: `${duration}ms`,
                animationDelay: `${delay}ms`,
                animationTimingFunction: 'ease-out',
                animationFillMode: 'forwards',
              } as CSSProperties
            : {}

        return (
          <span key={i} style={{ display: 'inline-block', ...animStyle }}>
            {char}
          </span>
        )
      })}
    </div>
  )
}
