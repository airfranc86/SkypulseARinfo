import type { WeatherIconCode } from './weatherIconCodes.ts'

/**
 * Icons for the visibility-reducing phenomena reported in METAR and TAF present weather.
 *
 * In Argentina "neblina" and "bruma" are the same thing (BR, water droplets, 1 to 5 km), so BR uses
 * `mist`; HZ is calima or dry haze; FG keeps the neutral `fog`. Any other code has no icon here:
 * nothing is invented. Pure module (relative imports only) so `node --test` can load it.
 */
const PHENOMENON_ICONS: Readonly<Record<string, WeatherIconCode>> = {
  BR: 'mist',
  FG: 'fog',
  HZ: 'haze',
  FU: 'smoke',
  DU: 'dust',
}

/** Qualifiers that precede the phenomenon in a token (MI, BC, FZ, BL...); they never have an icon. */
const DESCRIPTORS: ReadonlySet<string> = new Set(['TS', 'SH', 'FZ', 'MI', 'BC', 'PR', 'DR', 'BL'])

/** Icon of one two-letter present-weather code, or null when it has none. */
export function phenomenonIcon(code: string): WeatherIconCode | null {
  return Object.hasOwn(PHENOMENON_ICONS, code) ? PHENOMENON_ICONS[code] : null
}

function iconsForSingleToken(token: string): WeatherIconCode[] {
  const rest = token.toUpperCase().replace(/^[+-]/, '').replace(/^VC/, '')
  if (rest.length === 0 || rest.length % 2 !== 0 || !/^[A-Z]+$/.test(rest)) return []
  const pairs = rest.match(/../g) ?? []
  return pairs.flatMap((pair) => {
    if (DESCRIPTORS.has(pair)) return []
    const icon = phenomenonIcon(pair)
    return icon ? [icon] : []
  })
}

/**
 * Icons to show for a present-weather token such as `BR`, `-BR`, `BCFG`, `VCFG` or `FZFG`.
 * Intensity (+, -) and vicinity (VC) prefixes and descriptors are skipped. A token that mixes
 * several phenomena (`BRHZ`, or whitespace-separated `RA BR`) returns the icons that exist, in order
 * and without repeats. A malformed token (odd length, non-letters) returns no icons.
 */
export function phenomenonIconsForToken(token: string): WeatherIconCode[] {
  const icons = token.trim().split(/\s+/).flatMap(iconsForSingleToken)
  return [...new Set(icons)]
}
