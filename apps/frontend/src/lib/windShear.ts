import type {
  MetarDecodedResponse,
  WindShearDriverCode,
  WindShearLayer,
  WindShearLevel,
  WindShearRequest,
  WindShearResponse,
  WindShearRiskCode,
  WindShearThermal,
} from '@/lib/api'
import { roundMeasure } from './windShearHelpers.ts'
import messages from './windShearMessages.json' with { type: 'json' }

// Se re-exportan desde acá: el formato de magnitudes y el copy de errores viven en windShearHelpers.ts.
export { describeServerError, formatNearThreshold } from './windShearHelpers.ts'

/**
 * Cizalladura (LLWS) en aproximación: formulario, estimación local fail-open y copy. La estimación
 * espeja EXACTO app/services/wind_shear.py (fórmulas, umbrales, desempate), así que sirve de respaldo
 * completo si el backend no responde. Solo importa módulos puros (nada con `import.meta.env`)
 * para poder testearla con `node --test`.
 */

// ── Copy compartido con el backend (único origen: windShearMessages.json) ─────

/** Un test del backend verifica que este JSON no diverja de sus diccionarios. */
export const LEVEL_MESSAGES: Record<WindShearLevel, string> = messages.levels
export const DRIVER_MESSAGES: Record<WindShearDriverCode, string> = messages.drivers
export const THERMAL_MESSAGES: Record<WindShearThermal['code'], string> = messages.thermal

const RISK_CODES: Record<WindShearLevel, WindShearRiskCode> = {
  verde: 'SHEAR_LIGHT',
  amarillo: 'SHEAR_MODERATE',
  naranja: 'SHEAR_SEVERE',
  rojo: 'SHEAR_EXTREME',
}

// ── Copy solo del frontend: impacto operativo por nivel ──────────────────────

export interface LevelCopy {
  headline: string
  /** Impacto en paracaidismo (velamen). */
  canopy: string
  /** Impacto en la aeronave de salto. */
  aircraft: string
  /** Qué hacer, en una línea. */
  action: string
}

/**
 * Deliberadamente genérico, condicional y sin cifras: la herramienta no conoce el velamen, la
 * aeronave ni los procedimientos aplicables. Un test verifica que ningún texto lleve dígitos.
 */
export const LEVEL_COPY: Record<WindShearLevel, LevelCopy> = {
  verde: {
    headline: 'Cizalladura leve',
    canopy:
      'Con los datos ingresados la cizalladura evaluada es leve, pero solo se evaluó el viento que cargaste: cerca del suelo puede cambiar de un momento a otro. Conservá margen para corregir en el flare.',
    aircraft:
      'Con estos datos puede no hacer falta un ajuste especial de velocidad en final, pero solo se evaluó el viento ingresado. Mantené una aproximación estabilizada y atenta a cualquier cambio de viento.',
    action:
      'Con estos datos, seguí las verificaciones habituales del salto y mantené el monitoreo del viento hasta el aterrizaje: la herramienta solo evaluó lo que ingresaste.',
  },
  amarillo: {
    headline: 'Cizalladura moderada',
    canopy:
      'Puede haber una pérdida repentina de sustentación o una caída de la presión interna del velamen cerca del flare. Considerá más margen de altura en final y evitá maniobras tardías cerca del suelo.',
    aircraft:
      'Puede hacer falta ajustar velocidad y potencia en final para sostener la trayectoria de planeo. Mantené una aproximación estabilizada.',
    action: 'Considerá subir el margen de altura, revisá el viento justo antes de decidir y consultá al jefe de saltos.',
  },
  naranja: {
    headline: 'Cizalladura fuerte',
    canopy:
      'Puede haber pérdida de presión interna del velamen, un descenso repentino cerca del flare y pérdida de control direccional. Un error de timing a baja altura puede tener consecuencias serias.',
    aircraft:
      'Puede hacer falta corregir velocidad y trayectoria de forma repetida en final, con menos margen ante una pérdida repentina de sustentación. Considerá una velocidad de aproximación con margen y un punto claro para abortar.',
    action: 'Considerá postergar o cambiar la aproximación. Si se opera, que sea con el aval del piloto y del jefe de saltos.',
  },
  rojo: {
    headline: 'Cizalladura extrema',
    canopy:
      'Puede haber colapso del velamen y pérdida de control direccional a baja altura, sin margen para recuperar.',
    aircraft:
      'La aproximación puede volverse inestable y difícil de corregir. Considerá no iniciarla y planificar una alternativa.',
    action: 'Postergá la operación hasta que el viento cambie y volvé a calcular con datos nuevos.',
  },
}

export const DISCLAIMER =
  'Herramienta informativa: no reemplaza el criterio del piloto ni del jefe de saltos. Los umbrales son una referencia de partida, todavía sin validar con eventos reales.'

// ── Formulario ───────────────────────────────────────────────────────────────

export type WindShearFieldKey =
  | 'surface_wind_dir_deg'
  | 'surface_wind_speed_kt'
  | 'surface_gust_kt'
  | 'wind_500ft_dir_deg'
  | 'wind_500ft_speed_kt'
  | 'wind_1000ft_dir_deg'
  | 'wind_1000ft_speed_kt'
  | 'surface_temp_c'
  | 'temp_1000ft_c'

export type WindShearFormValues = Record<WindShearFieldKey, string>
export type WindShearFieldErrors = Partial<Record<WindShearFieldKey, string>>

interface FieldRule {
  key: WindShearFieldKey
  label: string
  min: number
  max: number
  optional: boolean
}

// Mismas cotas que WindShearRequest en el backend.
const MAX_DIRECTION_DEG = 360
const MAX_SURFACE_SPEED_KT = 100
const MAX_ALOFT_SPEED_KT = 150
const MAX_TEMP_C = 60

const FIELD_RULES: readonly FieldRule[] = [
  { key: 'surface_wind_dir_deg', label: 'Dirección en superficie', min: 0, max: MAX_DIRECTION_DEG, optional: false },
  { key: 'surface_wind_speed_kt', label: 'Viento en superficie', min: 0, max: MAX_SURFACE_SPEED_KT, optional: false },
  { key: 'surface_gust_kt', label: 'Ráfaga en superficie', min: 0, max: MAX_ALOFT_SPEED_KT, optional: true },
  { key: 'wind_500ft_dir_deg', label: 'Dirección a 500 ft', min: 0, max: MAX_DIRECTION_DEG, optional: false },
  { key: 'wind_500ft_speed_kt', label: 'Viento a 500 ft', min: 0, max: MAX_ALOFT_SPEED_KT, optional: false },
  { key: 'wind_1000ft_dir_deg', label: 'Dirección a 1.000 ft', min: 0, max: MAX_DIRECTION_DEG, optional: true },
  { key: 'wind_1000ft_speed_kt', label: 'Viento a 1.000 ft', min: 0, max: MAX_ALOFT_SPEED_KT, optional: true },
  { key: 'surface_temp_c', label: 'Temperatura en superficie', min: -MAX_TEMP_C, max: MAX_TEMP_C, optional: true },
  { key: 'temp_1000ft_c', label: 'Temperatura a 1.000 ft', min: -MAX_TEMP_C, max: MAX_TEMP_C, optional: true },
]

/** Orden visual del formulario: define cuál es el "primer" campo con error. */
export const FIELD_ORDER: readonly WindShearFieldKey[] = FIELD_RULES.map(rule => rule.key)

export const FIELD_LABELS: Record<WindShearFieldKey, string> = Object.fromEntries(
  FIELD_RULES.map(rule => [rule.key, rule.label]),
) as Record<WindShearFieldKey, string>

/** Pares que van completos o vacíos: viento a 1.000 ft (dirección + rapidez) y las dos temperaturas. */
const ALL_OR_NOTHING: readonly (readonly [WindShearFieldKey, WindShearFieldKey])[] = [
  ['wind_1000ft_dir_deg', 'wind_1000ft_speed_kt'],
  ['surface_temp_c', 'temp_1000ft_c'],
]

type ParsedNumbers = Partial<Record<WindShearFieldKey, number>>

const normalizeRaw = (raw: string): string => raw.trim().replace(',', '.')

const NO_BAD_INPUT: ReadonlySet<WindShearFieldKey> = new Set()

function validateFields(
  values: WindShearFormValues,
  badInput: ReadonlySet<WindShearFieldKey>,
): { parsed: ParsedNumbers; errors: WindShearFieldErrors } {
  const parsed: ParsedNumbers = {}
  const errors: WindShearFieldErrors = {}
  for (const rule of FIELD_RULES) {
    // El input numérico del navegador informa '' ante texto como "2e": no es un campo vacío.
    if (badInput.has(rule.key)) {
      errors[rule.key] = `${rule.label}: ingresá un número válido.`
      continue
    }
    const raw = normalizeRaw(values[rule.key])
    if (raw === '') {
      if (!rule.optional) errors[rule.key] = `${rule.label}: ingresá un número.`
      continue
    }
    const n = Number(raw)
    if (!Number.isFinite(n)) errors[rule.key] = `${rule.label}: ingresá un número.`
    else if (n < rule.min || n > rule.max) errors[rule.key] = `${rule.label}: desde ${rule.min} hasta ${rule.max}.`
    else parsed[rule.key] = n
  }
  return { parsed, errors }
}

function validatePairs(values: WindShearFormValues, errors: WindShearFieldErrors): void {
  for (const [a, b] of ALL_OR_NOTHING) {
    const aFilled = normalizeRaw(values[a]) !== ''
    const bFilled = normalizeRaw(values[b]) !== ''
    if (aFilled === bFilled) continue
    const [empty, filled] = aFilled ? [b, a] : [a, b]
    errors[empty] ??= `${FIELD_LABELS[empty]}: completalo junto con "${FIELD_LABELS[filled]}", o dejá ambos vacíos.`
  }
}

function required(parsed: ParsedNumbers, key: WindShearFieldKey): number {
  const value = parsed[key]
  if (value === undefined) throw new Error(`Campo obligatorio sin validar: ${key}`)
  return value
}

export function parseWindShearForm(
  values: WindShearFormValues,
  badInput: ReadonlySet<WindShearFieldKey> = NO_BAD_INPUT,
): { ok: true; request: WindShearRequest } | { ok: false; errors: WindShearFieldErrors } {
  const { parsed, errors } = validateFields(values, badInput)
  validatePairs(values, errors)

  const { surface_gust_kt: gust, surface_wind_speed_kt: speed } = parsed
  if (gust !== undefined && speed !== undefined && gust < speed) {
    errors.surface_gust_kt = 'Ráfaga en superficie: no puede ser menor que el viento sostenido.'
  }
  if (Object.keys(errors).length > 0) return { ok: false, errors }

  return {
    ok: true,
    request: {
      surface_wind_dir_deg: required(parsed, 'surface_wind_dir_deg'),
      surface_wind_speed_kt: required(parsed, 'surface_wind_speed_kt'),
      surface_gust_kt: parsed.surface_gust_kt ?? null,
      wind_500ft_dir_deg: required(parsed, 'wind_500ft_dir_deg'),
      wind_500ft_speed_kt: required(parsed, 'wind_500ft_speed_kt'),
      wind_1000ft_dir_deg: parsed.wind_1000ft_dir_deg ?? null,
      wind_1000ft_speed_kt: parsed.wind_1000ft_speed_kt ?? null,
      surface_temp_c: parsed.surface_temp_c ?? null,
      temp_1000ft_c: parsed.temp_1000ft_c ?? null,
    },
  }
}

export function requestsEqual(a: WindShearRequest, b: WindShearRequest): boolean {
  return (Object.keys(a) as (keyof WindShearRequest)[]).every(key => a[key] === b[key])
}

// ── Estimación local (espejo de app/services/wind_shear.py) ──────────────────

const SURFACE_FT = 0
const LEVEL_500_FT = 500
const LEVEL_1000_FT = 1000
const FT_PER_SHEAR_UNIT = 100 // la cizalladura se expresa en kt por cada 100 ft
const FT_PER_LAPSE_UNIT = 1000 // el gradiente térmico, en °C por cada 1.000 ft
const DEG_TO_RAD = Math.PI / 180

// Umbrales: hipótesis de partida de Linear FRA-119, sin validar con eventos observados.
// Deben coincidir con el backend (verde < 4 · amarillo [4, 9) · naranja [9, 12] · rojo > 12 o ráfaga > 15).
const SHEAR_YELLOW_KT_PER_100FT = 4
const SHEAR_ORANGE_KT_PER_100FT = 9
const SHEAR_RED_KT_PER_100FT = 12
const GUST_SPREAD_RED_KT = 15

/** Para el redondeo al mostrar: valores que cambian de nivel al cruzarlos. */
export const SHEAR_THRESHOLDS: readonly number[] = [SHEAR_YELLOW_KT_PER_100FT, SHEAR_ORANGE_KT_PER_100FT, SHEAR_RED_KT_PER_100FT]
export const GUST_THRESHOLDS: readonly number[] = [GUST_SPREAD_RED_KT]

/** Adiabático seco ≈ 9,8 °C/km ≈ 2,99 °C por cada 1.000 ft. Solo para la nota informativa. */
const DRY_ADIABATIC_LAPSE_C_PER_1000FT = 2.99

const SEVERITY: Record<WindShearLevel, number> = { verde: 0, amarillo: 1, naranja: 2, rojo: 3 }

interface WindVector {
  heightFt: number
  u: number
  v: number
}

/** Convención meteorológica: la dirección es DESDE donde sopla. u hacia el este, v hacia el norte. */
function windVector(heightFt: number, dirDeg: number, speedKt: number): WindVector {
  const rad = dirDeg * DEG_TO_RAD
  return { heightFt, u: -speedKt * Math.sin(rad), v: -speedKt * Math.cos(rad) }
}

/** La cizalladura sale ya redondeada (MEASURE_DECIMALS): el nivel, los drivers y el valor mostrado usan el mismo número. */
function layerShear(bottom: WindVector, top: WindVector): WindShearLayer {
  const deltaKt = Math.hypot(top.u - bottom.u, top.v - bottom.v)
  const hundredsOfFt = (top.heightFt - bottom.heightFt) / FT_PER_SHEAR_UNIT
  return { from_ft: bottom.heightFt, to_ft: top.heightFt, shear_kt_per_100ft: roundMeasure(deltaKt / hundredsOfFt) }
}

function shearLevel(shear: number): WindShearLevel {
  if (shear > SHEAR_RED_KT_PER_100FT) return 'rojo'
  if (shear >= SHEAR_ORANGE_KT_PER_100FT) return 'naranja'
  if (shear >= SHEAR_YELLOW_KT_PER_100FT) return 'amarillo'
  return 'verde'
}

/** La ráfaga solo puede producir rojo: exactamente 15 kt de diferencia no alcanza por sí sola. */
const gustLevel = (gustSpread: number): WindShearLevel => (gustSpread > GUST_SPREAD_RED_KT ? 'rojo' : 'verde')

/** Gana la condición más severa entre la cizalladura de la capa más fuerte y ráfaga − sostenido. */
export function classifyWindShear(maxShear: number, gustSpread: number): WindShearLevel {
  const fromShear = shearLevel(maxShear)
  const fromGust = gustLevel(gustSpread)
  return SEVERITY[fromGust] > SEVERITY[fromShear] ? fromGust : fromShear
}

/** Qué condiciones alcanzan el nivel elegido (o uno superior). Verde no tiene drivers. */
function driversFor(level: WindShearLevel, maxShear: number, gustSpread: number): WindShearDriverCode[] {
  if (level === 'verde') return []
  const drivers: WindShearDriverCode[] = []
  if (SEVERITY[shearLevel(maxShear)] >= SEVERITY[level]) drivers.push('shear')
  if (SEVERITY[gustLevel(gustSpread)] >= SEVERITY[level]) drivers.push('gust_spread')
  return drivers
}

function thermalNote(surfaceC: number | null, aloftC: number | null): WindShearThermal | null {
  if (surfaceC === null || aloftC === null) return null
  const lapse = roundMeasure(((surfaceC - aloftC) * FT_PER_LAPSE_UNIT) / (LEVEL_1000_FT - SURFACE_FT))
  if (aloftC > surfaceC) return { code: 'inversion', lapse_c_per_1000ft: lapse }
  const code = lapse > DRY_ADIABATIC_LAPSE_C_PER_1000FT ? 'unstable' : 'neutral'
  return { code, lapse_c_per_1000ft: lapse }
}

/** Misma forma que la respuesta del servidor: la UI renderiza ambas con el mismo código. */
export function estimateWindShear(request: WindShearRequest): WindShearResponse {
  const levels = [
    windVector(SURFACE_FT, request.surface_wind_dir_deg, request.surface_wind_speed_kt),
    windVector(LEVEL_500_FT, request.wind_500ft_dir_deg, request.wind_500ft_speed_kt),
  ]
  if (request.wind_1000ft_dir_deg !== null && request.wind_1000ft_speed_kt !== null) {
    levels.push(windVector(LEVEL_1000_FT, request.wind_1000ft_dir_deg, request.wind_1000ft_speed_kt))
  }
  const layers = levels.slice(1).map((top, i) => layerShear(levels[i], top))
  // En un empate gana la capa más baja: es la que más pesa en la toma de contacto.
  const maxLayer = layers.reduce((best, layer) => (layer.shear_kt_per_100ft > best.shear_kt_per_100ft ? layer : best))
  const gustSpread = request.surface_gust_kt === null ? 0 : roundMeasure(request.surface_gust_kt - request.surface_wind_speed_kt)
  const level = classifyWindShear(maxLayer.shear_kt_per_100ft, gustSpread)

  return {
    inputs: request,
    calculations: {
      layers,
      max_shear_kt_per_100ft: maxLayer.shear_kt_per_100ft,
      max_layer: { from_ft: maxLayer.from_ft, to_ft: maxLayer.to_ft },
      gust_spread_kt: gustSpread,
      thermal: thermalNote(request.surface_temp_c, request.temp_1000ft_c),
    },
    risk: { level, code: RISK_CODES[level], message: LEVEL_MESSAGES[level] },
    drivers: driversFor(level, maxLayer.shear_kt_per_100ft, gustSpread),
  }
}

// ── Precarga del viento de superficie desde el METAR ─────────────────────────

export interface SurfaceWindPrefill {
  icao: string
  /** null: viento variable (VRB) o dirección ausente; hay que cargarla a mano. */
  directionDeg: number | null
  speedKt: number
  gustKt: number | null
  variable: boolean
  /** Hora de emisión del METAR (ISO, UTC) tal como la informa CheckWX; null si falta. */
  observed: string | null
}

const VARIABLE_WIND_RE = /\bVRB\d{2,3}(?:G\d{2,3})?(?:KT|MPS)\b/
const ICAO_RE = /^[A-Z]{4}$/

export const METAR_NOTICE_NO_DATA = 'No encontramos un METAR para ese código. Cargá el viento a mano.'
export const METAR_NOTICE_UNAVAILABLE = 'No pudimos precargar el viento del METAR. Cargalo a mano.'

export const normalizeIcao = (raw: string): string => raw.trim().toUpperCase()
export const isValidIcao = (raw: string): boolean => ICAO_RE.test(normalizeIcao(raw))

const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

/** Un METAR no trae viento en altura: solo se extrae la superficie. null si no hay viento utilizable. */
export function extractSurfaceWind(response: MetarDecodedResponse): SurfaceWindPrefill | null {
  const entry = response.data?.[0]
  const wind = entry?.wind
  if (!entry || !wind || !isFiniteNumber(wind.speed_kts)) return null

  const speedKt = wind.speed_kts
  const degrees = isFiniteNumber(wind.degrees) ? wind.degrees : null
  const variable = degrees === null || VARIABLE_WIND_RE.test(entry.raw_text ?? '')
  const gust = wind.gust_kts
  return {
    icao: entry.icao ?? '',
    directionDeg: variable ? null : degrees,
    speedKt,
    gustKt: isFiniteNumber(gust) && gust >= speedKt ? gust : null,
    variable,
    observed: entry.observed ?? null,
  }
}

/** Reemplaza solo los tres campos de superficie; la dirección variable queda vacía para cargarla a mano. */
export function applySurfaceWind(values: WindShearFormValues, wind: SurfaceWindPrefill): WindShearFormValues {
  return {
    ...values,
    surface_wind_dir_deg: wind.directionDeg === null ? '' : String(wind.directionDeg),
    surface_wind_speed_kt: String(wind.speedKt),
    surface_gust_kt: wind.gustKt === null ? '' : String(wind.gustKt),
  }
}
