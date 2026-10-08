import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'
import { ESPACIO_STYLE, PALABRA_STYLE, agruparPorPalabra } from '@/lib/palabrasAnimadas'

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
      {/* Cada palabra es un único ítem flex con nowrap: el salto de línea solo cae entre palabras. */}
      {agruparPorPalabra(text).map(segmento => {
        if (segmento.tipo === 'espacio') {
          return <span key={`s${segmento.indice}`} style={ESPACIO_STYLE}>{' '}</span>
        }
        return (
          <span key={`w${segmento.letras[0].indice}`} style={PALABRA_STYLE}>
            {segmento.letras.map(({ char, indice }) => {
              const meltDrop = randomBetween(18, 32)
              const duration = randomBetween(900, 1300)
              const delay = indice * randomBetween(50, 90)

              const animStyle: CSSProperties = melting
                ? ({
                    '--melt-drop': `${meltDrop}px`,
                    animationName: 'charMelt',
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
