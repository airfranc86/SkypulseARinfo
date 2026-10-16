/**
 * Loading the pressure-map files over HTTP: the manifest, then one file per forecast hour. Pure module:
 * `fetch` comes in as a parameter, so `node --test` can drive every case with a table of answers.
 *
 * Pages replaces the whole site on each deploy and every file is cached by the browser for ~10 minutes, so a
 * client can hold a manifest of the old cycle while the hour files are already the new ones (a 404, or a file
 * whose `cycle` differs), or the other way round: a stale hour file in the HTTP cache next to a fresh manifest.
 * Both are handled the same way: the manifest is requested again ONCE, bypassing the browser cache, and the hour
 * is requested again ONCE, also bypassing it, against whichever manifest came back. Nothing is retried beyond that.
 *
 * Every request has a timeout, so a hung connection ends as a network error instead of leaving the page loading.
 */
import { leerHora, leerManifest, type Hora, type Manifest } from './formato.ts'
import { urlDeArchivoIsobaras, urlManifestIsobaras } from './fuente.ts'

export type Fetcher = (url: string, init?: RequestInit) => Promise<Response>

export type MotivoErrorCarga = 'red' | 'datos' | 'no-encontrado'

export class ErrorCarga extends Error {
  readonly motivo: MotivoErrorCarga

  constructor(motivo: MotivoErrorCarga, detalle: string) {
    super(detalle)
    this.name = 'ErrorCarga'
    this.motivo = motivo
  }
}

export interface OpcionesDeCarga {
  /** From react-query: aborts the request when the page leaves or the hour changes. */
  signal?: AbortSignal
  /** Overrides the 15 s timeout of each request (tests). */
  timeoutMs?: number
  /**
   * Background preloading: when the hour is missing or stale, fail instead of asking for the manifest again. The
   * preloads of 40 hours must not each trigger a manifest request when a new cycle appears; the hour the user
   * actually looks at is loaded without this option and does the full retry.
   */
  sinReintento?: boolean
}

export const TIMEOUT_POR_DEFECTO_MS = 15_000

export interface HoraCargada {
  hora: Hora
  /** The manifest the hour was validated against; a newer one when the cycle changed while loading. */
  manifest: Manifest
}

type Cuerpo = { ok: true; json: unknown } | { ok: false }

/** GET and parse JSON. A 404 is `{ ok: false }`; network errors, timeouts, other statuses and non-JSON bodies throw. */
async function pedirJson(
  fetcher: Fetcher,
  url: string,
  opciones: OpcionesDeCarga,
  sinCache: boolean,
): Promise<Cuerpo> {
  const limite = AbortSignal.timeout(opciones.timeoutMs ?? TIMEOUT_POR_DEFECTO_MS)
  const signal = opciones.signal ? AbortSignal.any([opciones.signal, limite]) : limite
  let respuesta: Response
  try {
    respuesta = await fetcher(url, sinCache ? { cache: 'no-store', signal } : { signal })
  } catch {
    throw new ErrorCarga('red', `no se pudo conectar con ${new URL(url).host}`)
  }
  if (respuesta.status === 404) return { ok: false }
  if (!respuesta.ok) throw new ErrorCarga('red', `${new URL(url).host} respondió ${respuesta.status}`)
  try {
    return { ok: true, json: await respuesta.json() }
  } catch {
    throw new ErrorCarga('datos', 'la respuesta no es JSON')
  }
}

/** The manifest, validated. `sinCache` asks the browser to skip its HTTP cache. */
export async function cargarManifest(
  fetcher: Fetcher,
  opciones: OpcionesDeCarga & { sinCache?: boolean } = {},
): Promise<Manifest> {
  const cuerpo = await pedirJson(fetcher, urlManifestIsobaras(), opciones, opciones.sinCache === true)
  if (!cuerpo.ok) throw new ErrorCarga('no-encontrado', 'todavía no hay un manifest publicado')
  const manifest = leerManifest(cuerpo.json)
  if (!manifest.ok) throw new ErrorCarga('datos', `manifest inválido: ${manifest.detalle}`)
  return manifest.valor
}

type Intento = { hora: Hora } | { cambio: true }

async function pedirHora(
  fetcher: Fetcher,
  manifest: Manifest,
  archivo: string,
  opciones: OpcionesDeCarga,
  sinCache: boolean,
): Promise<Intento> {
  const cuerpo = await pedirJson(fetcher, urlDeArchivoIsobaras(archivo), opciones, sinCache)
  if (!cuerpo.ok) return { cambio: true }
  const hora = leerHora(cuerpo.json, manifest)
  if (hora.ok) return { hora: hora.valor }
  if (hora.motivo === 'ciclo-cambiado') return { cambio: true }
  throw new ErrorCarga('datos', `archivo de hora inválido: ${hora.detalle}`)
}

/** One forecast hour (`f`), validated against `manifest`; see the module comment for the single retry. */
export async function cargarHora(
  fetcher: Fetcher,
  manifest: Manifest,
  f: number,
  opciones: OpcionesDeCarga = {},
): Promise<HoraCargada> {
  const entrada = manifest.hours.find((h) => h.f === f)
  if (!entrada) throw new ErrorCarga('no-encontrado', `el manifest no tiene la hora +${f} h`)
  const primero = await pedirHora(fetcher, manifest, entrada.file, opciones, false)
  if ('hora' in primero) return { hora: primero.hora, manifest }
  if (opciones.sinReintento) throw new ErrorCarga('no-encontrado', `el archivo de la hora +${f} h no está disponible`)

  const nuevo = await cargarManifest(fetcher, { ...opciones, sinCache: true })
  const nuevaEntrada = nuevo.hours.find((h) => h.f === f)
  if (!nuevaEntrada) throw new ErrorCarga('no-encontrado', `el manifest actual ya no tiene la hora +${f} h`)
  const segundo = await pedirHora(fetcher, nuevo, nuevaEntrada.file, opciones, true)
  if (!('hora' in segundo)) throw new ErrorCarga('no-encontrado', `el archivo de la hora +${f} h no está publicado`)
  return { hora: segundo.hora, manifest: nuevo }
}
