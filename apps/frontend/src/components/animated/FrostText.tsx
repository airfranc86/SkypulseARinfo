import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'
import { ESPACIO_STYLE, PALABRA_STYLE, agruparPorPalabra } from '@/lib/palabrasAnimadas'

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
  const total = [...text].length

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
      {/* Cada palabra es un único ítem flex con nowrap: el salto de línea solo cae entre palabras. */}
      {agruparPorPalabra(text).map(segmento => {
        if (segmento.tipo === 'espacio') {
          return <span key={`s${segmento.indice}`} style={ESPACIO_STYLE}>{' '}</span>
        }
        return (
          <span key={`w${segmento.letras[0].indice}`} style={PALABRA_STYLE}>
            {segmento.letras.map(({ char, indice }) => {
              // negative → upward movement (vapor rising)
              const frostRise = -randomBetween(14, 28)
              const duration = randomBetween(1200, 1600)
              // stagger right→left — cold descends from the peaks
              const delay = (total - 1 - indice) * randomBetween(50, 80)

              const animStyle: CSSProperties = frozen
                ? ({
                    '--frost-rise': `${frostRise}px`,
                    animationName: 'charFrost',
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
