/**
 * How strongly a tool color shows on the menu pills and the landing cards, plus the color math
 * (WCAG 2.x contrast, OKLab) that keeps them readable. The hex colors themselves live in
 * `toolRegistry.ts`; `tests/navContrast.test.ts` and `tests/toolRegistry.test.ts` fail if any label
 * drops under AA.
 */
import { TOOLS } from './toolRegistry.ts'

/** WCAG AA for normal-size text. */
export const MIN_TEXT_CONTRAST = 4.5

/**
 * `legacy`: the original pill (top row), exactly as on origin/main. `layer`: "Estratos" (bottom row),
 * where the color says at what height the phenomenon lives.
 */
export type PillLook = 'legacy' | 'layer'

export interface PillColors {
  /** Full tone: icon, border and tint (and the active legacy label, or the current layer pill fill). */
  accent: string
  /** Opaque label color: the darkened idle legacy label, or the light tone of a layer. */
  label: string
}

/** Colors by route, for code that looks a destination up by path. Derived from the registry. */
export const NAV_PILL_COLORS: Record<string, PillColors> = Object.fromEntries(
  TOOLS.map((tool) => [tool.path, tool.colors]),
)

export type NavRoute = string

// ── Legacy pill (top row) ────────────────────────────────────────────────────

/** Hex alpha of the legacy pill tint over the page surface (5 % at rest, 9 % active), as on origin/main. */
export const PILL_TINT_ALPHA = { idle: '0d', active: '18' } as const

/** Hex alpha of the legacy pill border at rest (16.5 %); the active pill shows the full accent. */
export const PILL_BORDER_ALPHA = '2a'

export type PillState = keyof typeof PILL_TINT_ALPHA

// ── Layer pill (bottom row, "Estratos") ──────────────────────────────────────

export type LayerPillState = 'idle' | 'hover' | 'current'

export const LAYER_STATES: readonly LayerPillState[] = ['idle', 'hover', 'current']

/**
 * Hex alphas of the layer pill: tint 13 % at rest and 22 % on hover or keyboard focus, border 34 % and
 * 85 %. The current page is filled with the full layer color. `glyph` dims the unlit steps of the
 * staircase: 40 % of the layer color on the pill, 28 % of the ink on the filled pill, 30 % on the card tag.
 */
export const LAYER_PRESENCE = {
  tint: { idle: '21', hover: '38' },
  border: { idle: '57', hover: 'd9' },
  glyph: { pill: '66', current: '47', tag: '4d' },
} as const

// ── Landing card ─────────────────────────────────────────────────────────────

/**
 * Card presence, the same for all 16 cards: border 30 % at rest and 75 % on hover and focus, a 7 % wash
 * of the color on hover and focus, the icon tile at 14 %. Layer cards add the layer tag at 16 % and the
 * altimeter strip, whose unlit segments sit at 14 %.
 */
export const CARD_ALPHA = {
  border: { idle: '4d', active: 'bf' },
  tint: { idle: '00', active: '12' },
  iconTile: '24',
  tag: '29',
  altimeter: '24',
} as const

// ── Color math ───────────────────────────────────────────────────────────────

type Rgb = readonly [number, number, number]

function parseHex(hex: string): Rgb {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) throw new Error(`Color inválido: ${hex}`)
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function toHex(rgb: Rgb): string {
  return `#${rgb.map((channel) => channel.toString(16).padStart(2, '0')).join('')}`
}

function linearChannel(channel: number): number {
  const s = channel / 255
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = parseHex(hex)
  return 0.2126 * linearChannel(r) + 0.7152 * linearChannel(g) + 0.0722 * linearChannel(b)
}

/** WCAG contrast ratio, 1 to 21, whichever color is lighter. */
export function contrastRatio(foreground: string, background: string): number {
  const a = relativeLuminance(foreground)
  const b = relativeLuminance(background)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

/** `foreground` at `alpha` (0..1) over `background`, rounded to whole channels like a browser does. */
export function blendHex(foreground: string, background: string, alpha: number): string {
  const fg = parseHex(foreground)
  const bg = parseHex(background)
  const mixed = fg.map((channel, i) => Math.round(channel * alpha + bg[i] * (1 - alpha)))
  return toHex(mixed as unknown as Rgb)
}

const alphaOf = (hexAlpha: string) => parseInt(hexAlpha, 16) / 255

// ── Legacy pill contrast ─────────────────────────────────────────────────────

/** Background the legacy label is read on: the accent tint over the page surface. */
export function pillBackground(accent: string, surface: string, state: PillState): string {
  return blendHex(accent, surface, alphaOf(PILL_TINT_ALPHA[state]))
}

/** Legacy label: the darkened `label` at rest, the full accent when active. */
export function pillLabelColor(colors: PillColors, state: PillState): string {
  return state === 'idle' ? colors.label : colors.accent
}

export function pillLabelContrast(colors: PillColors, surface: string, state: PillState): number {
  return contrastRatio(pillLabelColor(colors, state), pillBackground(colors.accent, surface, state))
}

// ── Layer pill contrast ──────────────────────────────────────────────────────

/** Background of a layer pill: the tint over the page, or the full layer color on the current page. */
export function layerPillBackground(accent: string, surface: string, state: LayerPillState): string {
  return state === 'current' ? accent : blendHex(accent, surface, alphaOf(LAYER_PRESENCE.tint[state]))
}

/** Layer label: the light tone of the layer, or the ink on the filled current pill. */
export function layerPillLabelColor(colors: PillColors, ink: string, state: LayerPillState): string {
  return state === 'current' ? ink : colors.label
}

export function layerPillContrast(colors: PillColors, ink: string, surface: string, state: LayerPillState): number {
  return contrastRatio(layerPillLabelColor(colors, ink, state), layerPillBackground(colors.accent, surface, state))
}

// ── Card contrast ────────────────────────────────────────────────────────────

/** Background the card text is read on: the card surface, washed with the color on hover and focus. */
export function cardBackground(accent: string, card: string, state: PillState): string {
  return blendHex(accent, card, alphaOf(CARD_ALPHA.tint[state]))
}

// ── OKLab: perceptual distance and hue ───────────────────────────────────────

type Lab = readonly [number, number, number]

function srgbToLinear(channel: number): number {
  const s = channel / 255
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

/** Björn Ottosson's OKLab, from an sRGB hex color. */
export function toOklab(hex: string): Lab {
  const [r, g, b] = parseHex(hex).map(srgbToLinear)
  const l = Math.cbrt(0.4122214708 * r + 0.5363015264 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

/** Euclidean OKLab distance: 0 for the same color, about 0.02 is barely noticeable. */
export function oklabDistance(a: string, b: string): number {
  const [l1, a1, b1] = toOklab(a)
  const [l2, a2, b2] = toOklab(b)
  return Math.hypot(l1 - l2, a1 - a2, b1 - b2)
}

/** OKLCH hue in degrees, 0 to 360. */
export function oklchHue(hex: string): number {
  const [, a, b] = toOklab(hex)
  return ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360
}

/**
 * CSS custom properties for a layer pill or card, in one place: the component spreads them inline and
 * `index.css` (`.layer-pill`, `.tool-card--layer`) turns them into tint, border, glyph and states.
 */
export function layerCssVars(colors: PillColors, ink: string): Record<string, string> {
  const { accent, label } = colors
  return {
    '--layer': accent,
    '--layer-label': label,
    '--layer-ink': ink,
    '--layer-tint': `${accent}${LAYER_PRESENCE.tint.idle}`,
    '--layer-tint-hover': `${accent}${LAYER_PRESENCE.tint.hover}`,
    '--layer-border': `${accent}${LAYER_PRESENCE.border.idle}`,
    '--layer-border-hover': `${accent}${LAYER_PRESENCE.border.hover}`,
    '--layer-glyph-dim': `${accent}${LAYER_PRESENCE.glyph.pill}`,
    '--layer-ink-dim': `${ink}${LAYER_PRESENCE.glyph.current}`,
    '--layer-tag': `${accent}${CARD_ALPHA.tag}`,
    '--layer-tag-dim': `${accent}${LAYER_PRESENCE.glyph.tag}`,
    '--layer-altimeter-dim': `${accent}${CARD_ALPHA.altimeter}`,
  }
}
