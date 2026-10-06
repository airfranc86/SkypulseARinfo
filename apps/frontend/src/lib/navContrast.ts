/**
 * Colors of the navigation pills, plus the WCAG 2.x contrast math that keeps them readable.
 * The palette lives only here; `tests/navContrast.test.ts` fails if any label drops under AA.
 */

/** WCAG AA for normal-size text. */
export const MIN_TEXT_CONTRAST = 4.5

/** Hex alpha of the pill tint over the page surface (the component and the contrast check share it). */
export const PILL_TINT_ALPHA = { idle: '0d', active: '18' } as const

export type PillState = keyof typeof PILL_TINT_ALPHA

export interface PillColors {
  /** Brand tone of the destination: icon, border, tint and the label of the active pill. */
  accent: string
  /** Opaque label color of the idle pill. */
  label: string
}

/**
 * One entry per destination. `label` starts from how the idle pill used to look (the accent at
 * 70 % over its tint, which fell under 4.5:1 for most destinations) and, where that was under
 * 4.6:1, is lightened at the same hue and saturation until it reaches 4.6:1 on the pill: a
 * little headroom over AA. Entries marked "same look" already passed and are unchanged.
 */
export const NAV_PILL_COLORS = {
  '/prevision': { accent: '#c8a84b', label: '#937e3e' },
  '/hacer-deporte': { accent: '#3fb8c4', label: '#308c98' },
  '/tender-ropa': { accent: '#3ecf7a', label: '#2e985f' }, // same look
  '/lavar-auto': { accent: '#5aaad8', label: '#4686ad' },
  '/terremotos': { accent: '#e05545', label: '#c46057' },
  '/cota-de-nieve': { accent: '#90aabb', label: '#6d8392' },
  '/volcanes': { accent: '#e05545', label: '#c46057' },
  '/incendios': { accent: '#f0a030', label: '#ae762a' }, // same look
  '/nubes': { accent: '#7ea8c4', label: '#62849d' },
  '/metar': { accent: '#8b9fc4', label: '#70809d' },
  '/altitud-de-densidad': { accent: '#8fc4a8', label: '#689080' }, // same look
  '/cizalladura': { accent: '#c4b08f', label: '#8e826e' }, // same look
  '/desastres': { accent: '#c47e5a', label: '#aa7258' },
  '/lluvias': { accent: '#7ab5c4', label: '#598795' },
  '/radar': { accent: '#9a9ac4', label: '#7c7e9d' },
  '/niebla': { accent: '#90aabb', label: '#6d8392' },
} as const satisfies Record<string, PillColors>

export type NavRoute = keyof typeof NAV_PILL_COLORS

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

/** Background the label is read on: the accent tint over the page surface. */
export function pillBackground(accent: string, surface: string, state: PillState): string {
  return blendHex(accent, surface, parseInt(PILL_TINT_ALPHA[state], 16) / 255)
}

/** Label color in each state: the lightened `label` at rest, the full accent when active. */
export function pillLabelColor(colors: PillColors, state: PillState): string {
  return state === 'idle' ? colors.label : colors.accent
}

export function pillLabelContrast(colors: PillColors, surface: string, state: PillState): number {
  return contrastRatio(pillLabelColor(colors, state), pillBackground(colors.accent, surface, state))
}
