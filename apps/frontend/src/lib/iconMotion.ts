/**
 * When a Meteocons weather icon animates (FRA-342). Kept pure so it can be tested without a
 * browser: WeatherIcon only reads the preference and the visibility and applies the result.
 *
 * Each SVG with a running SMIL animation makes the browser sample its timeline, recalculate
 * style and lay it out on every frame, even when the icon is off screen or inside a collapsed
 * section. In Previsión 15 of 19 icons sit in the collapsed detail, so pausing what is not seen
 * removes most of that work without changing how the visible icons look.
 */

export type IconMotion = 'play' | 'pause' | 'freeze'

export interface IconMotionState {
  /** `prefers-reduced-motion: reduce` */
  reducedMotion: boolean
  /** The icon intersects the viewport (widened by ICON_VIEW_MARGIN) and no ancestor clips it. */
  inView: boolean
}

/**
 * - `freeze`: reduced motion. Jump to the rest frame and pause, as before, seen or not.
 * - `pause`: not seen. Stop the timeline where it is; it resumes from that frame.
 * - `play`: seen. Run the animation.
 */
export function iconMotion({ reducedMotion, inView }: IconMotionState): IconMotion {
  if (reducedMotion) return 'freeze'
  return inView ? 'play' : 'pause'
}

/** IntersectionObserver rootMargin: resume a little before the icon scrolls into view. */
export const ICON_VIEW_MARGIN = '64px'
