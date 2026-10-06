import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { FadeContent } from '@/components/animated/FadeContent'
import { NowCard } from '@/components/landing/NowCard'
import { DecisionShortcuts } from '@/components/landing/DecisionShortcuts'
import type { LocationState } from '@/hooks/useLocation'
import { LayerGlyph } from '@/components/ui/LayerGlyph'
import { CARD_ALPHA, layerCssVars } from '@/lib/navContrast'
import { GROUP_HEADING, LAYERS, LAYER_INK, TOOL_FAMILIES, type Tool, type ToolFamily } from '@/lib/toolRegistry'

interface LandingProps {
  location: LocationState | null
  /** The city on screen is the Buenos Aires fallback (no saved city, location denied or unavailable). */
  isFallback: boolean
}

export function Landing({ location, isFallback }: LandingProps) {
  return (
    <div className="relative pb-8">
      {/* "Now" first (FRA-333, direction A): the city's weather and the everyday decisions.
          Outside FadeContent so it shows at once and the skeleton never fades in. */}
      <div className="relative">
        <NowCard location={location} isFallback={isFallback} />
        <DecisionShortcuts />
      </div>

      <FadeContent>
        {/* Hero */}
        <div className="mt-12 mb-10 text-center">
          <h1
            className="text-4xl sm:text-5xl font-semibold tracking-tight mb-3"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Sky<span style={{ color: 'var(--color-primary)' }}>Pulse</span>
          </h1>

          <p
            className="text-base sm:text-lg font-medium mb-3"
            style={{ color: 'var(--color-foreground)' }}
          >
            Meteorología que se entiende y se usa.
          </p>

          <p
            className="text-sm sm:text-base max-w-md mx-auto leading-relaxed"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            Convierte datos del cielo en respuestas concretas para el día a día.
            Sin tecnicismos, sin ambigüedad.
          </p>
        </div>

        {/* Tool catalog, one group per family, with the same colors as the menu */}
        <div className="flex flex-col gap-10">
          {TOOL_FAMILIES.map(({ family, tools }) => (
            <ToolGroup key={family.id} family={family} tools={tools} />
          ))}
        </div>
      </FadeContent>
    </div>
  )
}

/** Four cards fill a desktop row; three or five go three per row. */
const gridColumns = (count: number) =>
  count === 4 ? 'sm:grid-cols-2 lg:grid-cols-4' : 'sm:grid-cols-2 lg:grid-cols-3'

function ToolGroup({ family, tools }: { family: ToolFamily; tools: readonly Tool[] }) {
  const headingId = `grupo-${family.id}`
  return (
    <section aria-labelledby={headingId}>
      {/* Neutral heading: a group can mix legacy colors and "Estratos" layers. */}
      <h2
        id={headingId}
        className="mb-3 text-xs font-medium tracking-widest uppercase"
        style={{ color: `${GROUP_HEADING.color}${GROUP_HEADING.alpha}` }}
      >
        {family.title}
      </h2>
      <div className={`grid grid-cols-1 gap-3 sm:gap-4 ${gridColumns(tools.length)}`}>
        {tools.map((tool) => <ToolCard key={tool.path} tool={tool} />)}
      </div>
    </section>
  )
}

/** Altimeter segments from the top (space) down to the ground. */
const ALTIMETER_LEVELS = [3, 2, 1, 0] as const

/**
 * Card colors travel as custom properties; `.tool-card` in index.css applies them (hover and focus
 * included). A layer card ("Estratos") adds the altimeter strip on its left edge, with its layer lit,
 * and a tag naming the layer.
 */
function ToolCard({ tool }: { tool: Tool }) {
  const { path, Icon, title, description, colors } = tool
  const { accent } = colors
  const layer = tool.look === 'layer' ? LAYERS[tool.layer] : null
  const style = {
    ...(layer ? layerCssVars(colors, LAYER_INK) : {}),
    '--tool-border': `${accent}${CARD_ALPHA.border.idle}`,
    '--tool-border-active': `${accent}${CARD_ALPHA.border.active}`,
    '--tool-tint-active': `${accent}${CARD_ALPHA.tint.active}`,
  } as CSSProperties
  return (
    <Link
      to={path}
      className={`tool-card flex gap-4 rounded-xl p-5 sm:flex-col sm:gap-3.5${layer ? ' tool-card--layer' : ''}`}
      style={style}
    >
      {layer && (
        <span aria-hidden="true" className="tool-card__altimeter">
          {ALTIMETER_LEVELS.map((level) => (
            <span key={level} className={level === layer.level ? 'tool-card__segment tool-card__segment--lit' : 'tool-card__segment'} />
          ))}
        </span>
      )}
      <div
        className="size-10 rounded-[10px] flex items-center justify-center shrink-0"
        style={{ background: `${accent}${CARD_ALPHA.iconTile}`, color: accent }}
      >
        <Icon size={20} aria-hidden="true" />
      </div>
      <div className="min-w-0">
        {layer && (
          <span className="tool-card__tag">
            <LayerGlyph level={layer.level} />
            {layer.name}
          </span>
        )}
        <h3 className="font-semibold mb-1" style={{ color: 'var(--color-foreground)' }}>
          {title}
        </h3>
        <p className="text-sm leading-snug" style={{ color: 'var(--color-muted-foreground)' }}>
          {description}
        </p>
      </div>
    </Link>
  )
}
