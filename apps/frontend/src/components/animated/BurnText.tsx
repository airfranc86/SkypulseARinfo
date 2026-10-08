import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'
import { ESPACIO_STYLE, PALABRA_STYLE, agruparPorPalabra } from '@/lib/palabrasAnimadas'

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
      {/* Cada palabra es un único ítem flex con nowrap: el salto de línea solo cae entre palabras.
          agruparPorPalabra separa por code points (Unicode-safe). */}
      {agruparPorPalabra(text).map(segmento => {
        if (segmento.tipo === 'espacio') {
          return <span key={`s${segmento.indice}`} style={ESPACIO_STYLE}>{' '}</span>
        }
        return (
          <span key={`w${segmento.letras[0].indice}`} style={PALABRA_STYLE}>
            {segmento.letras.map(({ char, indice }) => {
              const charLean = randomBetween(-15, 15)
              const charRise = randomBetween(28, 52)
              const duration = randomBetween(750, 1150)
              // left-to-right stagger — fire spreads along the word
              const delay = indice * randomBetween(45, 75)

              const animStyle: CSSProperties = burning
                ? ({
                    '--char-lean': `${charLean}deg`,
                    '--char-rise': `-${charRise}px`,
                    animationName: 'charBurn',
                    animationDuration: `${duration}ms`,
                    animationDelay: `${delay}ms`,
                    animationTimingFunction: 'ease-in',
                    animationFillMode: 'forwards',
                  } as CSSProperties)
                : {}

              return (
                <span key={indice} style={{ display: 'inline-block', ...animStyle }}>
                  {char}
                </span>
              )
            })}
          </span>
        )
      })}
    </div>
  )
}
