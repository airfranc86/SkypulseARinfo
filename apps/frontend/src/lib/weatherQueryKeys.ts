/**
 * The key of the forecast dashboard in React Query's cache. It is shared on purpose: every page that loads the
 * dashboard (`useWeatherDashboard`) and Mora's floating bubble, which only READS the cache (`useHumorMora`), must land
 * on the same entry. Keeping it in one function means a swapped argument or another model cannot drift apart between
 * the two sides without a test noticing.
 */

export type ModeloDashboard = 'gfs' | 'ecmwf' | 'consensus'

export function weatherDashboardQueryKey(lat: number | null, lon: number | null, model: ModeloDashboard) {
  return ['weather-dashboard', lat, lon, model] as const
}
