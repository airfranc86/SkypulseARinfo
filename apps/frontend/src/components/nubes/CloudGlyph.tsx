import type { CSSProperties, ReactNode } from 'react'
import type { CloudId } from '@/data/clouds'

/**
 * Small monochrome cloud drawings for the altitude diagram (40 × 24, stroke = currentColor).
 * They are decoration: the cloud name is always written next to them, so meaning never
 * depends on the drawing or its colour.
 */

const SCALE_DOTS: ReactNode = [8, 13, 18].flatMap((y, row) =>
  [0, 1, 2, 3, 4].map(i => {
    const x = 6 + (row % 2) * 3 + i * 6
    return <circle key={`${row}-${i}`} cx={x} cy={y} r="1.5" />
  }),
)

const GLYPHS: Record<CloudId, ReactNode> = {
  cirros: (
    <>
      <path d="M3 17c7-1 12-6 20-9 4-1.5 8-2 13-2" />
      <path d="M9 21c6-1 10-4 16-6 3-1 6-1.4 10-1.4" />
      <path d="M33 6c1.5-.2 2.6.4 3 1.6" />
    </>
  ),
  cirrocumulos: <g fill="currentColor" stroke="none">{SCALE_DOTS}</g>,
  cirrostratos: (
    <>
      <path d="M2 9h36M2 15h36" opacity=".45" />
      <circle cx="20" cy="12" r="8" />
      <circle cx="20" cy="12" r="2" fill="currentColor" stroke="none" />
    </>
  ),
  altocumulos: (
    <>
      <path d="M3 11q3-5 6 0q3-5 6 0q3-5 6 0q3-5 6 0q3-5 6 0" />
      <path d="M6 19q3-5 6 0q3-5 6 0q3-5 6 0q3-5 6 0" />
    </>
  ),
  lenticular: (
    <>
      <ellipse cx="20" cy="8" rx="15" ry="3.6" />
      <path d="M2 22l9-8 6 5 7-8 14 11" opacity=".55" />
    </>
  ),
  altostratos: (
    <>
      <rect x="2" y="7" width="36" height="9" rx="4.5" fill="currentColor" fillOpacity=".28" />
      <circle cx="27" cy="11.5" r="3" opacity=".6" />
    </>
  ),
  estratocumulos: (
    <>
      <path d="M2 14a4 4 0 0 1 4-4h5a4 4 0 0 1 0 8H6a4 4 0 0 1-4-4z" />
      <path d="M15 13a4 4 0 0 1 4-4h6a4 4 0 0 1 0 8h-6a4 4 0 0 1-4-4z" />
      <path d="M29 15a3.5 3.5 0 0 1 3.5-3.5h2a3.5 3.5 0 0 1 0 7h-2A3.5 3.5 0 0 1 29 15z" />
    </>
  ),
  nimboestrato: (
    <>
      <rect x="2" y="3" width="36" height="9" rx="3" fill="currentColor" fillOpacity=".5" />
      <path d="M8 15l-2 6M15 15l-2 6M22 15l-2 6M29 15l-2 6M36 15l-2 6" opacity=".7" />
    </>
  ),
  estrato: (
    <>
      <rect x="1" y="9" width="38" height="6" rx="3" fill="currentColor" fillOpacity=".3" />
      <path d="M10 19v1M20 19v1M30 19v1" />
    </>
  ),
  cumulo: <path d="M7 19h26a5 5 0 0 0-2.5-9.4A7.5 7.5 0 0 0 16.4 8 5.5 5.5 0 0 0 7 13a3 3 0 0 0 0 6z" />,
  cumulonimbo: <path d="M4 4h32l-9 5v12H13V9z" />,
  mammatus: (
    <>
      <path d="M3 5h34" />
      <path d="M5 5q3.5 9 7 0q3.5 9 7 0q3.5 9 7 0q3.5 9 7 0" />
    </>
  ),
  niebla: <path d="M3 8h22M9 12h28M3 16h30M11 20h20" opacity=".8" />,
}

export function CloudGlyph({ cloudId, className, style }: { cloudId: CloudId; className?: string; style?: CSSProperties }) {
  return (
    <svg className={className} style={style} viewBox="0 0 40 24" aria-hidden="true" focusable="false">
      {GLYPHS[cloudId]}
    </svg>
  )
}
