/**
 * InfiniteNavRail — two-row marquee nav with drag interaction.
 *
 * Row 1 (tools) auto-scrolls left ←, Row 2 (catalog) auto-scrolls right →.
 * Users can click-and-drag each row to scroll manually.
 * A drag of >5px suppresses the NavLink click to avoid accidental navigation.
 *
 * Auto-scroll is JS-driven (requestAnimationFrame) so drag and auto-scroll
 * share the same transform — no CSS animation conflicts.
 *
 * Edge blur: two overlay divs with pointer-events:none and a gradient from
 * var(--color-background) → transparent. More compatible than maskImage
 * (Safari has bugs with maskImage + overflow:hidden).
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
import { NavLink, useNavigate } from 'react-router-dom'

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

/** Width of the frosted-glass edge overlay on each side, in pixels */
const EDGE_BLUR_WIDTH = 72

/**
 * Build the CSS for a single edge overlay div.
 * Direction controls which side fades to transparent.
 */
function edgeOverlayStyle(side: 'left' | 'right'): CSSProperties {
  const gradientDir = side === 'left' ? 'to right' : 'to left'
  return {
    position: 'absolute',
    top: 0,
    [side]: 0,
    width: EDGE_BLUR_WIDTH,
    height: '100%',
    background: `linear-gradient(${gradientDir}, var(--color-background, #000) 0%, transparent 100%)`,
    // Slight blur on the fading content — enhances the frosted-glass feel
    backdropFilter: 'blur(2px)',
    WebkitBackdropFilter: 'blur(2px)',
    // The gradient mask scopes the blur to the fade area
    maskImage: `linear-gradient(${gradientDir}, black 0%, transparent 100%)`,
    WebkitMaskImage: `linear-gradient(${gradientDir}, black 0%, transparent 100%)`,
    pointerEvents: 'none',
    zIndex: 10,
  }
}

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
  // Stable ref to the latest animate — avoids stale-closure self-reference
  const animateRef = useRef<() => void>(() => {})

  // Cursor state — only this needs a re-render
  const [cursor, setCursor] = useState<'grab' | 'grabbing'>('grab')

  const navigate = useNavigate()

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
    const ro = new ResizeObserver(measureHalfWidth)
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [measureHalfWidth])

  const applyTransform = useCallback(() => {
    if (trackRef.current) {
      trackRef.current.style.transform = `translateX(${posRef.current}px)`
    }
  }, [])

  /**
   * Normalise posRef into the [−half, 0) window so the loop is seamless.
   * Calling this after every drag move prevents visible jumps at the boundary.
   */
  const wrapPosition = useCallback(() => {
    const half = halfWidthRef.current
    if (!half) return
    if (posRef.current <= -half) posRef.current += half
    else if (posRef.current > 0) posRef.current -= half
  }, [])

  /**
   * RAF callback.
   * Guard: if halfWidth hasn't been measured yet (first frame after mount),
   * we skip the tick and retry via setTimeout so we never start from a broken
   * position that could cause a visible jump on the first wrap.
   */
  const animate = useCallback(() => {
    if (!halfWidthRef.current) {
      rafRef.current = requestAnimationFrame(animateRef.current)
      return
    }
    if (!isDragging.current) {
      posRef.current += speed
      wrapPosition()
      applyTransform()
    }
    rafRef.current = requestAnimationFrame(animateRef.current)
  }, [speed, wrapPosition, applyTransform])

  // Keep animateRef pointing to the latest version (avoids stale closure)
  animateRef.current = animate

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
    // Explicit capture on the container overrides the browser's implicit pointer
    // capture on child NavLink elements. Without this, on mobile the browser
    // captures the pointer on the NavLink that received the initial touch, so
    // pointermove/pointerup go to the NavLink and the container never sees them
    // — the drag never works and isDragging gets stuck in true.
    // Navigation is now handled by onContainerClick below (since setPointerCapture
    // causes the click event to fire on the container, not on the NavLink).
    e.currentTarget.setPointerCapture(e.pointerId)
    setCursor('grabbing')
  }, [])

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!isDragging.current) return
      const delta = e.clientX - dragStartX.current
      totalDragDelta.current = Math.abs(delta)
      posRef.current = dragStartPos.current + delta
      // Wrap during drag so releasing near a boundary never produces a jump
      wrapPosition()
      applyTransform()
    },
    [wrapPosition, applyTransform],
  )

  const onPointerUp = useCallback(() => {
    isDragging.current = false
    setCursor('grab')
  }, [])

  /**
   * With setPointerCapture, the browser fires click on the container (not on the
   * NavLink). For short taps (totalDragDelta ≤ 5 px) we synthesise navigation by
   * hit-testing the physical tap coordinates to find the underlying NavLink.
   * Keyboard navigation (Tab + Enter on a NavLink) still works natively because
   * keyboard-originated clicks are NOT pointer-captured.
   */
  const onContainerClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (totalDragDelta.current > 5) return // real drag — skip navigation
      const el = document.elementFromPoint(e.clientX, e.clientY)
      const link = el?.closest('a') as HTMLAnchorElement | null
      if (link) {
        const href = link.getAttribute('href')
        if (href) navigate(href)
      }
    },
    [navigate],
  )

  return (
    <div
      ref={containerRef}
      role="list"
      aria-label={ariaLabel}
      className="relative overflow-hidden"
      style={{ cursor, touchAction: 'pan-y' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      onPointerCancel={onPointerUp}
      onClick={onContainerClick}
    >
      {/* Frosted-glass left edge — pointer-events:none so drag still works */}
      <div style={edgeOverlayStyle('left')} aria-hidden="true" />

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
            className="rounded-full"
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

      {/* Frosted-glass right edge — pointer-events:none so drag still works */}
      <div style={edgeOverlayStyle('right')} aria-hidden="true" />
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
