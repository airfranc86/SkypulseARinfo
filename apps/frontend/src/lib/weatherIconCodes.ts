/**
 * Valid `WeatherIcon` codes (one per bundled Meteocons SVG). Kept in a pure module, with no React
 * or SVG imports, so tests and the label-to-icon mappings can validate against it.
 */
export const WEATHER_ICON_CODES = [
  'clear-day',
  'clear-night',
  'partly-cloudy-day',
  'partly-cloudy-night',
  'overcast',
  'overcast-day',
  'overcast-night',
  'fog',
  'fog-day',
  'fog-night',
  'drizzle',
  'overcast-drizzle',
  'partly-cloudy-day-drizzle',
  'partly-cloudy-night-drizzle',
  'rain',
  'partly-cloudy-day-rain',
  'partly-cloudy-night-rain',
  'snow',
  'partly-cloudy-day-snow',
  'partly-cloudy-night-snow',
  'sleet',
  'thunderstorms',
  'thunderstorms-day',
  'thunderstorms-night',
  'hail',
  // The backend picks these by WMO code and cloud cover (sun with showers, storms or hail).
  'mostly-clear-day',
  'mostly-clear-night',
  'mostly-clear-day-rain',
  'mostly-clear-night-rain',
  'mostly-clear-day-snow',
  'mostly-clear-night-snow',
  'thunderstorms-mostly-clear-day',
  'thunderstorms-mostly-clear-night',
  'thunderstorms-mostly-clear-day-hail',
  'thunderstorms-mostly-clear-night-hail',
  'thunderstorms-day-hail',
  'thunderstorms-night-hail',
  'thunderstorms-overcast-hail',
  'thermometer',
  'humidity',
  'wind',
  'wind-beaufort-5',
  'wind-beaufort-6',
  'wind-beaufort-7',
  'wind-beaufort-8',
  'wind-beaufort-9',
  'wind-beaufort-10',
  'wind-beaufort-11',
  'wind-beaufort-12',
  'uv-index',
  'sunrise',
  'sunset',
  'moon-new',
  'moon-waxing-crescent',
  'moon-first-quarter',
  'moon-waxing-gibbous',
  'moon-full',
  'moon-waning-gibbous',
  'moon-last-quarter',
  'moon-waning-crescent',
] as const

export type WeatherIconCode = (typeof WEATHER_ICON_CODES)[number]

const VALID_CODES: ReadonlySet<string> = new Set(WEATHER_ICON_CODES)

export function isWeatherIconCode(code: string): code is WeatherIconCode {
  return VALID_CODES.has(code)
}
