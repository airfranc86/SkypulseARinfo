import { type ReactElement } from 'react'
import { cn } from '@/lib/utils'

interface DitherProps {
  className?: string
  opacity?: number
}

export function Dither({ className, opacity = 0.03 }: DitherProps): ReactElement {
  return (
    <div
      className={cn('pointer-events-none fixed inset-0 z-0', className)}
      style={{ opacity }}
      aria-hidden="true"
    >
      <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <filter id="dither-noise">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.65"
            numOctaves={3}
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#dither-noise)" />
      </svg>
    </div>
  )
}
