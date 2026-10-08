import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'
import { ESPACIO_STYLE, PALABRA_STYLE, agruparPorPalabra } from '@/lib/palabrasAnimadas'

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
      {/* Cada palabra es un único ítem flex con nowrap: el salto de línea solo cae entre palabras. */}
      {agruparPorPalabra(text).map(segmento => {
        if (segmento.tipo === 'espacio') {
          return <span key={`s${segmento.indice}`} style={ESPACIO_STYLE}>{' '}</span>
        }
        return (
          <span key={`w${segmento.letras[0].indice}`} style={PALABRA_STYLE}>
            {segmento.letras.map(({ char, indice }) => {
              const fogDriftX = randomBetween(6, 12) * (Math.random() < 0.5 ? 1 : -1)
              const duration = randomBetween(1100, 1600)
              // random stagger — fog has no direction
              const delay = randomBetween(0, 300)

              const animStyle: CSSProperties = fogged
                ? ({
                    '--fog-drift-x': `${fogDriftX}px`,
                    animationName: 'charFog',
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
