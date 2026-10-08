import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'
import { ESPACIO_STYLE, PALABRA_STYLE, agruparPorPalabra } from '@/lib/palabrasAnimadas'

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
      {/* Cada palabra es un único ítem flex con nowrap: el salto de línea solo cae entre palabras. */}
      {agruparPorPalabra(text).map(segmento => {
        if (segmento.tipo === 'espacio') {
          return <span key={`s${segmento.indice}`} style={ESPACIO_STYLE}>{' '}</span>
        }
        return (
          <span key={`w${segmento.letras[0].indice}`} style={PALABRA_STYLE}>
            {segmento.letras.map(({ char, indice }) => {
              // negative → upward
              const driftRise = -randomBetween(20, 45)
              const driftX = randomBetween(5, 10) * (Math.random() < 0.5 ? 1 : -1)
              const duration = randomBetween(1400, 1900)
              // random stagger — clouds drift at their own pace
              const delay = randomBetween(0, 400)

              const animStyle: CSSProperties = drifting
                ? ({
                    '--drift-rise': `${driftRise}px`,
                    '--drift-x': `${driftX}px`,
                    animationName: 'charDrift',
                    animationDuration: `${duration}ms`,
                    animationDelay: `${delay}ms`,
                    animationTimingFunction: 'ease-out',
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
