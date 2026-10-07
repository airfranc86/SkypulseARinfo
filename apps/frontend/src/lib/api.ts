import { ApiError, buildApiError } from '@/lib/apiErrors'
import type { TafDecoded } from '@/lib/taf'

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

if (import.meta.env.PROD && !BASE_URL) {
  throw new Error('[SkyPulse] VITE_API_BASE_URL is not set. Configure it in Vercel environment variables.')
}

export { ApiError } from '@/lib/apiErrors'

async function throwApiError(res: Response): Promise<never> {
  const body = await res.json().catch(() => null)
  throw buildApiError(body, res.status, res.headers.get('Retry-After'))
}

/** Sin tope, un backend que no responde deja la pantalla cargando para siempre. Con 30 s el
 *  reintento de TanStack llega cuando Render ya despertó (el cold start ronda 20-50 s). */
const REQUEST_TIMEOUT_MS = 30_000

async function request<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
  }
  let res: Response
  try {
    res = await fetch(url.toString(), { signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError('El servidor no respondió a tiempo.', 504)
    }
    throw error
  }
  if (!res.ok) await throwApiError(res)
  return res.json()
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) await throwApiError(res)
  return res.json()
}

/**
 * POST con cuerpo JSON y el mismo tope de 30 s que `request`: pasado el tiempo, `ApiError` 504 en vez de
 * quedar cargando. Devuelve la respuesta ya comprobada (`ok`); cada variante decide si lee el cuerpo.
 * Es lo que usan las alertas push; `postJson` (sin tope) sigue igual para sus otros llamadores.
 */
async function postConTope(path: string, body: unknown): Promise<Response> {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  let res: Response
  try {
    res = await fetch(url.toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError('El servidor no respondió a tiempo.', 504)
    }
    throw error
  }
  if (!res.ok) await throwApiError(res)
  return res
}

async function postJsonConTope<T>(path: string, body: unknown): Promise<T> {
  const res = await postConTope(path, body)
  return res.json()
}

/** Para las respuestas sin cuerpo (204): `res.json()` reventaría con "Unexpected end of JSON input". */
async function postSinCuerpo(path: string, body: unknown): Promise<void> {
  await postConTope(path, body)
}

// ── Schemas — espejados del backend ──────────────────────────────────────────

export interface WeatherCurrentResponse {
  temp_c: number | null
  feels_like_c: number | null
  humidity: number | null
  wind_speed_kmh: number | null
  wind_dir_deg: number | null
  wind_dir_cardinal: string | null
  pressure_hpa: number | null
  precip_1h_mm: number | null
  cloud_cover: number | null
  description: string | null
  meta: {
    source: string
    reason: string
    station: {
      name: string
      lat: number
      lon: number
      distance_km: number
    } | null
    fetched_at: string
    cache_hit: boolean
    stale: boolean
    /** Instante (UTC, ISO) que la propia fuente reporta como momento de la observación. */
    observed_at?: string | null
  }
}

export interface HourlyScore {
  timestamp: number
  hour_label: string
  score: number
  is_best: boolean
}

/** Respuesta de /tender-ropa y /hacer-deporte */
export interface ToolResult {
  tool: string
  score: number
  label: 'Excelente' | 'Bueno' | 'Regular' | 'No apto'
  color: 'green' | 'yellow' | 'red'
  headline: string
  reason: string
  best_window: string | null
  hourly: HourlyScore[]
  temp: number | null
  humidity: number | null
  wind_speed: number | null
  precip: number | null
  source?: string
}

/** Respuesta de /sensacion-termica */
export interface FeelsLikeResponse {
  formula: 'heat_index' | 'wind_chill' | 'none'
  feels_like_c: number
  temp_c: number
  humidity: number | null
  wind_speed_kmh: number | null
  description: string
}

/** Respuesta de /cota-de-nieve */
export interface SnowLevelResponse {
  alcaide_m: number
  gradiente_m: number
  m850_hpa_m: number | null
  average_m: number
  temp_c: number
  station_altitude_m: number
  description: string
  source?: string  // "openmeteo" | "unavailable"
}

export interface CarWashDay {
  date: string
  day_label: string
  score: number
  label: 'Excelente' | 'Bueno' | 'Regular' | 'No apto'
  color: 'green' | 'yellow' | 'red'
  headline: string
  precip_mm: number
  temp_max_c: number
  temp_min_c: number
  wind_speed_kmh: number
  humidity: number
  is_best: boolean
}

export interface CarWashForecastResponse {
  days: CarWashDay[]
  source?: string
}

export interface LaundryDay {
  date: string
  day_label: string
  score: number
  label: 'Excelente' | 'Bueno' | 'Regular' | 'No apto'
  headline: string
  temp_max_c: number
  humidity: number
  wind_speed_kmh: number
  precip_prob: number
  is_best: boolean
  confidence_pct: number
  confidence_label: 'Alta' | 'Media' | 'Baja'
}

export interface LaundryForecastResponse {
  days: LaundryDay[]
  source: string
}

export interface EarthquakeEvent {
  id: string
  magnitude: number
  place: string
  occurred_at: string   // ISO datetime from backend
  depth_km: number
  lat: number
  lon: number
  distance_km: number
  usgs_url: string
  source?: string       // "emsc" | "usgs" — red que reportó el evento
}

export interface EarthquakesResponse {
  events: EarthquakeEvent[]
  total: number
  radius_km: number
}

// ── Volcanes schemas ──────────────────────────────────────────────────────────

/** 'sin_datos': OAVV no respondió o su imagen no se pudo leer. No es "estable" ni alerta. */
export type AlertLevel = 'verde' | 'amarillo' | 'naranja' | 'rojo' | 'sin_datos'

export interface Volcan {
  id: number
  name: string
  province: string
  alert_level: AlertLevel
  alert_color_hex: string
  lat: number
  lon: number
  segemar_url: string
  ranking: number | null
}

export interface VolcanesResponse {
  /** Volcanes con dato (excluye los 'sin_datos'). */
  total: number
  /** Algún volcán con dato en naranja o rojo. */
  has_active_alert: boolean
  volcanes: Volcan[]
  /** False si falta el dato de al menos un volcán. Opcional: un backend anterior no lo envía. */
  available?: boolean
}

// ── Alertas SMN ────────────────────────────────────────────────────────────────

export interface SmnAlerta {
  nivel: string
  tipo: string
  fecha_desde: string | null
  fecha_hasta: string | null
  descripcion: string
  /** Severidad CAP tal cual (Extreme, Severe, Moderate…). Opcional: un backend anterior no la envía. */
  severidad?: string | null
  /** Qué hacer, según el SMN; el feed puede omitirlo. Opcional: un backend anterior no lo envía. */
  instruccion?: string | null
}

export interface SmnAlertasResponse {
  alertas: SmnAlerta[]
  available: boolean
  fetched_at: string
}

// ── Dashboard schemas ─────────────────────────────────────────────────────────

export interface MoonPhaseInfo {
  name: string
  illumination: number
  icon: string
  position_pct: number | null
  moonrise_label: string | null
  moonset_label: string | null
  is_above_horizon: boolean
}

export interface DayArcInfo {
  sunrise: string
  sunset: string
  current_position_pct: number
  daylight_label: string
  is_day: boolean
}

export type ConvectiveRisk = 'low' | 'moderate' | 'high' | 'severe'

export interface HourlyEntry {
  timestamp: number
  hour_label: string
  date: string
  temp_c: number | null
  precip_mm: number | null
  precip_prob: number | null
  weather_code: number | null
  icon: string
  is_day: boolean
  convective_risk?: ConvectiveRisk | null
  freezing_level_height_m?: number | null
  wind_gusts_kmh?: number | null
}

/** The two models behind the 7-day card. */
export type ForecastModelName = 'gfs' | 'ecmwf'

/** Rain probability band of a trend day (days 5 to 7), in percent. */
export type RainBand = '10-40' | '40-60' | '60-100'

/** One model's numbers for one day. Still in the response, not shown in the UI (FRA-334). */
export interface ModelDayDetail {
  temp_max: number | null
  temp_min: number | null
  precip_sum: number | null
  precip_prob: number | null
  wind_speed_max: number | null
  cloud_cover_mean: number | null
}

/** Only one of the two models predicts rain (above 0.9 mm). Still in the response, not shown in the UI (FRA-334). */
export interface RainDisagreement {
  gfs_mm: number
  ecmwf_mm: number
}

export interface DailyEntry {
  date: string
  day_label: string
  day_label_long: string
  temp_max: number | null
  temp_min: number | null
  precip_sum: number | null
  precip_prob: number | null
  wind_speed_max: number | null
  snow_level_m: number | null
  weather_code: number | null
  icon: string
  wind_dir_dominant_deg: number | null
  wind_dir_cardinal: string | null
  wind_icon: string | null
  wind_intensity: string | null
  wind_shift: boolean
  convective_risk?: ConvectiveRisk | null
  rain_disagreement: RainDisagreement | null
  /** Days 5 to 7: a trend that can change. */
  is_trend: boolean
  /** Probability band of a trend day; null below 10 % and outside the trend. */
  rain_band: RainBand | null
  /** Per-model numbers; each model is null when it did not answer. */
  models: Record<ForecastModelName, ModelDayDetail | null> | null
}

export interface RainForecastInfo {
  status_text: string
  confidence_label: 'alta' | 'media' | 'baja'
  has_rain_today: boolean
  best_window_start: string | null
  best_window_end: string | null
  best_window_label: string | null
  is_ideal_for_drying: boolean
  drying_label: string | null
  drying_hours_range: string | null
  drying_reason: string | null
}

/** Where the dashboard "now" comes from: the nearest airport METAR, an SMN station or the model. */
export type CurrentSource = 'metar' | 'smn' | 'openmeteo' | 'unknown'

/** Why the dashboard "now" uses (or not) the nearest airport METAR (FRA-320). */
export type CurrentSourceReason =
  | 'metar_ok'
  | 'metar_too_far'
  | 'metar_unavailable'
  | 'metar_stale'
  | 'metar_missing_fields'

export type PossibleChangeReason = 'wind' | 'rain' | 'storm'

/** Airport whose METAR feeds the dashboard "now" (only with source "metar"). */
export interface CurrentStation {
  icao: string
  name: string
  distance_km: number
}

/** Notices about the "now": codes and values only, the frontend writes the text. */
export type CurrentNotice =
  | { code: 'model_temp_differs'; model_temp_c: number }
  | {
      code: 'possible_change'
      reasons: PossibleChangeReason[]
      model_wind_speed_kmh: number | null
      model_wind_gust_kmh: number | null
      model_precip_1h_mm: number | null
      model_weather_code: number | null
    }
  | { code: 'reported_phenomenon'; kind: 'rain' | 'storm'; wx: string }

export interface CurrentDetailed {
  temp_c: number | null
  feels_like_c: number | null
  humidity: number | null
  wind_speed_kmh: number | null
  /** null with variable (VRB) or calm wind in the METAR. */
  wind_dir_deg: number | null
  wind_dir_cardinal: string | null
  uv_index: number | null
  description: string
  icon: string
  is_day: boolean
  source?: CurrentSource
  /** Real UTC time of the data: METAR obsTime, Open-Meteo current.time or the SMN observation. */
  observed_at?: string | null
  wind_icon: string | null
  wind_intensity: string | null
  stale?: boolean
  wind_gust_kmh?: number | null
  station?: CurrentStation | null
  /** Model temperature, only with source "metar". */
  model_temp_c?: number | null
  source_reason?: CurrentSourceReason | null
  notices?: CurrentNotice[]
}

export interface HourlyConsensus {
  entries: HourlyEntry[]
}

export interface WeatherDashboardResponse {
  location: { lat: number; lon: number; city: string | null }
  current: CurrentDetailed
  day_arc: DayArcInfo
  moon_phase: MoonPhaseInfo
  snow_level_m: number | null
  rain_today: RainForecastInfo
  hourly: HourlyConsensus
  forecast_7d: DailyEntry[]
  /** Models that contributed to `forecast_7d`; one entry when the other model did not answer. */
  forecast_models: ForecastModelName[]
  fetched_at: string
  // Todo el pronóstico sale de Open-Meteo.
  forecast_source?: 'openmeteo'
  degraded?: boolean
}

// ── Fire Danger schemas ───────────────────────────────────────────────────────

export interface FireDangerSlot {
  date: string
  hour_label: string
  fwi: number | null
  fire_risk_score: number
  fire_risk_label: string
  temp_c: number | null
  humidity: number | null
  wind_kmh: number | null
  precip_mm: number | null
  is_estimated: boolean
}

export interface FireDangerResponse {
  slots: FireDangerSlot[]
  current_score: number
  current_label: string
  current_color: string
  peak_score: number
  peak_label: string
  peak_hour_label: string
  source: string
  is_estimated: boolean
}

// ── Niebla / Visibilidad schemas ──────────────────────────────────────────────

export interface VisibilityHourlySlot {
  hour_label: string
  visibility_m: number | null
  fog_level: number
  fog_label: string
  fog_color: string
}

export interface NieblaResponse {
  visibility_m: number | null
  fog_level: number
  fog_label: string
  fog_color: string
  weather_code: number | null
  hourly: VisibilityHourlySlot[]
  source?: string               // "metar" | "openmeteo"
  metar_station?: string | null
  metar_station_name?: string | null
  metar_distance_km?: number | null
  hourly_source?: string        // "taf" | "openmeteo_inference" | "openmeteo"
}

// ── METAR/TAF crudo (código aeronáutico) ─────────────────────────────────────

export interface MetarRawResponse {
  data?: (string | { raw_text?: string })[]
}

// ── Altitud de densidad (POST /api/v1/aeronautica/density-altitude) ──────────

export type AircraftModel = 'piston' | 'turboprop'
export type DensityRisk = 'verde' | 'amarillo' | 'naranja' | 'rojo'

export interface DensityAltitudeRequest {
  elev_ft: number
  qnh_hpa: number
  oat_c: number
  td_c: number
  wl_nom: number
  ias_kt: number
  aircraft_model: AircraftModel
}

export type DensityRiskCode =
  | 'NORMAL'
  | 'REDUCED_PERFORMANCE_MARGIN'
  | 'UNFAVORABLE_PERFORMANCE'
  | 'SPECIFIC_EVALUATION_REQUIRED'

export interface DensityAltitudeCalculations {
  pressure_altitude_ft: number
  isa_temperature_c: number
  station_pressure_hpa: number
  vapor_pressure_hpa: number
  virtual_temperature_c: number
  density_altitude_ft: number
  sigma: number
  tas_kt: number
  /** Índice operacional wl_nom / sigma — NO es el wing loading físico (W/S). */
  density_adjusted_wing_loading: number
}

export interface DensityAltitudeResponse {
  inputs: DensityAltitudeRequest
  calculations: DensityAltitudeCalculations
  risk: { level: DensityRisk; code: DensityRiskCode; message: string }
  flare_loss_pct: number
  takeoff_run_increase_pct: number
  engine_power_loss_pct: number | null
  /** Siempre null: no hay fórmula aprobada de tasa de ascenso. */
  roc: null
}

// ── METAR decodificado (GET /api/metar?icao=…) ───────────────────────────────

/** Subconjunto del METAR decodificado de CheckWX: solo lo que usa la precarga del viento de superficie. */
export interface MetarWindData {
  degrees?: number | null
  direction?: string | null
  speed_kts?: number | null
  gust_kts?: number | null
}

export interface MetarDecodedEntry {
  icao?: string
  raw_text?: string
  wind?: MetarWindData | null
  /** Hora de emisión del METAR (campo `observed` de CheckWX, ISO en UTC); la precarga la usa para avisar si es vieja. */
  observed?: string | null
}

export interface MetarDecodedResponse {
  data?: MetarDecodedEntry[]
}

/** GET /api/metar/nearest: aeropuerto argentino más cercano y distancia real (lookup puro, sin cuota). */
export interface NearestAirportResponse {
  icao: string
  name: string
  lat: number
  lon: number
  distance_km: number
}

// ── Cizalladura / LLWS (POST /api/v1/aeronautica/wind-shear) ─────────────────

export type WindShearLevel = 'verde' | 'amarillo' | 'naranja' | 'rojo'
export type WindShearRiskCode = 'SHEAR_LIGHT' | 'SHEAR_MODERATE' | 'SHEAR_SEVERE' | 'SHEAR_EXTREME'
export type WindShearDriverCode = 'shear' | 'gust_spread'
export type WindShearThermalCode = 'inversion' | 'unstable' | 'neutral'

/** Dirección en grados meteorológicos (DESDE donde sopla), rapidez en kt, temperaturas en °C. */
export interface WindShearRequest {
  surface_wind_dir_deg: number
  surface_wind_speed_kt: number
  surface_gust_kt: number | null
  wind_500ft_dir_deg: number
  wind_500ft_speed_kt: number
  /** El viento a 1.000 ft va completo (dirección + rapidez) o ninguno. */
  wind_1000ft_dir_deg: number | null
  wind_1000ft_speed_kt: number | null
  /** Las dos temperaturas van juntas o ninguna. */
  surface_temp_c: number | null
  temp_1000ft_c: number | null
}

export interface WindShearLayer {
  from_ft: number
  to_ft: number
  /** |V_top − V_bottom| (módulo vectorial) por cada 100 ft. */
  shear_kt_per_100ft: number
}

export interface WindShearThermal {
  code: WindShearThermalCode
  /** Temperatura de superficie menos la de 1.000 ft (°C por 1.000 ft). */
  lapse_c_per_1000ft: number
}

export interface WindShearCalculations {
  layers: WindShearLayer[]
  max_shear_kt_per_100ft: number
  max_layer: { from_ft: number; to_ft: number }
  /** Ráfaga menos viento sostenido en superficie; 0 sin ráfaga. */
  gust_spread_kt: number
  /** null si no se enviaron las dos temperaturas. Informativa: no modifica el nivel. */
  thermal: WindShearThermal | null
}

export interface WindShearResponse {
  inputs: WindShearRequest
  calculations: WindShearCalculations
  risk: { level: WindShearLevel; code: WindShearRiskCode; message: string }
  /** Condiciones que alcanzan el umbral del nivel elegido; vacío en verde. */
  drivers: WindShearDriverCode[]
}

// Alertas push (FRA-353, FRA-354): espejo de apps/backend/app/schemas/alertas.py.

/** Lo que devuelve `PushSubscription.toJSON()` más la ciudad (slug de `ZONAS_ALERTAS`). */
export interface AlertaSuscripcionRequest {
  endpoint: string
  keys: { p256dh: string; auth: string }
  zona: string
}

export interface AlertaSuscripcionResponse {
  /** Identificador de la suscripción, 22 caracteres base64url; sirve para la baja y la prueba. */
  id: string
  zona: string
}

export interface AlertaBajaRequest {
  id: string
}

export interface AlertaPruebaRequest {
  id: string
}

export interface AlertaPruebaResponse {
  /** El servicio push aceptó el aviso de prueba (aún puede tardar en llegar). */
  enviada: boolean
}

// ── API client ────────────────────────────────────────────────────────────────

export const api = {
  weatherCurrent: (lat: number, lon: number) =>
    request<WeatherCurrentResponse>('/api/weather/current', { lat, lon }),

  tenderRopa: (lat: number, lon: number) =>
    request<ToolResult>('/api/tools/tender-ropa', { lat, lon }),

  sensacionTermica: (lat: number, lon: number) =>
    request<FeelsLikeResponse>('/api/tools/sensacion-termica', { lat, lon }),

  cotaDeNieve: (lat: number, lon: number) =>
    request<SnowLevelResponse>('/api/tools/cota-de-nieve', { lat, lon }),

  hacerDeporte: (lat: number, lon: number) =>
    request<ToolResult>('/api/tools/hacer-deporte', { lat, lon }),

  earthquakes: (lat: number, lon: number, radius_km = 500) =>
    request<EarthquakesResponse>('/api/earthquakes/recent', { lat, lon, radius_km }),

  lavarCoche: (lat: number, lon: number) =>
    request<CarWashForecastResponse>('/api/tools/lavar-coche', { lat, lon }),

  weatherDashboard: (lat: number, lon: number, model: 'gfs' | 'ecmwf' | 'consensus' = 'consensus') =>
    request<WeatherDashboardResponse>('/api/weather/dashboard', { lat, lon, model }),

  laundryForecast: (lat: number, lon: number) =>
    request<LaundryForecastResponse>('/api/tools/tender-ropa/forecast', { lat, lon }),

  volcanes: () =>
    request<VolcanesResponse>('/api/volcanes'),

  /** Con coordenadas, solo los avisos cuya área contiene ese punto; sin ellas, todos los del país. */
  alertasSmn: (lat?: number, lon?: number) =>
    request<SmnAlertasResponse>('/api/alertas-smn', lat !== undefined && lon !== undefined ? { lat, lon } : undefined),

  fireDanger: (lat: number, lon: number) =>
    request<FireDangerResponse>('/api/incendios', { lat, lon }),

  niebla: (lat: number, lon: number) =>
    request<NieblaResponse>('/api/niebla', { lat, lon }),

  densityAltitude: (body: DensityAltitudeRequest, signal?: AbortSignal) =>
    postJson<DensityAltitudeResponse>('/api/v1/aeronautica/density-altitude', body, signal),

  windShear: (body: WindShearRequest, signal?: AbortSignal) =>
    postJson<WindShearResponse>('/api/v1/aeronautica/wind-shear', body, signal),

  /** METAR decodificado — a demanda (cuota diaria de CheckWX: 198/200). */
  metarDecoded: (icao: string) =>
    request<MetarDecodedResponse>('/api/metar', { icao }),

  /** Aeropuerto AR más cercano a un punto — no consume cuota (no llama a CheckWX). */
  metarNearest: (lat: number, lon: number) =>
    request<NearestAirportResponse>('/api/metar/nearest', { lat, lon }),

  /** TAF en código aeronáutico crudo — a demanda, para no consumir la cuota diaria de CheckWX (198/200 por día). */
  tafRaw: (icao: string) =>
    request<MetarRawResponse>('/api/metar', { icao, type: 'taf' }),

  /** TAF decodificado por períodos (Aviation Weather Center, no gasta cupo de CheckWX). 404 = el aeródromo no publica TAF. */
  tafDecoded: (icao: string) =>
    request<TafDecoded>('/api/taf', { icao }),

  /**
   * Alta (o renovación) de la suscripción push a una ciudad. Repetirla con el mismo endpoint es un upsert:
   * devuelve el mismo `id`. Errores como `ApiError`: 422 datos inválidos, 429 (con `retryAfter`), 503 sin servicio o tope.
   */
  alertasSuscribir: (body: AlertaSuscripcionRequest) =>
    postJsonConTope<AlertaSuscripcionResponse>('/api/alertas/suscripcion', body),

  /** Baja por `id`. El backend contesta 204 sin cuerpo, también para un `id` desconocido. */
  alertasBaja: (body: AlertaBajaRequest) =>
    postSinCuerpo('/api/alertas/baja', body),

  /**
   * Aviso de prueba a una suscripción. Errores como `ApiError`: 404 no existe, 410 vencida (el servidor ya
   * la borró), 429 (una por minuto, con `retryAfter`), 502 el servicio push falló, 503 sin servicio.
   */
  alertasPrueba: (body: AlertaPruebaRequest) =>
    postJsonConTope<AlertaPruebaResponse>('/api/alertas/prueba', body),
}
