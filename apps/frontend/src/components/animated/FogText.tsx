import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface FogTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function FogText({ text, fontSize = '1rem', className = '' }: FogTextProps): ReactElement {
  const [fogged, setFogged] = useState(false)
  const chars = [...text]

  const handleClick = useCallback(() => {
    if (!fogged) setFogged(true)
  }, [fogged])

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        cursor: fogged ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'inline-flex',
        flexWrap: 'wrap',
        fontFamily: 'var(--font-serif)',
        color: 'var(--color-foreground)',
      }}
    >
      {chars.map((char, i) => {
        const isSpace = char === ' '
        const fogDriftX = randomBetween(6, 12) * (Math.random() < 0.5 ? 1 : -1)
        const duration = randomBetween(1100, 1600)
        // random stagger — fog has no direction
        const delay = randomBetween(0, 300)

        const animStyle: CSSProperties =
          fogged && !isSpace
            ? {
                '--fog-drift-x': `${fogDriftX}px`,
                animationName: 'charFog',
                animationDuration: `${duration}ms`,
                animationDelay: `${delay}ms`,
                animationTimingFunction: 'ease-out',
                animationFillMode: 'forwards',
              } as CSSProperties
            : {}

        return (
          <span key={i} style={{ display: 'inline-block', ...(isSpace ? { minWidth: '0.3em' } : {}), ...animStyle }}>
            {char}
          </span>
        )
      })}
    </div>
  )
}
