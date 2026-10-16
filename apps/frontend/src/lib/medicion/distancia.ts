/**
 * Distance helpers for the map measuring tool. Pure module (no React, no Leaflet, no `window`), so
 * `node --test` can check every rule.
 *
 * Distances use the haversine formula with R = 6371 km, the same radius Leaflet uses (`CRS.Earth`)
 * and the same formula as the backend (`apps/backend/app/services/smn.py`). It works on lat/lon, so
 * Web Mercator only distorts how long a segment looks on screen, never the value. Against the WGS84
 * ellipsoid the difference can reach ~0.5 %, which the panel states ("aproximada").
 */

export interface LatLon {
  readonly lat: number
  readonly lon: number
}

const EARTH_RADIUS_KM = 6371
const DEG_TO_RAD = Math.PI / 180
const RAD_TO_DEG = 180 / Math.PI

/** Below this many meters the length is shown with one decimal; from here on, whole kilometers. */
const WHOLE_KM_FROM_M = 9950

const UN_DECIMAL = new Intl.NumberFormat('es-AR', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
  useGrouping: 'always',
})
// `useGrouping: 'always'` so "1.000" does not depend on the locale's minimum grouping digits.
const KM_ENTEROS = new Intl.NumberFormat('es-AR', { maximumFractionDigits: 0, useGrouping: 'always' })

/** Great-circle distance in km between two points. Symmetric; 0 for the same point. */
export function haversineKm(a: LatLon, b: LatLon): number {
  const lat1 = a.lat * DEG_TO_RAD
  const lat2 = b.lat * DEG_TO_RAD
  const dLat = lat2 - lat1
  const dLon = (b.lon - a.lon) * DEG_TO_RAD
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** Length of the path through `puntos`, in km. 0 with fewer than two points. */
export function totalKm(puntos: ReadonlyArray<LatLon>): number {
  let suma = 0
  for (let i = 1; i < puntos.length; i += 1) suma += haversineKm(puntos[i - 1], puntos[i])
  return suma
}

/**
 * Points along the great circle from `a` to `b`, `max(1, ceil(d / pasoKm))` segments, so a long leg
 * is drawn as a curve instead of a straight line on the Mercator map. The first and last points
 * are copies of the endpoints (exact, never recomputed). Always returns new objects.
 *
 * Preconditions: longitudes already wrapped to [-180, 180] and the points not antipodal. The map
 * guarantees both (`maxBounds` and `latlng.wrap()`). A `pasoKm` that is not a finite number above 0
 * returns just the two endpoints instead of looping.
 */
export function densificar(a: LatLon, b: LatLon, pasoKm: number): LatLon[] {
  const distancia = haversineKm(a, b)
  const validoPaso = Number.isFinite(pasoKm) && pasoKm > 0
  const segmentos = validoPaso ? Math.max(1, Math.ceil(distancia / pasoKm)) : 1
  const angulo = distancia / EARTH_RADIUS_KM
  const seno = Math.sin(angulo)
  const puntos: LatLon[] = [{ lat: a.lat, lon: a.lon }]
  if (seno > 0) {
    const lat1 = a.lat * DEG_TO_RAD
    const lon1 = a.lon * DEG_TO_RAD
    const lat2 = b.lat * DEG_TO_RAD
    const lon2 = b.lon * DEG_TO_RAD
    for (let i = 1; i < segmentos; i += 1) {
      const f = i / segmentos
      const k1 = Math.sin((1 - f) * angulo) / seno
      const k2 = Math.sin(f * angulo) / seno
      const x = k1 * Math.cos(lat1) * Math.cos(lon1) + k2 * Math.cos(lat2) * Math.cos(lon2)
      const y = k1 * Math.cos(lat1) * Math.sin(lon1) + k2 * Math.cos(lat2) * Math.sin(lon2)
      const z = k1 * Math.sin(lat1) + k2 * Math.sin(lat2)
      puntos.push({ lat: Math.atan2(z, Math.hypot(x, y)) * RAD_TO_DEG, lon: Math.atan2(y, x) * RAD_TO_DEG })
    }
  } else {
    // Same point: a single segment, nothing to interpolate (`segmentos` is 1 here).
  }
  puntos.push({ lat: b.lat, lon: b.lon })
  return puntos
}

/**
 * Human text for a length in km, es-AR. Rounded from whole meters so the 9.95 km edge does not
 * depend on the binary value of 9.95: under 9,950 m one decimal ("8,4 km"), from there whole km
 * with a thousands dot ("1.632 km"). `NaN`, infinite or negative → "—".
 */
export function formatearKm(km: number): string {
  if (!Number.isFinite(km) || km < 0) return '—'
  const metros = Math.round(km * 1000) + 0 // `+ 0` turns -0 into 0 so it never prints "-0,0"
  if (metros < WHOLE_KM_FROM_M) return `${UN_DECIMAL.format(Math.round(metros / 100) / 10)} km`
  return `${KM_ENTEROS.format(Math.round(km))} km`
}
