import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface BurnTextProps {
  text: string
  fontSize?: string
  className?: string
}

function randomBetween(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export function BurnText({ text, fontSize = '1rem', className = '' }: BurnTextProps): ReactElement {
  const [burning, setBurning] = useState(false)
  const chars = [...text]  // Unicode-safe split

  const handleClick = useCallback(() => {
    if (!burning) setBurning(true)
  }, [burning])

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        lineHeight: 1.4,
        cursor: burning ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'inline-flex',
        flexWrap: 'wrap',
        fontFamily: 'var(--font-serif)',
        color: 'var(--color-foreground)',
      }}
    >
      {chars.map((char, i) => {
        const isSpace = char === ' '
        const charLean = randomBetween(-15, 15)
        const charRise = randomBetween(28, 52)
        const duration = randomBetween(750, 1150)
        // left-to-right stagger — fire spreads along the word
        const delay = i * randomBetween(45, 75)

        const animStyle: CSSProperties = burning && !isSpace
          ? {
              '--char-lean': `${charLean}deg`,
              '--char-rise': `-${charRise}px`,
              animationName: 'charBurn',
              animationDuration: `${duration}ms`,
              animationDelay: `${delay}ms`,
              animationTimingFunction: 'ease-in',
              animationFillMode: 'forwards',
            } as CSSProperties
          : {}

        return (
          <span
            key={i}
            style={{ display: 'inline-block', ...animStyle }}
          >
            {char}
          </span>
        )
      })}
    </div>
  )
}
