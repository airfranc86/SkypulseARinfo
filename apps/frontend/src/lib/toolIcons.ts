/**
 * Which icon each tool page uses (FRA-346). Pure module: no React and no SVG imports, so
 * `node --test` can load it. Weather phenomena use the animated Meteocons through `WeatherIcon`;
 * signals with no weather equivalent (ok, warning, time, runner) use lucide icons, chosen by
 * the page component.
 */
import type { SnowBandKey } from './cotaDeNieve.ts'
import type { WeatherIconCode } from './weatherIconCodes.ts'
import { uvCategory } from './uvScale.ts'

/** Header icon of each tool page: a Meteocon inside the 64 px `PageHeader` square. */
export const TOOL_HEADER_ICON_CODES = {
  cotaDeNieve: 'snow',
  hacerDeporte: 'partly-cloudy-day',
  incendios: 'thermometer',
} as const satisfies Record<string, WeatherIconCode>

/** Px size of the header Meteocon (it must fit inside the 64 px square). */
export const TOOL_HEADER_ICON_SIZE = 40

// ── Incendios ────────────────────────────────────────────────────────────────

/** Icon of each condition chip in Incendios, keyed by the chip label. */
export const FIRE_CONDITION_ICON_CODES = {
  'Temperatura': 'thermometer',
  'Humedad': 'humidity',
  'Viento': 'wind',
  'Precipitación': 'rain',
} as const satisfies Record<string, WeatherIconCode>

/** Meteocon for a condition chip, or null when the label has none (the page then draws a lucide fallback). */
export function fireConditionIconCode(label: string): WeatherIconCode | null {
  return Object.hasOwn(FIRE_CONDITION_ICON_CODES, label)
    ? FIRE_CONDITION_ICON_CODES[label as keyof typeof FIRE_CONDITION_ICON_CODES]
    : null
}

// ── Hacer deporte ────────────────────────────────────────────────────────────

/** Icon of each factor shown by the sport block (indicators and the storm warning). */
export const SPORT_FACTOR_ICON_CODES = {
  humidity: 'humidity',
  uv: 'uv-index',
  wind: 'wind',
  // No cold or hot icon exists: the text and the colour already tell them apart.
  cold: 'thermometer',
  heat: 'thermometer',
  rain: 'rain',
  storm: 'thunderstorms',
} as const satisfies Record<string, WeatherIconCode>

export type SportFactor = keyof typeof SPORT_FACTOR_ICON_CODES

/** Icon of the "Sol" chip: night, strong UV, direct sun, or moderate sun. The UV is classified
    like the chip text (`uvCategory`, on the rounded number), so icon and text never disagree. */
export function sunIconCode(isDay: boolean, uvIndex: number | null): WeatherIconCode {
  if (!isDay) return 'clear-night'
  const level = uvCategory(uvIndex)?.level
  if (level === undefined || level === 'bajo') return 'partly-cloudy-day'
  if (level === 'moderado') return 'clear-day'
  return 'uv-index'
}

// ── Cota de nieve ────────────────────────────────────────────────────────────

/** Status icon of the snow-level card: always a Meteocon (no verdict glyphs such as a check or a warning). */
export type SnowStatusIcon = { kind: 'weather'; code: WeatherIconCode }

/**
 * Icon of the snow-level card: one neutral thermometer for every band. The snow line is a height,
 * so the icon must not claim a phenomenon (rain, snow) for the current state.
 */
export const SNOW_STATUS_ICONS = {
  veryHigh: { kind: 'weather', code: 'thermometer' },
  high: { kind: 'weather', code: 'thermometer' },
  medium: { kind: 'weather', code: 'thermometer' },
  low: { kind: 'weather', code: 'thermometer' },
} as const satisfies Record<SnowBandKey, SnowStatusIcon>
