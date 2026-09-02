import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface ScanTextProps {
  text: string
  fontSize?: string
  className?: string
}

export function ScanText({ text, fontSize = '1rem', className = '' }: ScanTextProps): ReactElement {
  const [scanning, setScanning] = useState(false)
  const words = text.split(' ')

  const handleClick = useCallback(() => {
    if (!scanning) setScanning(true)
  }, [scanning])

  const charStyle = (i: number): CSSProperties =>
    scanning
      ? ({
          '--scan-final-color': 'var(--color-foreground)',
          animationName: 'charScan',
          animationDuration: '600ms',
          // strictly sequential L→R — radar sweep
          animationDelay: `${i * 80}ms`,
          animationTimingFunction: 'ease-out',
          // 'both' → chars go to opacity:0 immediately on click (0% keyframe), then reveal
          animationFillMode: 'both',
        } as CSSProperties)
      : {}

  // Cada palabra es un único flex item con white-space:nowrap — el wrap del
  // contenedor solo puede caer entre palabras, nunca a mitad de una (antes cada
  // letra era su propio flex item suelto, así que el navegador cortaba
  // palabras largas donde fuera con tal de llenar el ancho de línea).
  let i = 0
  const nodes: ReactElement[] = []
  words.forEach((word, wi) => {
    nodes.push(
      <span key={`w${wi}`} style={{ display: 'inline-block', whiteSpace: 'nowrap' }}>
        {[...word].map(char => {
          const idx = i++
          return (
            <span key={idx} style={{ display: 'inline-block', ...charStyle(idx) }}>
              {char}
            </span>
          )
        })}
      </span>
    )
    if (wi < words.length - 1) {
      i++ // el espacio no anima, pero conserva el mismo paso de delay que antes
      nodes.push(
        <span key={`s${wi}`} style={{ display: 'inline-block', minWidth: '0.3em' }}>
          &nbsp;
        </span>
      )
    }
  })

  return (
    <div
      className={className}
      onClick={handleClick}
      style={{
        fontSize,
        cursor: scanning ? 'default' : 'pointer',
        userSelect: 'none',
        display: 'inline-flex',
        flexWrap: 'wrap',
        fontFamily: 'var(--font-serif)',
        color: 'var(--color-foreground)',
      }}
    >
      {nodes}
    </div>
  )
}
