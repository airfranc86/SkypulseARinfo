import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'
import { ESPACIO_STYLE, PALABRA_STYLE, agruparPorPalabra } from '@/lib/palabrasAnimadas'

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
      {/* Cada palabra es un único ítem flex con nowrap: el salto de línea solo cae entre palabras. */}
      {agruparPorPalabra(text).map(segmento => {
        if (segmento.tipo === 'espacio') {
          return <span key={`s${segmento.indice}`} style={ESPACIO_STYLE}>{' '}</span>
        }
        return (
          <span key={`w${segmento.letras[0].indice}`} style={PALABRA_STYLE}>
            {segmento.letras.map(({ char, indice }) => {
              const rainDrop = randomBetween(60, 100)
              const duration = randomBetween(350, 550)
              // very short stagger — rain falls almost simultaneously
              const delay = indice * randomBetween(0, 60)

              const animStyle: CSSProperties = raining
                ? ({
                    '--rain-drop': `${rainDrop}px`,
                    animationName: 'charRain',
                    animationDuration: `${duration}ms`,
                    animationDelay: `${delay}ms`,
                    animationTimingFunction: 'cubic-bezier(0.55, 0, 1, 0.45)',
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
