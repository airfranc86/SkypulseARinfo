import { revealScrollDelta } from '@/lib/cloudSky'

/** Breathing room between the element and the header / window edge. */
const MARGIN_PX = 12

/** Bottom edge of the app's sticky (or fixed) header, 0 when there is none. */
function stickyHeaderBottom(): number {
  return [...document.querySelectorAll('header')]
    .filter(h => ['sticky', 'fixed'].includes(getComputedStyle(h).position))
    .reduce((max, h) => Math.max(max, h.getBoundingClientRect().bottom), 0)
}

/**
 * Scrolls the window so `el` shows below the sticky header (whose height changes with the
 * nav rows), instead of `scrollIntoView`, which would leave it under the header.
 */
export function revealBelowHeader(el: HTMLElement, { align, smooth }: { align: 'start' | 'nearest'; smooth: boolean }): void {
  const rect = el.getBoundingClientRect()
  const delta = revealScrollDelta({
    top: rect.top,
    bottom: rect.bottom,
    viewTop: stickyHeaderBottom() + MARGIN_PX,
    viewBottom: window.innerHeight - MARGIN_PX,
    align,
  })
  if (Math.abs(delta) > 1) window.scrollBy({ top: delta, behavior: smooth ? 'smooth' : 'auto' })
}
