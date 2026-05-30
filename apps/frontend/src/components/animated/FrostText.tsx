import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface FrostTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function FrostText({ text, fontSize = '1rem', className = '' }: FrostTextProps): ReactElement {
  const [frozen, setFrozen] = useState(false)
  const chars = [...text]

  const handleClick = useCallback(() => {
    if (!frozen) setFrozen(true)
  }, [frozen])

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        cursor: frozen ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'inline-flex',
        flexWrap: 'wrap',
        fontFamily: 'var(--font-serif)',
        color: 'var(--color-foreground)',
      }}
    >
      {chars.map((char, i) => {
        const isSpace = char === ' '
        // negative → upward movement (vapor rising)
        const frostRise = -randomBetween(14, 28)
        const duration = randomBetween(1200, 1600)
        // stagger right→left — cold descends from the peaks
        const delay = (chars.length - 1 - i) * randomBetween(50, 80)

        const animStyle: CSSProperties =
          frozen && !isSpace
            ? {
                '--frost-rise': `${frostRise}px`,
                animationName: 'charFrost',
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
