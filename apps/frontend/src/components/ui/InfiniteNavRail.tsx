/**
 * InfiniteNavRail — two-row marquee nav.
 *
 * Row 1 (tools) scrolls left ←, Row 2 (catalog) scrolls right →.
 * Both rows pause on hover / focus-within so users can click comfortably.
 * Items are duplicated in the DOM for a seamless CSS loop; React Router NavLink
 * applies the active style to all copies automatically.
 *
 * Zero extra dependencies — pure CSS @keyframes nav-marquee (index.css).
 */
import type { ReactNode, CSSProperties } from 'react'
import { NavLink } from 'react-router-dom'

export interface NavRailItem {
  to: string
  label: string
  emoji: string
  color: string
  badge?: ReactNode
}

interface MarqueeStripProps {
  items: NavRailItem[]
  reverse?: boolean
  ariaLabel: string
}

const PILL_BASE: CSSProperties = {
  padding: '8px 13px',
  borderRadius: '9999px',
  fontSize: '0.72rem',
  minHeight: '38px',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '5px',
  whiteSpace: 'nowrap',
  textDecoration: 'none',
  flexShrink: 0,
  transition: 'border-color 0.18s, background 0.18s, color 0.18s',
}

function pillStyle(color: string, isActive: boolean): CSSProperties {
  return {
    ...PILL_BASE,
    fontWeight: isActive ? 600 : 400,
    border: `1px solid ${isActive ? color : `${color}55`}`,
    background: isActive ? `${color}18` : 'transparent',
    color: isActive ? color : 'var(--color-muted-foreground)',
  }
}

function MarqueeStrip({ items, reverse = false, ariaLabel }: MarqueeStripProps) {
  // Duplicate for seamless loop
  const doubled = [...items, ...items]

  return (
    <div
      role="list"
      aria-label={ariaLabel}
      className="relative overflow-hidden"
      style={{
        // Fade edges so the loop feels infinite rather than hard-clipping
        maskImage:
          'linear-gradient(to right, transparent 0%, black 5%, black 95%, transparent 100%)',
        WebkitMaskImage:
          'linear-gradient(to right, transparent 0%, black 5%, black 95%, transparent 100%)',
      }}
    >
      <div
        className="nav-marquee-track flex gap-2 w-max py-1"
        style={{ animationDirection: reverse ? 'reverse' : 'normal' }}
      >
        {doubled.map((item, i) => (
          <NavLink
            key={`${item.to}-${i}`}
            to={item.to}
            role="listitem"
            aria-label={item.label}
            style={({ isActive }) => pillStyle(item.color, isActive)}
          >
            <span aria-hidden="true">{item.emoji}</span>
            <span style={{ position: 'relative' }}>
              {item.label}
              {item.badge}
            </span>
          </NavLink>
        ))}
      </div>
    </div>
  )
}

interface InfiniteNavRailProps {
  tools: NavRailItem[]
  catalog: NavRailItem[]
}

export function InfiniteNavRail({ tools, catalog }: InfiniteNavRailProps) {
  return (
    <nav
      aria-label="Navegación principal"
      className="max-w-5xl mx-auto px-4 pb-2 flex flex-col gap-1"
    >
      {/* Row 1 — live tools, scrolls left */}
      <MarqueeStrip items={tools} ariaLabel="Herramientas en tiempo real" />

      {/* Row 2 — catalog pages, scrolls right for visual contrast */}
      <MarqueeStrip items={catalog} reverse ariaLabel="Catálogo informativo" />
    </nav>
  )
}
