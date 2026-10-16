/**
 * Background map for `/mapa`: CARTO's dark raster tiles, served from one host with a free API key.
 *
 * The key is public by design (a tile key is visible in every request the browser makes), so it lives in
 * a `VITE_` variable. Without it there is no background and the page shows the theme's plain colour:
 * never an error and no tile request (CARTO answers a watermark tile when the key is missing).
 * Pure module: the environment comes in as a parameter, like `lib/alertas/config.ts`.
 */

export const VARIABLE_CLAVE_CARTO = 'VITE_CARTO_API_KEY'

const HOST_TILES = 'https://basemaps.cartocdn.com'

export interface UrlsDelFondo {
  /** Dark tiles without labels, drawn under the isobars. */
  base: string
  /** The labels (cities, countries) on their own layer, drawn over the isobars. */
  etiquetas: string
}

/** The key from the build environment, trimmed; null when absent, blank or not text. Never throws. */
export function leerClaveCarto(env: Record<string, unknown> | undefined): string | null {
  const valor = typeof env === 'object' && env !== null ? env[VARIABLE_CLAVE_CARTO] : null
  const clave = typeof valor === 'string' ? valor.trim() : ''
  return clave === '' ? null : clave
}

/** Leaflet tile templates for the two layers, or null without a key (then no tile is requested). */
export function urlsDelFondo(clave: string | null): UrlsDelFondo | null {
  const limpia = clave?.trim() ?? ''
  if (limpia === '') return null
  let codificada: string
  try {
    codificada = encodeURIComponent(limpia)
  } catch {
    return null // a lone surrogate cannot be encoded: a key like that is not a real key
  }
  const sufijo = `/{z}/{x}/{y}.png?key=${codificada}`
  return {
    base: `${HOST_TILES}/dark_nolabels${sufijo}`,
    etiquetas: `${HOST_TILES}/dark_only_labels${sufijo}`,
  }
}
