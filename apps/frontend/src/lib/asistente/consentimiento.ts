/**
 * The "Entendido" of the first-use notice (owner decision D6): the person is told, once, that the question goes to an
 * AI provider before the first question leaves. The answer is kept in the browser (`localStorage`) with the VERSION of
 * the notice: if its text changes, the version goes up and it is shown again.
 *
 * Pure: the storage comes in as a parameter, so `node --test` covers it. Every access is guarded: in a private window,
 * with site data blocked or in a preview, `localStorage` can throw, and the notice must still work (it is just shown
 * again on the next visit).
 */

export const CLAVE_AVISO = 'skypulse:asistente-aviso'

/** Goes up when the text of `AVISO_PRIMER_USO` changes in a way that needs a new acceptance. */
export const VERSION_AVISO = 1

/** The part of `Storage` that is used. */
export interface Almacen {
  getItem(clave: string): string | null
  setItem(clave: string, valor: string): void
}

/** True only if this version of the notice was accepted. Never throws. */
export function avisoAceptado(almacen: Almacen | null | undefined, version: number = VERSION_AVISO): boolean {
  if (!almacen) return false
  try {
    return almacen.getItem(CLAVE_AVISO) === String(version)
  } catch {
    return false
  }
}

/** Remembers the acceptance. Returns whether it could be saved (false: it will be asked again). Never throws. */
export function aceptarAviso(almacen: Almacen | null | undefined, version: number = VERSION_AVISO): boolean {
  if (!almacen) return false
  try {
    almacen.setItem(CLAVE_AVISO, String(version))
    return true
  } catch {
    return false
  }
}
