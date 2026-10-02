import { normalizeText, type City } from './cities-ar.ts'

/**
 * Georef AR (datos.gob.ar): localidades de Argentina con provincia, departamento y centroide.
 * Módulo puro (URL, parseo defensivo, dedupe, ranking, merge): el fetch vive en `useCitySearch`.
 */

const GEOREF_ENDPOINT = 'https://apis.datos.gob.ar/georef/api/localidades'
const GEOREF_FIELDS = 'nombre,provincia.nombre,departamento.nombre,centroide'
const GEOREF_ORDER = 'nombre'

/** Mínimo de caracteres (útiles) para consultar Georef; antes de eso alcanza la lista local. */
export const GEOREF_MIN_QUERY_LENGTH = 3
/** Tope del texto enviado: Georef no necesita más y evita URLs enormes. */
export const GEOREF_MAX_QUERY_LENGTH = 100
/** `max` por defecto y tope (la API admite más, pero acá nunca se muestran tantas). */
export const GEOREF_DEFAULT_MAX = 8
export const GEOREF_MAX_RESULTS = 50
/** Filas de la respuesta que se examinan como máximo (la respuesta es input no confiable). */
export const GEOREF_MAX_ROWS = 100
/** Largo máximo de nombre/provincia/departamento aceptado. */
export const GEOREF_MAX_TEXT_LENGTH = 100
/**
 * Decimales de lat/lon (~11 m), como el redondeo de la geolocalización en useLocation.ts. Los
 * centroides de Georef traen 13 y terminarían en localStorage y en cada URL/clave de caché.
 */
export const GEOREF_COORD_DECIMALS = 4

/**
 * Límites de coordenadas: los mismos que LatParam/LonParam del backend
 * (apps/backend/app/core/params.py). El backend rechaza lo que quede afuera, así que un
 * resultado fuera de rango se descarta acá en vez de fallar después al pedir el pronóstico.
 */
const LAT_MIN = -55
const LAT_MAX = -21
const LON_MIN = -74
const LON_MAX = -53

/** Dos filas del mismo nombre+provincia a menos de esto (grados, ~1 km) son la misma localidad. */
const DUPLICATE_RADIUS_DEG = 0.01
/** Una remota con el mismo nombre que una local y a menos de esto (~11 km) es esa misma ciudad. */
const LOCAL_DUPLICATE_RADIUS_DEG = 0.1
const KEY_COORD_DECIMALS = 3

export interface Place {
  readonly name: string
  readonly province: string
  readonly department: string | null
  readonly lat: number
  readonly lon: number
}

/** Lo mínimo para mostrar un lugar: lo cumplen `Place` y `City` (la local no trae departamento). */
export interface PlaceLike {
  readonly name: string
  readonly province: string
  readonly department?: string | null
}

export interface PlaceKeyInput extends PlaceLike {
  readonly lat: number
  readonly lon: number
}

// ── Consulta y URL ───────────────────────────────────────────────────────────

/** Recorta, colapsa espacios y trunca; conserva mayúsculas y tildes. */
function cleanQuery(text: string): string {
  return text.trim().replace(/\s+/g, ' ').slice(0, GEOREF_MAX_QUERY_LENGTH).trimEnd()
}

/** Forma canónica de la consulta (sin tildes ni mayúsculas): sirve de clave de caché. */
export function normalizeGeorefQuery(text: string): string {
  return normalizeText(cleanQuery(text))
}

/** Hay algo que buscar: largo mínimo y al menos una letra o dígito (no solo espacios/signos). */
export function isSearchableQuery(text: string): boolean {
  const clean = cleanQuery(text)
  return clean.length >= GEOREF_MIN_QUERY_LENGTH && /[\p{L}\p{N}]/u.test(clean)
}

function clampMax(max: number): number {
  if (!Number.isFinite(max)) return GEOREF_DEFAULT_MAX
  return Math.min(GEOREF_MAX_RESULTS, Math.max(1, Math.floor(max)))
}

/** URL de búsqueda por nombre. `URLSearchParams` percent-encodea espacios, tildes, `&` y `#`. */
export function buildGeorefUrl(text: string, max: number): string {
  const params = new URLSearchParams({
    nombre: cleanQuery(text),
    max: String(clampMax(max)),
    campos: GEOREF_FIELDS,
    orden: GEOREF_ORDER,
  })
  return `${GEOREF_ENDPOINT}?${params.toString()}`
}

// ── Parseo defensivo ─────────────────────────────────────────────────────────

/** ¿Cae dentro de lo que acepta el backend? (límites inclusivos, ambos finitos). */
export function isWithinBounds(lat: number, lon: number): boolean {
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    lat >= LAT_MIN &&
    lat <= LAT_MAX &&
    lon >= LON_MIN &&
    lon <= LON_MAX
  )
}

function roundCoord(value: number): number {
  const factor = 10 ** GEOREF_COORD_DECIMALS
  return Math.round(value * factor) / factor
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readText(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const text = value.trim().slice(0, GEOREF_MAX_TEXT_LENGTH).trimEnd()
  return text.length > 0 ? text : null
}

function readNamed(value: unknown): string | null {
  return isRecord(value) ? readText(value.nombre) : null
}

function parseRow(raw: unknown): Place | null {
  if (!isRecord(raw)) return null
  const name = readText(raw.nombre)
  const province = readNamed(raw.provincia)
  const centroide = raw.centroide
  if (name === null || province === null || !isRecord(centroide)) return null
  if (typeof centroide.lat !== 'number' || typeof centroide.lon !== 'number') return null
  // Se redondea antes de validar: los límites se aplican al valor que de verdad se usa.
  const lat = roundCoord(centroide.lat)
  const lon = roundCoord(centroide.lon)
  if (!isWithinBounds(lat, lon)) return null
  return Object.freeze({ name, province, department: readNamed(raw.departamento), lat, lon })
}

/** Respuesta de `/localidades` → lugares válidos. Nunca lanza: lo malformado se descarta. */
export function parseGeorefResponse(payload: unknown): readonly Place[] {
  if (!isRecord(payload) || !Array.isArray(payload.localidades)) return Object.freeze([])
  const places: Place[] = []
  for (const raw of (payload.localidades as unknown[]).slice(0, GEOREF_MAX_ROWS)) {
    const place = parseRow(raw)
    if (place !== null) places.push(place)
  }
  return Object.freeze(places)
}

// ── Dedupe ───────────────────────────────────────────────────────────────────

function isNear(a: PlaceKeyInput, b: PlaceKeyInput, radiusDeg: number): boolean {
  return Math.abs(a.lat - b.lat) <= radiusDeg && Math.abs(a.lon - b.lon) <= radiusDeg
}

function sameName(a: PlaceLike, b: PlaceLike): boolean {
  return normalizeText(a.name) === normalizeText(b.name)
}

function sameNameAndProvince(a: PlaceLike, b: PlaceLike): boolean {
  return sameName(a, b) && normalizeText(a.province) === normalizeText(b.province)
}

function sameDepartment(a: PlaceLike, b: PlaceLike): boolean {
  const first = normalizeText(a.department ?? '')
  return first !== '' && first === normalizeText(b.department ?? '')
}

function isSamePlace(a: Place, b: Place): boolean {
  if (!sameNameAndProvince(a, b)) return false
  return sameDepartment(a, b) || isNear(a, b, DUPLICATE_RADIUS_DEG)
}

/** Quita duplicados (Georef repite filas, p. ej. dos "Córdoba"/Capital). Conserva el primero y el orden. */
export function dedupePlaces(places: readonly Place[]): Place[] {
  const kept: Place[] = []
  for (const place of places) {
    if (!kept.some((existing) => isSamePlace(existing, place))) kept.push(place)
  }
  return kept
}

// ── Ranking ──────────────────────────────────────────────────────────────────

const TIER_EXACT = 0
const TIER_PREFIX = 1
const TIER_WORD_PREFIX = 2
const TIER_CONTAINS = 3
const TIER_OTHER = 4

function matchTier(name: string, query: string, tokens: readonly string[]): number {
  if (name === query) return TIER_EXACT
  if (name.startsWith(query)) return TIER_PREFIX
  const words = name.split(' ')
  if (tokens.every((token) => words.some((word) => word.startsWith(token)))) return TIER_WORD_PREFIX
  return name.includes(query) ? TIER_CONTAINS : TIER_OTHER
}

/**
 * Ordena por relevancia: coincidencia exacta, prefijo, prefijo de alguna palabra, contiene y el
 * resto (Georef es tolerante, así que puede traer filas que no calzan literal). Insensible a
 * tildes y mayúsculas; estable entre empates (conserva el orden de Georef).
 */
export function rankPlaces(places: readonly Place[], query: string): Place[] {
  const normalized = normalizeGeorefQuery(query)
  if (normalized === '') return [...places]
  const tokens = normalized.split(' ')
  return places
    .map((place, index) => ({
      place,
      index,
      tier: matchTier(normalizeText(place.name).replace(/\s+/g, ' '), normalized, tokens),
    }))
    .sort((a, b) => a.tier - b.tier || a.index - b.index)
    .map((entry) => entry.place)
}

// ── Presentación ─────────────────────────────────────────────────────────────

/** Clave estable y única para listas: nombre + provincia + departamento + coordenadas redondeadas. */
export function placeKey(place: PlaceKeyInput): string {
  const lat = place.lat.toFixed(KEY_COORD_DECIMALS)
  const lon = place.lon.toFixed(KEY_COORD_DECIMALS)
  return `${place.name}|${place.province}|${place.department ?? ''}|${lat}|${lon}`
}

/** "Departamento, Provincia"; sin departamento si falta o repite el nombre de la localidad. */
export function placeDetail(place: PlaceLike): string {
  const department = (place.department ?? '').trim()
  if (department === '' || normalizeText(department) === normalizeText(place.name)) {
    return place.province
  }
  return `${department}, ${place.province}`
}

/** "Localidad · Departamento, Provincia". */
export function placeLabel(place: PlaceLike): string {
  return `${place.name} · ${placeDetail(place)}`
}

// ── Estado de la búsqueda ────────────────────────────────────────────────────

export type SearchHint = 'none' | 'searching' | 'unavailable' | 'not_found'

export interface SearchHintInput {
  /** El usuario cerró el desplegable. */
  dismissed: boolean
  /** Hay una búsqueda remota pendiente (debounce o en vuelo). */
  isSearching: boolean
  /** La última búsqueda remota terminó en error (red, HTTP o formato). */
  remoteFailed: boolean
  /** Largo del texto tipeado, sin espacios en los extremos. */
  queryLength: number
  resultCount: number
}

/**
 * Qué aviso va bajo la lista. `not_found` solo si la búsqueda remota terminó bien y no hubo
 * nada; si el servicio falló no se puede afirmar que la localidad no existe (`unavailable`).
 */
export function searchHint(input: SearchHintInput): SearchHint {
  if (input.dismissed) return 'none'
  if (input.isSearching) return 'searching'
  if (input.resultCount > 0 || input.queryLength < GEOREF_MIN_QUERY_LENGTH) return 'none'
  return input.remoteFailed ? 'unavailable' : 'not_found'
}

// ── Merge ────────────────────────────────────────────────────────────────────

function toCity(place: Place): City {
  const base = { name: place.name, province: place.province, lat: place.lat, lon: place.lon }
  return place.department === null ? base : { ...base, department: place.department }
}

function duplicatesLocal(place: Place, local: readonly City[]): boolean {
  return local.some(
    (city) => sameNameAndProvince(city, place) || (sameName(city, place) && isNear(city, place, LOCAL_DUPLICATE_RADIUS_DEG)),
  )
}

/**
 * Locales primero (instantáneas y de confianza), luego remotas que no repitan una local
 * (mismo nombre+provincia, o mismo nombre y casi las mismas coordenadas: "CABA" vs "Ciudad
 * Autónoma de Buenos Aires"). Total acotado a `limit`.
 */
export function mergeResults(local: readonly City[], remote: readonly Place[], limit: number): City[] {
  const max = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : 0
  const merged = local.slice(0, max)
  for (const place of remote) {
    if (merged.length >= max) break
    if (!duplicatesLocal(place, local)) merged.push(toCity(place))
  }
  return merged
}

/** Respuesta cruda de Georef → lugares listos para mezclar: parseados, sin repetidos y ordenados. */
export function processGeorefResponse(payload: unknown, query: string): Place[] {
  return rankPlaces(dedupePlaces(parseGeorefResponse(payload)), query)
}
