import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface RainTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function RainText({ text, fontSize = '1rem', className = '' }: RainTextProps): ReactElement {
  const [raining, setRaining] = useState(false)
  const chars = [...text]

  const handleClick = useCallback(() => {
    if (!raining) setRaining(true)
  }, [raining])

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        cursor: raining ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'inline-flex',
        flexWrap: 'wrap',
        fontFamily: 'var(--font-serif)',
        color: 'var(--color-foreground)',
      }}
    >
      {chars.map((char, i) => {
        const isSpace = char === ' '
        const rainDrop = randomBetween(60, 100)
        const duration = randomBetween(350, 550)
        // very short stagger — rain falls almost simultaneously
        const delay = i * randomBetween(0, 60)

        const animStyle: CSSProperties =
          raining && !isSpace
            ? {
                '--rain-drop': `${rainDrop}px`,
                animationName: 'charRain',
                animationDuration: `${duration}ms`,
                animationDelay: `${delay}ms`,
                animationTimingFunction: 'cubic-bezier(0.55, 0, 1, 0.45)',
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
