import { useEffect, useId, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { cumulonimbusShape, type CbBox, type GridRows } from '@/lib/cloudSky'

/*
 * The Cb tower: a subgrid that covers the strip lanes and the tower lane, with the silhouette
 * drawn behind the mammatus and Cb buttons. The silhouette is computed by `cumulonimbusShape`
 * from the real size of the box (measured with zero-size markers on the grid lines), so it is
 * never stretched. In the list layout (narrow screens, large text) only the buttons show.
 */

interface CumulonimbusTowerProps {
  /** Rows of the whole tower in the diagram grid. */
  rows: GridRows
  /** Grid lines (diagram numbering) the drawing needs. */
  anvilBottomLine: number
  wideBottomLine: number
  baseLine: number
  children: ReactNode
}

const toSubgridLine = (line: number, rows: GridRows) => line - rows.start + 1

function sameBox(a: CbBox | null, b: CbBox | null): boolean {
  if (a === null || b === null) return a === b
  return (Object.keys(a) as Array<keyof CbBox>).every(k => Math.abs(a[k] - b[k]) < 0.5)
}

function measure(el: HTMLElement): CbBox | null {
  if (getComputedStyle(el).display !== 'grid') return null
  const mark = (name: string) => el.querySelector<HTMLElement>(`[data-cb-mark="${name}"]`)
  const lane2 = mark('lane2')
  const tower = mark('tower')
  const anvil = mark('anvil')
  const wide = mark('wide')
  const base = mark('base')
  if (!lane2 || !tower || !anvil || !wide || !base) return null
  return {
    width: el.clientWidth,
    lane2X: lane2.offsetLeft,
    towerX: tower.offsetLeft,
    anvilBottomY: anvil.offsetTop,
    wideBottomY: wide.offsetTop,
    baseY: base.offsetTop,
    groundY: el.clientHeight,
  }
}

/** Box of the drawing, re-measured whenever the tower changes size (rows follow their content). */
function useCbBox(ref: RefObject<HTMLDivElement | null>): CbBox | null {
  const [box, setBox] = useState<CbBox | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    // ResizeObserver also reports the first size right after observe().
    const observer = new ResizeObserver(() => {
      const next = measure(el)
      setBox(prev => (sameBox(prev, next) ? prev : next))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  return box
}

export function CumulonimbusTower({ rows, anvilBottomLine, wideBottomLine, baseLine, children }: CumulonimbusTowerProps) {
  const ref = useRef<HTMLDivElement>(null)
  const gradientId = useId()
  const box = useCbBox(ref)
  const shape = useMemo(() => (box ? cumulonimbusShape(box) : null), [box])

  return (
    <div
      ref={ref}
      role="group"
      aria-label="Torre del cumulonimbo, hasta 15 km"
      className="sky-tower"
      style={{ gridRow: `${rows.start} / ${rows.end}` }}
    >
      <i className="sky-cb__mark" data-cb-mark="lane2" style={{ gridColumn: 2, gridRow: 1 }} aria-hidden="true" />
      <i className="sky-cb__mark" data-cb-mark="tower" style={{ gridColumn: 3, gridRow: 1 }} aria-hidden="true" />
      <i className="sky-cb__mark" data-cb-mark="anvil" style={{ gridColumn: 3, gridRow: toSubgridLine(anvilBottomLine, rows) }} aria-hidden="true" />
      <i className="sky-cb__mark" data-cb-mark="wide" style={{ gridColumn: 3, gridRow: toSubgridLine(wideBottomLine, rows) }} aria-hidden="true" />
      <i className="sky-cb__mark" data-cb-mark="base" style={{ gridColumn: 3, gridRow: toSubgridLine(baseLine, rows) }} aria-hidden="true" />

      {box && shape && (
        <svg
          className="sky-cb"
          viewBox={`0 0 ${box.width} ${box.groundY}`}
          preserveAspectRatio="none"
          aria-hidden="true"
          focusable="false"
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#ff6b6b" stopOpacity="0.2" />
              <stop offset="0.5" stopColor="#ff6b6b" stopOpacity="0.1" />
              <stop offset="1" stopColor="#0a1220" stopOpacity="0.92" />
            </linearGradient>
          </defs>
          <g className="sky-cb__rain">
            {shape.rain.map(l => (
              <line key={`${l.x1}-${l.y1}`} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />
            ))}
          </g>
          <path className="sky-cb__body" d={shape.outline} fill={`url(#${gradientId})`} />
          <path className="sky-cb__texture" d={shape.texture} />
          <path className="sky-cb__base" d={shape.baseBand} />
        </svg>
      )}

      {children}
    </div>
  )
}
