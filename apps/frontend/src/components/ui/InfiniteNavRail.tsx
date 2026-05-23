/**
 * InfiniteNavRail — two-row marquee nav with drag interaction.
 *
 * Row 1 (tools) auto-scrolls left ←, Row 2 (catalog) auto-scrolls right →.
 * Users can click-and-drag each row to scroll manually.
 * A drag of >5px suppresses the NavLink click to avoid accidental navigation.
 *
 * Auto-scroll is JS-driven (requestAnimationFrame) so drag and auto-scroll
 * share the same transform — no CSS animation conflicts.
 */
import {
  useRef,
  useEffect,
  useCallback,
  useState,
  type ReactNode,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
} from 'react'
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

/** px per frame (~60 fps) — matches the feel of the original 55 s CSS loop */
const AUTO_SCROLL_SPEED = 0.32

function MarqueeStrip({ items, reverse = false, ariaLabel }: MarqueeStripProps) {
  // Items are doubled for the seamless wrap-around loop
  const doubled = [...items, ...items]

  const containerRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)

  // JS-driven position (negative = scrolled left)
  const posRef = useRef(0)
  // Half the total track width — the wrap boundary
  const halfWidthRef = useRef(0)

  // Drag state (refs to avoid re-renders in RAF loop)
  const isDragging = useRef(false)
  const dragStartX = useRef(0)
  const dragStartPos = useRef(0)
  const totalDragDelta = useRef(0) // used to suppress NavLink click on real drags

  const rafRef = useRef<number>(0)

  // Cursor state — only this needs a re-render
  const [cursor, setCursor] = useState<'grab' | 'grabbing'>('grab')

  // Speed: negative = leftward (default), positive = rightward (reverse rows)
  const speed = reverse ? AUTO_SCROLL_SPEED : -AUTO_SCROLL_SPEED

  // Measure the half-width of the doubled track
  const measureHalfWidth = useCallback(() => {
    if (trackRef.current) {
      halfWidthRef.current = trackRef.current.scrollWidth / 2
    }
  }, [])

  useEffect(() => {
    measureHalfWidth()
    // Re-measure if container resizes (font scaling, layout shifts)
    const ro = new ResizeObserver(measureHalfWidth)
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [measureHalfWidth])

  const applyTransform = useCallback(() => {
    if (trackRef.current) {
      trackRef.current.style.transform = `translateX(${posRef.current}px)`
    }
  }, [])

  const wrapPosition = useCallback(() => {
    const half = halfWidthRef.current
    if (!half) return
    // Wrap so the loop feels infinite in both directions
    if (posRef.current <= -half) posRef.current += half
    else if (posRef.current > 0) posRef.current -= half
  }, [])

  const animate = useCallback(() => {
    if (!isDragging.current) {
      posRef.current += speed
      wrapPosition()
      applyTransform()
    }
    rafRef.current = requestAnimationFrame(animate)
  }, [speed, wrapPosition, applyTransform])

  useEffect(() => {
    rafRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafRef.current)
  }, [animate])

  // ── Pointer handlers ──────────────────────────────────────────────────────

  const onPointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return // left-click / touch only
    isDragging.current = true
    totalDragDelta.current = 0
    dragStartX.current = e.clientX
    dragStartPos.current = posRef.current
    containerRef.current?.setPointerCapture(e.pointerId)
    setCursor('grabbing')
  }, [])

  const onPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isDragging.current) return
    const delta = e.clientX - dragStartX.current
    totalDragDelta.current = Math.abs(delta)
    posRef.current = dragStartPos.current + delta
    wrapPosition()
    applyTransform()
  }, [wrapPosition, applyTransform])

  const onPointerUp = useCallback(() => {
    isDragging.current = false
    setCursor('grab')
  }, [])

  return (
    <div
      ref={containerRef}
      role="list"
      aria-label={ariaLabel}
      className="relative overflow-hidden"
      style={{
        cursor,
        // Fade edges so the loop feels infinite rather than hard-clipping
        maskImage:
          'linear-gradient(to right, transparent 0%, black 6%, black 94%, transparent 100%)',
        WebkitMaskImage:
          'linear-gradient(to right, transparent 0%, black 6%, black 94%, transparent 100%)',
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div
        ref={trackRef}
        className="flex gap-2 w-max py-1"
        style={{ willChange: 'transform', userSelect: 'none' }}
      >
        {doubled.map((item, i) => (
          <NavLink
            key={`${item.to}-${i}`}
            to={item.to}
            role="listitem"
            aria-label={item.label}
            draggable={false}
            style={({ isActive }) => pillStyle(item.color, isActive)}
            onClick={(e) => {
              // Suppress navigation when the user was actually dragging
              if (totalDragDelta.current > 5) {
                e.preventDefault()
              }
            }}
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
      {/* Row 1 — live tools, auto-scrolls left */}
      <MarqueeStrip items={tools} ariaLabel="Herramientas en tiempo real" />

      {/* Row 2 — catalog pages, auto-scrolls right for visual contrast */}
      <MarqueeStrip items={catalog} reverse ariaLabel="Catálogo informativo" />
    </nav>
  )
}
