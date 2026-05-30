import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface MeltTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function MeltText({ text, fontSize = '1rem', className = '' }: MeltTextProps): ReactElement {
  const [melting, setMelting] = useState(false)
  const chars = [...text]

  const handleClick = useCallback(() => {
    if (!melting) setMelting(true)
  }, [melting])

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        cursor: melting ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'inline-flex',
        flexWrap: 'wrap',
        fontFamily: 'var(--font-serif)',
        color: 'var(--color-foreground)',
      }}
    >
      {chars.map((char, i) => {
        const isSpace = char === ' '
        const meltDrop = randomBetween(18, 32)
        const duration = randomBetween(900, 1300)
        const delay = i * randomBetween(50, 90)

        const animStyle: CSSProperties =
          melting && !isSpace
            ? {
                '--melt-drop': `${meltDrop}px`,
                animationName: 'charMelt',
                animationDuration: `${duration}ms`,
                animationDelay: `${delay}ms`,
                animationTimingFunction: 'ease-in',
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
