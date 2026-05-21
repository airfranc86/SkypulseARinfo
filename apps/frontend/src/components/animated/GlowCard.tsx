import { useRef, useState, type ReactNode, type CSSProperties } from 'react'

interface GlowCardProps {
  children: ReactNode
  glowColor?: string
  borderRadius?: number
  /** Diameter of the spotlight in px */
  glowSize?: number
  className?: string
  style?: CSSProperties
}

/**
 * React Bits–style GlowCard.
 * A radial gradient spotlight follows the cursor inside the card,
 * with a matching border highlight on hover.
 */
export function GlowCard({
  children,
  glowColor = '#c8a84b',
  borderRadius = 12,
  glowSize = 220,
  className,
  style,
}: GlowCardProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return
    const rect = cardRef.current.getBoundingClientRect()
    setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top })
  }

  const handleMouseLeave = () => setPos(null)

  return (
    <div
      ref={cardRef}
      className={className}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ position: 'relative', borderRadius, overflow: 'hidden', ...style }}
    >
      {/* Spotlight glow overlay */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius,
          pointerEvents: 'none',
          zIndex: 1,
          opacity: pos ? 1 : 0,
          transition: 'opacity 0.25s ease',
          background: pos
            ? `radial-gradient(${glowSize}px circle at ${pos.x}px ${pos.y}px, ${glowColor}22, transparent 70%)`
            : 'none',
        }}
      />

      {/* Ambient border glow — always visible at low opacity, brighter on hover */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          borderRadius,
          pointerEvents: 'none',
          zIndex: 2,
          border: `1px solid ${glowColor}${pos ? '70' : '30'}`,
          boxShadow: pos
            ? `0 0 12px 1px ${glowColor}25, inset 0 0 8px 0px ${glowColor}10`
            : `0 0 0 0 transparent`,
          transition: 'border-color 0.25s ease, box-shadow 0.25s ease',
        }}
      />

      {/* Content — above overlays */}
      <div style={{ position: 'relative', zIndex: 3 }}>
        {children}
      </div>
    </div>
  )
}
