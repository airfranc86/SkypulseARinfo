/**
 * InfiniteNavRail — two-row marquee nav with drag interaction.
 *
 * Row 1 (tools) auto-scrolls left ←, Row 2 (catalog) auto-scrolls right →.
 * Users can click-and-drag each row to scroll manually.
 * A drag of >5px suppresses the NavLink click to avoid accidental navigation.
 *
 * Auto-scroll is JS-driven (requestAnimationFrame) so drag and auto-scroll
 * share the same transform — no CSS animation conflicts. It never starts with
 * `prefers-reduced-motion: reduce` (the rows can still be dragged), and it
 * pauses while a link has keyboard focus.
 *
 * Each row is a list of links. The copy that makes the loop seamless is
 * aria-hidden and out of the tab order, so every destination is announced and
 * tabbable once. Keyboard focus slides the row to bring the focused pill into view.
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
  type FocusEvent as ReactFocusEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { revealPosition, shouldAutoScroll } from '@/lib/motionPreference'
import { PILL_TINT_ALPHA, layerCssVars, pillLabelColor, type PillColors } from '@/lib/navContrast'
import { LAYERS, LAYER_INK, type LayerId } from '@/lib/toolRegistry'
import { LayerGlyph } from '@/components/ui/LayerGlyph'

export interface NavRailItem {
  to: string
  label: string
  emoji: ReactNode
  colors: PillColors
  /** "Estratos" layer of a bottom-row pill; without it the pill keeps the legacy look. */
  layer?: LayerId
  badge?: ReactNode
}

interface MarqueeStripProps {
  items: NavRailItem[]
  reverse?: boolean
  ariaLabel: string
}

const PILL_BASE: CSSProperties = {
  padding: '10px 14px',
  fontSize: '0.72rem',
  minHeight: '44px',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '5px',
  whiteSpace: 'nowrap',
  textDecoration: 'none',
  flexShrink: 0,
  transition: 'border-color 0.18s, background 0.18s, color 0.18s',
}

function pillStyle(colors: PillColors, isActive: boolean): CSSProperties {
  const state = isActive ? 'active' : 'idle'
  return {
    ...PILL_BASE,
    fontWeight: isActive ? 600 : 400,
    border: `1px solid ${isActive ? colors.accent : `${colors.accent}2a`}`,
    background: `${colors.accent}${PILL_TINT_ALPHA[state]}`,
    color: pillLabelColor(colors, state),
  }
}

/** px per frame (~60 fps) — matches the feel of the original 55 s CSS loop */
const AUTO_SCROLL_SPEED = 0.32

/** Width of the frosted-glass edge overlay on each side, in pixels */
const EDGE_BLUR_WIDTH = 72

/**
 * Build the CSS for a single edge overlay div.
 * Direction controls which side fades to transparent.
 *
 * FIX: `backdropFilter` + `maskImage` used to be layered on top of the solid
 * `background` gradient to scope the blur to the fade area. Since `mask-image`
 * applies to the WHOLE element (not just the backdrop-filter), it multiplied
 * against the background gradient's own opacity — the overlay ended up far
 * more transparent near the true edge than the gradient stops implied, so
 * pill text/emoji peeked through instead of being hidden ("Secado de ropa"
 * clipped to "orte", "METAR" clipped to "ME"). The file's own top comment
 * already says the gradient approach was chosen specifically to avoid
 * maskImage (Safari bugs) — dropping it here just matches that documented
 * intent and restores real full-opacity coverage at the edge.
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
    pointerEvents: 'none',
    zIndex: 10,
  }
}

/**
 * A bottom-row pill in the "Estratos" look. Colors and states (hover, keyboard focus, current page)
 * live in `.layer-pill` in index.css, fed by the custom properties of its layer; NavLink sets
 * `aria-current="page"` on the current page, which fills the pill with the layer color.
 */
function LayerNavPill({ item, layer, hidden }: { item: NavRailItem; layer: LayerId; hidden: boolean }) {
  return (
    <li aria-hidden={hidden ? true : undefined} className="flex shrink-0">
      <NavLink
        to={item.to}
        aria-label={item.label}
        tabIndex={hidden ? -1 : undefined}
        draggable={false}
        className="layer-pill"
        style={layerCssVars(item.colors, LAYER_INK) as CSSProperties}
      >
        <LayerGlyph level={LAYERS[layer].level} />
        <span aria-hidden="true" className="layer-pill__icon">{item.emoji}</span>
        <span style={{ position: 'relative' }}>
          {item.label}
          {item.badge}
        </span>
      </NavLink>
    </li>
  )
}

/** One destination. `hidden` marks the loop copy: invisible to assistive tech and not tabbable. */
function NavPill({ item, hidden }: { item: NavRailItem; hidden: boolean }) {
  if (item.layer) return <LayerNavPill item={item} layer={item.layer} hidden={hidden} />
  return (
    <li aria-hidden={hidden ? true : undefined} className="flex shrink-0">
      <NavLink
        to={item.to}
        aria-label={item.label}
        tabIndex={hidden ? -1 : undefined}
        draggable={false}
        className="rounded-full"
        style={({ isActive }) => pillStyle(item.colors, isActive)}
      >
        <span aria-hidden="true">{item.emoji}</span>
        <span style={{ position: 'relative' }}>
          {item.label}
          {item.badge}
        </span>
      </NavLink>
    </li>
  )
}

function MarqueeStrip({ items, reverse = false, ariaLabel }: MarqueeStripProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const trackRef = useRef<HTMLUListElement>(null)

  // JS-driven position (negative = scrolled left)
  const posRef = useRef(0)
  // Half the total track width — the wrap boundary
  const halfWidthRef = useRef(0)

  // Drag state (refs to avoid re-renders in RAF loop)
  const isDragging = useRef(false)
  const dragStartX = useRef(0)
  const dragStartPos = useRef(0)
  const totalDragDelta = useRef(0) // used to suppress NavLink click on real drags
  // A link inside the row has keyboard focus: the row holds still
  const hasKeyboardFocus = useRef(false)

  // Cursor state — only this needs a re-render
  const [cursor, setCursor] = useState<'grab' | 'grabbing'>('grab')

  const navigate = useNavigate()

  const reducedMotion = useReducedMotion()
  const autoScroll = shouldAutoScroll({ reducedMotion })

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
   * Auto-scroll loop. Not started at all with reduced motion; the effect re-runs when
   * the preference changes, so toggling it takes effect without a reload.
   * Until halfWidth has been measured (first frame after mount) ticks only reschedule,
   * so the track never starts from a broken position that could jump on the first wrap.
   */
  useEffect(() => {
    if (!autoScroll) return
    let frame = 0
    const tick = () => {
      if (halfWidthRef.current && !isDragging.current && !hasKeyboardFocus.current) {
        posRef.current += speed
        wrapPosition()
        applyTransform()
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [autoScroll, speed, wrapPosition, applyTransform])

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

  // ── Keyboard focus ────────────────────────────────────────────────────────

  /**
   * Tabbing to a pill that is out of view (or under a faded edge) slides the row to show it
   * and holds the auto-scroll. Mouse and touch focus (not :focus-visible) are left alone, so
   * tapping a pill near an edge never makes the row jump.
   * The row is moved with transform only, so any scroll the browser applied to this clipped
   * box to reveal the link is undone first.
   */
  const onFocus = useCallback(
    (e: ReactFocusEvent<HTMLDivElement>) => {
      const link = e.target
      const container = containerRef.current
      const track = trackRef.current
      if (!container || !track || !link.matches(':focus-visible')) return
      hasKeyboardFocus.current = true
      container.scrollLeft = 0
      posRef.current = revealPosition({
        position: posRef.current,
        itemLeft: link.getBoundingClientRect().left - track.getBoundingClientRect().left,
        itemWidth: link.offsetWidth,
        viewportWidth: container.clientWidth,
        inset: EDGE_BLUR_WIDTH,
        minPosition: container.clientWidth - 2 * halfWidthRef.current,
      })
      applyTransform()
    },
    [applyTransform],
  )

  const onBlur = useCallback((e: ReactFocusEvent<HTMLDivElement>) => {
    if (!e.currentTarget.contains(e.relatedTarget)) hasKeyboardFocus.current = false
  }, [])

  return (
    <div
      ref={containerRef}
      className="relative overflow-hidden"
      style={{ cursor, touchAction: 'pan-y' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
      onPointerCancel={onPointerUp}
      onClick={onContainerClick}
      onFocus={onFocus}
      onBlur={onBlur}
    >
      {/* Frosted-glass left edge — pointer-events:none so drag still works */}
      <div style={edgeOverlayStyle('left')} aria-hidden="true" />

      {/* role="list" keeps the list semantics in Safari, which drops them with list-style:none */}
      <ul
        ref={trackRef}
        role="list"
        aria-label={ariaLabel}
        className="flex gap-2 w-max py-1"
        style={{ willChange: 'transform', userSelect: 'none' }}
      >
        {items.map((item) => (
          <NavPill key={item.to} item={item} hidden={false} />
        ))}
        {/* Second copy for the seamless wrap-around loop */}
        {items.map((item) => (
          <NavPill key={`${item.to}-loop`} item={item} hidden />
        ))}
      </ul>

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
