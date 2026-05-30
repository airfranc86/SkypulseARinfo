import { useState, useCallback, type ReactElement, type CSSProperties } from 'react'

interface ScanTextProps {
  text: string
  fontSize?: string
  className?: string
}

export function ScanText({ text, fontSize = '1rem', className = '' }: ScanTextProps): ReactElement {
  const [scanning, setScanning] = useState(false)
  const chars = [...text]

  const handleClick = useCallback(() => {
    if (!scanning) setScanning(true)
  }, [scanning])

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
      {chars.map((char, i) => {
        const isSpace = char === ' '
        // strictly sequential L→R — radar sweep
        const delay = i * 80

        const animStyle: CSSProperties =
          scanning && !isSpace
            ? {
                '--scan-final-color': 'var(--color-foreground)',
                animationName: 'charScan',
                animationDuration: '600ms',
                animationDelay: `${delay}ms`,
                animationTimingFunction: 'ease-out',
                // 'both' → chars go to opacity:0 immediately on click (0% keyframe), then reveal
                animationFillMode: 'both',
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
