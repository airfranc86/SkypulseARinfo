/**
 * Where the pressure-map files are served from: the project's GitHub Pages site, which the scheduled
 * workflow (`.github/workflows/isobaras.yml`) redeploys with every new model cycle. Pure module.
 *
 * The origin and path must match the `connect-src` entry in `vercel.json` (a test checks it).
 */

/** Base URL of the published files, without a trailing slash. */
export const ISOBARAS_BASE_URL = 'https://airfranc86.github.io/SkypulseARinfo'

// The same shape the manifest validator (`formato.ts`) accepts for an hour file name.
const ARCHIVO_DE_HORA = /^isobaras_f[0-9]{3}\.json$/

/** URL of `manifest.json`, the entry point that lists the cycle and its hours. */
export function urlManifestIsobaras(): string {
  return `${ISOBARAS_BASE_URL}/manifest.json`
}

/** URL of one hour file by the name the manifest gives it. Rejects anything else (paths, other hosts). */
export function urlDeArchivoIsobaras(nombre: string): string {
  if (!ARCHIVO_DE_HORA.test(nombre)) {
    throw new Error(`no es un archivo de hora de las isobaras: ${JSON.stringify(nombre)}`)
  }
  return `${ISOBARAS_BASE_URL}/${nombre}`
}
