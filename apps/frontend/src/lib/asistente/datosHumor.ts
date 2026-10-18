/**
 * What Mora's mood depends on, read from what the app already has: the forecast dashboard and the SMN warnings that
 * React Query keeps in its cache. Pure (no React, no timers, no network): the caller passes the data and the clock.
 *
 * The floating bubble never asks for anything (Open-Meteo's quota is shared by every page); it only looks at what
 * another page already loaded. No dashboard in the cache means everything is unknown and `humorDesdeClima` answers
 * `reposo`.
 */

import type { SmnAlertasResponse, WeatherDashboardResponse } from '../api.ts'
import { entriesFromNow } from '../weatherVerdict.ts'
import type { DatosHumor } from './humor.ts'

/** Every field unknown: what the bubble has before any page loaded a forecast. */
const DESCONOCIDO: DatosHumor = Object.freeze({
  alertas: null,
  riesgoConvectivo: null,
  panel: null,
  esDeDia: null,
  rafagaKmh: null,
  intensidadViento: null,
  icono: null,
  precipMm: null,
})

/**
 * How old data may be before it counts as unknown. The bubble keeps the cache entry alive and never asks again, so
 * `current` (day or night, gust, icon) and the warnings freeze at the moment they were loaded: a user who loads the
 * home page at 18:00 and stays three hours on a page without a forecast must not see Mora glide at 21:00.
 */
const EDAD_MAXIMA_MS = 3 * 3_600_000

/** Older than `EDAD_MAXIMA_MS`. An unreadable date (or clock) is not "old": its age is unknown, not too big. */
export function esViejo(cargadoEn: string | null | undefined, ahoraMs: number): boolean {
  const cargado = Date.parse(cargadoEn ?? '')
  return Number.isFinite(cargado) && Number.isFinite(ahoraMs) && ahoraMs - cargado > EDAD_MAXIMA_MS
}

/**
 * The mood data for this forecast.
 *
 * - The current slot is the first one that has not ended yet (`entriesFromNow`: the hour that started up to an hour
 *   ago, or a later one). `riesgoConvectivo` and `precipMm` come from it; with no slot left they stay unknown.
 * - Day or night comes from the current slot (it follows the clock) and, without it, from `current`; the gust, the
 *   wind intensity and the icon come from `current`. A missing value is `null`.
 * - A dashboard (or a warnings answer) older than three hours is unknown: see `EDAD_MAXIMA_MS`.
 * - The warnings pass through only when the SMN feed answered. A feed that did not answer is "unknown" (`null`),
 *   never "no warnings".
 * - The panel moods (pensando, respondiendo, confundido) are set by the panel, never by the weather: here `panel`
 *   is always `null`.
 */
export function datosHumorDesde(
  dashboard: WeatherDashboardResponse | null | undefined,
  avisos: SmnAlertasResponse | null | undefined,
  ahoraMs: number,
): DatosHumor {
  if (!dashboard || esViejo(dashboard.fetched_at, ahoraMs)) return DESCONOCIDO
  const franja = entriesFromNow(dashboard.hourly.entries, ahoraMs)[0]
  const actual = dashboard.current
  return {
    alertas: avisos && avisos.available && !esViejo(avisos.fetched_at, ahoraMs) ? avisos.alertas : null,
    riesgoConvectivo: franja?.convective_risk ?? null,
    panel: null,
    esDeDia: typeof franja?.is_day === 'boolean' ? franja.is_day : typeof actual.is_day === 'boolean' ? actual.is_day : null,
    rafagaKmh: actual.wind_gust_kmh ?? null,
    intensidadViento: actual.wind_intensity ?? null,
    icono: actual.icon ?? null,
    precipMm: franja?.precip_mm ?? null,
  }
}
