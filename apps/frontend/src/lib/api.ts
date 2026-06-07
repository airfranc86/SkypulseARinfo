const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

if (import.meta.env.PROD && !BASE_URL) {
  throw new Error('[SkyPulse] VITE_API_BASE_URL is not set. Configure it in Vercel environment variables.')
}

/** Error de API con status HTTP — permite distinguir 503 (cold start de Render) de otros fallos. */
export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
  }
  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError((body as { detail?: string }).detail ?? `HTTP ${res.status}`, res.status)
  }
  return res.json()
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

export type AlertLevel = 'verde' | 'amarillo' | 'naranja' | 'rojo'

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
  total: number
  has_active_alert: boolean
  volcanes: Volcan[]
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
  confidence_pct: number
  confidence_label: 'ALTA' | 'MEDIA' | 'BAJA'
  wind_dir_dominant_deg: number | null
  wind_dir_cardinal: string | null
  wind_icon: string | null
  wind_intensity: string | null
  wind_shift: boolean
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

export interface CurrentDetailed {
  temp_c: number | null
  feels_like_c: number | null
  humidity: number | null
  wind_speed_kmh: number | null
  wind_dir_deg: number | null
  wind_dir_cardinal: string | null
  uv_index: number | null
  description: string
  icon: string
  is_day: boolean
  source?: string  // "smn" | "openmeteo" | "unknown"
  observed_at?: string  // ISO datetime of the SMN observation
  wind_icon: string | null
  wind_intensity: string | null
}

export interface HourlyConsensus {
  entries: HourlyEntry[]
  rain_consensus_label: string
  rain_probability_pct: number
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
  fetched_at: string
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

  fireDanger: (lat: number, lon: number) =>
    request<FireDangerResponse>('/api/incendios', { lat, lon }),

  niebla: (lat: number, lon: number) =>
    request<NieblaResponse>('/api/niebla', { lat, lon }),
}
