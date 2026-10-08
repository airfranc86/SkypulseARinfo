/**
 * Glow tint per phenomenon family, using the project's brand tokens, not generic amber/indigo.
 *
 * Precipitation (rain/drizzle/snow/sleet/hail/thunderstorm) is checked first, day or night: the
 * Meteocons drop gradient (#0a5ad4-ish blue) reads low-contrast against the app's dark navy
 * background at small sizes, so brightness and saturation make the drops visible and not just a glow
 * around the cloud. Checking "night" first used to strip that boost from every night variant of rain,
 * snow, hail and storms. Then the sun (gold) and last the night and the moon (lavender).
 *
 * Pure module (no React, no SVG imports) so tests can import it.
 */
const PRECIPITATION_WORDS = ['rain', 'drizzle', 'snow', 'sleet', 'hail', 'thunderstorm'] as const

const PRECIPITATION_GLOW = 'brightness(1.35) saturate(1.6) drop-shadow(0 0 6px rgba(90,170,216,0.45))' // --color-info (celeste), gotas con más punch
const SUN_GLOW = 'drop-shadow(0 0 8px rgba(200,168,75,0.4))' // --color-primary (dorado)
const NIGHT_GLOW = 'drop-shadow(0 0 6px rgba(168,180,234,0.35))' // lavanda suave, nocturno

export function glowFilter(code: string): string | undefined {
  if (PRECIPITATION_WORDS.some((word) => code.includes(word))) return PRECIPITATION_GLOW
  if (code.includes('clear-day') || code.startsWith('partly-cloudy-day')) return SUN_GLOW
  if (code.includes('night') || code.startsWith('moon-')) return NIGHT_GLOW
  return undefined
}
