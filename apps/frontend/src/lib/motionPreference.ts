/**
 * Motion and placement decisions for the app shell, kept pure so they can be tested
 * without a browser (the components only read the preferences and call these).
 */

/** Viewport width from which the decorative Threads background is allowed (Tailwind `lg`). */
export const DESKTOP_MEDIA_QUERY = '(min-width: 1024px)'

export interface MotionPreferences {
  /** `prefers-reduced-motion: reduce` */
  reducedMotion: boolean
  /** `DESKTOP_MEDIA_QUERY` matches */
  isDesktop: boolean
}

/** The nav marquee drifts on its own only when the user has not asked for less motion. */
export function shouldAutoScroll({ reducedMotion }: Pick<MotionPreferences, 'reducedMotion'>): boolean {
  return !reducedMotion
}

/** Threads is a full-screen WebGL canvas: desktop only, and never with reduced motion. */
export function shouldShowThreads({ reducedMotion, isDesktop }: MotionPreferences): boolean {
  return isDesktop && !reducedMotion
}

export interface RevealInput {
  /** Current translateX of the marquee track (<= 0). */
  position: number
  /** Distance from the track's left edge to the item, ignoring the translation. */
  itemLeft: number
  itemWidth: number
  viewportWidth: number
  /** Width of the faded edge on each side: the item must sit clear of it. */
  inset: number
  /** Furthest the track can go left (<= 0): viewport minus track width. */
  minPosition: number
}

/**
 * Where to put the marquee track so a keyboard-focused item is fully visible.
 * Items already clear of the faded edges leave the track alone; an item that does not
 * fit between the edges keeps its left side in view.
 */
export function revealPosition(input: RevealInput): number {
  const { position, itemLeft, itemWidth, viewportWidth, inset, minPosition } = input
  const left = itemLeft + position
  const right = left + itemWidth
  const alignLeft = inset - itemLeft
  let next = position
  if (left < inset) next = alignLeft
  else if (right > viewportWidth - inset) next = Math.max(viewportWidth - inset - itemLeft - itemWidth, alignLeft)
  return Math.min(0, Math.max(minPosition, next))
}
