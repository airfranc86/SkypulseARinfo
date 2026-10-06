/**
 * LayerGlyph — the four-step staircase of "Estratos": the lit step marks the layer of a tool
 * (0 = ground, at the bottom and widest; 3 = space, at the top and narrowest), so the layer reads
 * without relying on color. Decorative: always aria-hidden, the label names the tool.
 *
 * Step colors come from CSS custom properties set by the context (`.layer-pill`, `.tool-card__tag`):
 * `--glyph-lit` for the lit step and `--glyph-dim` for the others.
 */
import type { LayerLevel } from '@/lib/toolRegistry'

/** Steps from the top (space) down to the ground: width in px, as in the approved mockup. */
const STEPS: readonly { level: LayerLevel; width: number }[] = [
  { level: 3, width: 5 },
  { level: 2, width: 8 },
  { level: 1, width: 10 },
  { level: 0, width: 12 },
]

const STEP_HEIGHT = 2.5
const STEP_GAP = 2
const WIDTH = 12
const HEIGHT = STEPS.length * STEP_HEIGHT + (STEPS.length - 1) * STEP_GAP

export function LayerGlyph({ level }: { level: LayerLevel }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      className="layer-glyph"
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
    >
      {STEPS.map((step, i) => (
        <rect
          key={step.level}
          className={step.level === level ? 'layer-glyph__step layer-glyph__step--lit' : 'layer-glyph__step'}
          x={(WIDTH - step.width) / 2}
          y={i * (STEP_HEIGHT + STEP_GAP)}
          width={step.width}
          height={STEP_HEIGHT}
          rx={1}
        />
      ))}
    </svg>
  )
}
