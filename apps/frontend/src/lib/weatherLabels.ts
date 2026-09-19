import type { WeatherDashboardResponse } from '@/lib/api'

/** Orden importa: "thunderstorms" se evalúa antes que "rain" para los íconos combinados. */
const PRECIP_KINDS: ReadonlyArray<readonly [string, string]> = [
  ['thunderstorm', 'Tormenta'],
  ['hail', 'Granizo'],
  ['sleet', 'Aguanieve'],
  ['snow', 'Nieve'],
  ['drizzle', 'Llovizna'],
  ['rain', 'Lluvia'],
]

/** Tipo de precipitación que muestra un código de ícono, o null si el ícono no muestra ninguna. */
export function precipKind(code: string): string | null {
  return PRECIP_KINDS.find(([key]) => code.includes(key))?.[1] ?? null
}

function skyKind(code: string): string | null {
  if (code.startsWith('partly-cloudy')) return 'parcialmente nublado'
  if (code.startsWith('overcast')) return 'nublado'
  if (code.startsWith('fog')) return 'niebla'
  if (code.startsWith('clear')) return 'despejado'
  return null
}

/**
 * Condición del cielo en palabras para un código de ícono del backend.
 * Devuelve null si el código no describe el cielo (viento, UV, luna, salida del sol):
 * en ese caso el ícono sigue siendo decorativo.
 */
export function describeWeatherIcon(code: string): string | null {
  const precip = precipKind(code)
  const sky = skyKind(code)
  if (precip) return sky === 'parcialmente nublado' ? `${precip}, parcialmente nublado` : precip
  if (!sky) return null
  return sky.charAt(0).toUpperCase() + sky.slice(1)
}

/** Hora del reloj argentina ("19:47") de un ISO del backend, o null si no es una fecha válida. */
export function formatClock(iso: string | undefined | null): string | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleTimeString('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'America/Argentina/Buenos_Aires',
  })
}

type StatusInput = Pick<WeatherDashboardResponse, 'degraded'> & {
  current: Pick<WeatherDashboardResponse['current'], 'stale'>
}

/**
 * Avisos de estado de los datos, en hechos. Vacío cuando todo llegó completo. Ya no hay avisos por
 * "GFS (Windy) no respondió": Open-Meteo es la única fuente del pronóstico y, si falla, no hay
 * pronóstico (el backend responde 503) en vez de un pronóstico armado con otra fuente.
 */
export function forecastNotes(data: StatusInput): string[] {
  const notes: string[] = []
  if (data.current.stale) {
    notes.push('La observación actual puede no estar al día.')
  }
  if (data.degraded && notes.length === 0) {
    notes.push('Alguna fuente no respondió: el pronóstico puede diferir de lo habitual.')
  }
  return notes
}
