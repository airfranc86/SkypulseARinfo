import type { NearestAirportResponse } from '@/lib/api'
import { isValidIcao, normalizeIcao, type WindShearFieldKey, type WindShearFormValues } from './windShear.ts'

/**
 * Lógica pura de la cizalladura que rodea a la precarga del METAR: elegir el aeropuerto más cercano,
 * decidir si se precarga sola, descartar respuestas tardías y cancelar pedidos en curso. Vive aparte
 * de windShear.ts (ya pasó el tope de tamaño). Solo módulos puros (sin `import.meta.env`) para poder
 * testearla con `node --test`.
 */

// ── Aeropuerto más cercano ───────────────────────────────────────────────────

/** Más lejos que esto, el viento de ese aeropuerto no representa el del lugar: solo se sugiere el código. */
export const MAX_AUTO_PREFILL_KM = 60

export interface LatLon {
  lat: number
  lon: number
}

export type NearestPrefillDecision =
  | { action: 'auto'; icao: string }
  | { action: 'suggest'; icao: string }
  | { action: 'none' }

export const SURFACE_KEYS: readonly WindShearFieldKey[] = ['surface_wind_dir_deg', 'surface_wind_speed_kt', 'surface_gust_kt']

/** El usuario ya cargó algo en superficie: la precarga automática nunca lo pisa. */
export const hasSurfaceInput = (values: WindShearFormValues): boolean =>
  SURFACE_KEYS.some(key => values[key].trim() !== '')

interface DecideInput {
  airport: NearestAirportResponse
  /** Contenido actual del campo ICAO. */
  icao: string
  values: WindShearFormValues
  /** Origen de la ubicación; la precarga automática solo confía en 'gps' y 'city'. */
  source?: LocationSource
}

/**
 * Qué hacer con el aeropuerto más cercano: precargar sola (cerca, ubicación confiable y sin datos del usuario), solo sugerir
 * el código (lejos, o el usuario ya cargó superficie) o nada (el usuario ya eligió un código, o el dato
 * del servidor no es usable). Nunca se pisa lo que el usuario escribió.
 */
export function decideNearestPrefill({ airport, icao, values, source }: DecideInput): NearestPrefillDecision {
  if (icao.trim() !== '') return { action: 'none' }
  if (!isValidIcao(airport.icao) || !Number.isFinite(airport.distance_km)) return { action: 'none' }
  const code = normalizeIcao(airport.icao)
  const near = airport.distance_km <= MAX_AUTO_PREFILL_KM
  // Una ubicación por defecto (o de origen desconocido) no dice dónde está el usuario: no se consulta sola.
  const trusted = source === 'gps' || source === 'city'
  return near && trusted && !hasSurfaceInput(values) ? { action: 'auto', icao: code } : { action: 'suggest', icao: code }
}

const KM = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0 })

const formatDistance = (km: number): string => (km < 1 ? 'menos de 1 km' : `${KM.format(km)} km`)

/** Desde dónde se mide la distancia, según cómo se obtuvo la ubicación. */
function placeReference(source: LocationSource | undefined): string {
  if (source === 'gps') return 'tu ubicación'
  if (source === 'city') return 'la ciudad elegida'
  return 'la ubicación guardada'
}

/**
 * Qué estación y a qué distancia. Si está lejos, o si la ubicación es la de por defecto (o de origen
 * desconocido), aclara que no se precargó el viento: nunca afirma que es "tu ubicación" sin saberlo.
 */
export function describeNearestStation(airport: NearestAirportResponse, source?: LocationSource): string {
  const station = `${airport.icao} (${airport.name})`
  const distance = formatDistance(airport.distance_km)
  const place = placeReference(source)
  if (airport.distance_km > MAX_AUTO_PREFILL_KM) {
    return `El aeropuerto más cercano es ${station}, a ${distance}: queda lejos de ${place} y no precargamos el viento automáticamente. Podés usar su METAR igual, con cautela.`
  }
  if (source !== 'gps' && source !== 'city') {
    return `Aeropuerto más cercano a ${place}: ${station}, a ${distance}. Como no sabemos si estás ahí, no precargamos el viento: tocá «Precargar desde METAR» si te sirve.`
  }
  return `METAR de ${station}, a ${distance} de ${place}.`
}

// ── Origen de la ubicación ───────────────────────────────────────────────────

/** Cómo se obtuvo la ubicación: GPS, ciudad elegida por el usuario, o el valor por defecto de la app. */
export type LocationSource = 'gps' | 'city' | 'fallback'

/** Lee el origen guardado; las entradas viejas (sin `source`) o inválidas quedan como desconocidas (undefined). */
export function parseLocationSource(raw: unknown): LocationSource | undefined {
  return raw === 'gps' || raw === 'city' || raw === 'fallback' ? raw : undefined
}

const COORD_SCALE = 100

/** 2 decimales (~1 km): sobra para elegir aeropuerto y evita partir la caché por el jitter del GPS. */
export const roundCoord = (value: number): number => Math.round(value * COORD_SCALE) / COORD_SCALE

// ── Descartar respuestas tardías ─────────────────────────────────────────────

interface ApplyGuard {
  requestedIcao: string
  /** Contenido actual del campo ICAO. */
  currentIcao: string
  requestId: number
  latestRequestId: number
  /** ICAO que informa la respuesta, si lo trae. */
  windIcao?: string
}

/**
 * Una respuesta de METAR solo se aplica si todavía es la que el usuario espera: el campo ICAO sigue
 * diciendo lo mismo, no hay un pedido más nuevo y la respuesta es de ese aeródromo.
 */
export function shouldApplyPrefill({ requestedIcao, currentIcao, requestId, latestRequestId, windIcao }: ApplyGuard): boolean {
  if (requestId !== latestRequestId) return false
  if (normalizeIcao(currentIcao) !== normalizeIcao(requestedIcao)) return false
  return windIcao === undefined || windIcao === '' || normalizeIcao(windIcao) === normalizeIcao(requestedIcao)
}

// ── Texto malformado en campos numéricos ─────────────────────────────────────

export type BadInputKeys = ReadonlySet<WindShearFieldKey>

/** `<input type="number">` informa '' para "2e" o "-": el formulario marca el campo aparte (validity.badInput). */
export function withBadInput(current: BadInputKeys, key: WindShearFieldKey, bad: boolean): BadInputKeys {
  if (current.has(key) === bad) return current
  const next = new Set(current)
  if (bad) next.add(key)
  else next.delete(key)
  return next
}

export function withoutKeys(current: BadInputKeys, keys: readonly WindShearFieldKey[]): BadInputKeys {
  if (!keys.some(key => current.has(key))) return current
  return new Set([...current].filter(key => !keys.includes(key)))
}

// ── Cancelación de pedidos ───────────────────────────────────────────────────

/** El pedido se canceló a propósito (nuevo envío, reset o desmontaje): no es un fallo y no se reintenta. */
export class RunCancelledError extends Error {
  constructor() {
    super('Pedido cancelado')
    this.name = 'RunCancelledError'
  }
}

export interface LinkedAbort {
  signal: AbortSignal
  /** Limpia el timer y los listeners; llamar siempre al terminar el intento. */
  dispose: () => void
}

/** Una señal que se aborta cuando se aborta cualquiera de `sources` o vence `timeoutMs`. */
export function linkedAbort(sources: readonly AbortSignal[], timeoutMs: number): LinkedAbort {
  const controller = new AbortController()
  const abort = (): void => controller.abort()
  const detach = sources.map(source => {
    if (source.aborted) {
      abort()
      return () => undefined
    }
    source.addEventListener('abort', abort, { once: true })
    return () => source.removeEventListener('abort', abort)
  })
  const timer = setTimeout(abort, timeoutMs)
  return {
    signal: controller.signal,
    dispose: () => {
      clearTimeout(timer)
      detach.forEach(fn => fn())
    },
  }
}
