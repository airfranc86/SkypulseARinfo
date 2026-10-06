// TAF decodificado (FRA-365): tipos del contrato de GET /api/taf y textos en español para mostrarlo.
//
// Módulo puro y sin dependencias de la app (ni api.ts), así se prueba con `node --test`.
// Las horas se muestran en hora de Argentina y en UTC, nunca en la zona del dispositivo: el TAF
// se emite en UTC y quien lo lee necesita el mismo reloj que el pronóstico del resto del sitio.

export interface TafWind {
  direction_deg: number | null
  variable: boolean
  speed_kt: number | null
  gust_kt: number | null
}

export interface TafCloud {
  cover: string
  base_ft: number | null
  kind: string | null
}

export interface TafTemperature {
  kind: string
  celsius: number
  valid_at: string
}

export interface TafPeriod {
  change: string
  probability: number | null
  valid_from: string
  valid_to: string
  becoming_by: string | null
  wind: TafWind | null
  visibility_m: number | null
  visibility_over: boolean
  clouds: TafCloud[]
  weather: string[]
  flight_category: string | null
  inherited: string[]
}

export interface TafDecoded {
  icao: string
  name: string | null
  issued_at: string | null
  valid_from: string | null
  valid_to: string | null
  raw: string
  periods: TafPeriod[]
  temperatures: TafTemperature[]
  source: string
}

export const TAF_ZONE = 'America/Argentina/Buenos_Aires'

export const FLIGHT_CATEGORY_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  VFR: { color: '#3ecf7a', bg: 'rgba(62,207,122,.12)', border: 'rgba(62,207,122,.4)' },
  MVFR: { color: '#5aaad8', bg: 'rgba(43,143,212,.12)', border: 'rgba(43,143,212,.4)' },
  IFR: { color: '#e05545', bg: 'rgba(192,57,43,.12)', border: 'rgba(192,57,43,.4)' },
  LIFR: { color: '#cc66ff', bg: 'rgba(204,102,255,.12)', border: 'rgba(204,102,255,.4)' },
  UNKNOWN: { color: '#90aabb', bg: 'rgba(96,112,128,.12)', border: 'rgba(96,112,128,.4)' },
}

// ------------------------------------------------------------------ números

/** 3500 -> "3.500" (separador de miles argentino, sin depender del ICU del navegador). */
function thousands(value: number): string {
  return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

// ------------------------------------------------------------------ viento

const CARDINALS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO']

function cardinal(degrees: number): string {
  return CARDINALS[Math.round((((degrees % 360) + 360) % 360) / 22.5) % 16]
}

export function windText(wind: TafWind | null): string {
  if (!wind) return 'Sin dato'
  const { direction_deg: dir, variable, speed_kt: speed, gust_kt: gust } = wind
  if (speed === 0 && !gust) return 'Calmo'
  const gusts = gust ? `, ráfagas de ${gust} kt` : ''
  if (variable) return `Variable a ${speed ?? '?'} kt${gusts}`
  if (dir === null) return speed === null ? 'Sin dato' : `${speed} kt${gusts}`
  return `${cardinal(dir)} (${String(Math.round(dir)).padStart(3, '0')}°) a ${speed ?? '?'} kt${gusts}`
}

// ------------------------------------------------------------------ visibilidad

export function visibilityText(meters: number | null, over: boolean): string {
  if (over) return '10 km o más'
  if (meters === null) return 'Sin dato'
  if (meters < 1000) return `${Math.round(meters)} m`
  return `${String(Math.round(meters / 100) / 10).replace('.', ',')} km`
}

// ------------------------------------------------------------------ nubes

const COVER_TEXT: Record<string, string> = {
  FEW: 'Pocas nubes',
  SCT: 'Nubes dispersas',
  BKN: 'Nubes fragmentadas',
  OVC: 'Cielo cubierto',
}
const KIND_TEXT: Record<string, string> = {
  CB: 'cumulonimbus (CB)',
  TCU: 'cúmulos en torre (TCU)',
}

export function cloudsText(clouds: TafCloud[]): string[] {
  return clouds.map(({ cover, base_ft: base, kind }) => {
    const code = cover.toUpperCase()
    if (code === 'NSC') return 'Sin nubes significativas'
    if (code === 'CLR' || code === 'SKC') return 'Despejado'
    if (code === 'VV') {
      return base === null ? 'Cielo oscurecido' : `Cielo oscurecido (visibilidad vertical ${thousands(base)} ft)`
    }
    const name = COVER_TEXT[code] ?? code
    const at = base === null ? '' : ` a ${thousands(base)} ft`
    const extra = kind && KIND_TEXT[kind.toUpperCase()] ? ` · ${KIND_TEXT[kind.toUpperCase()]}` : ''
    return `${name}${at}${extra}`
  })
}

// ------------------------------------------------------------------ fenómenos

const DESCRIPTORS: Record<string, string> = {
  TS: 'tormenta',
  SH: 'chubascos',
  FZ: 'engelante',
  MI: 'poco profunda',
  BC: 'en bancos',
  PR: 'parcial',
  DR: 'baja',
  BL: 'elevada por el viento',
}
const PHENOMENA: Record<string, string> = {
  RA: 'lluvia',
  DZ: 'llovizna',
  SN: 'nieve',
  SG: 'granos de nieve',
  IC: 'cristales de hielo',
  PL: 'hielo granulado',
  GR: 'granizo',
  GS: 'granizo pequeño',
  UP: 'precipitación desconocida',
  BR: 'neblina',
  FG: 'niebla',
  FU: 'humo',
  VA: 'ceniza volcánica',
  DU: 'polvo',
  SA: 'arena',
  HZ: 'calima',
  PO: 'remolinos de polvo',
  SQ: 'turbonada',
  FC: 'tornado o tromba',
  SS: 'tormenta de arena',
  DS: 'tormenta de polvo',
}

function describeWeatherToken(token: string): string {
  let rest = token.trim().toUpperCase()
  if (rest === 'NSW') return 'Sin fenómenos significativos'
  let intensity = ''
  if (rest.startsWith('+')) intensity = ' fuerte'
  if (rest.startsWith('-')) intensity = ' leve'
  rest = rest.replace(/^[+-]/, '')
  const vicinity = rest.startsWith('VC')
  if (vicinity) rest = rest.slice(2)
  const pairs = rest.match(/.{2}/g)
  if (!pairs || pairs.join('') !== rest) return token

  const descriptor = DESCRIPTORS[pairs[0]] ? pairs.shift() : undefined
  const phenomena = pairs.map(code => PHENOMENA[code])
  if (phenomena.some(name => !name)) return token
  const joined = phenomena.join(' y ')

  let text: string
  if (descriptor === 'TS') text = joined ? `tormenta con ${joined}` : 'tormenta'
  else if (descriptor === 'SH') text = joined ? `chubascos de ${joined}` : 'chubascos'
  else if (descriptor) text = joined ? `${joined} ${DESCRIPTORS[descriptor]}` : ''
  else text = joined
  if (!text) return token
  return `${text}${intensity}${vicinity ? ' en las cercanías' : ''}`
}

export function weatherText(codes: string[]): string[] {
  return codes.map(describeWeatherToken)
}

// ------------------------------------------------------------------ grupos de cambio

/** CAVOK: AWC lo manda como 6 millas o más, sin nubes significativas y sin fenómenos. */
export function isCavok(period: TafPeriod): boolean {
  return (
    period.visibility_over &&
    period.clouds.length > 0 &&
    period.clouds.every(c => c.cover.toUpperCase() === 'NSC') &&
    period.weather.every(w => w.toUpperCase() === 'NSW')
  )
}

export function changeLabel(period: TafPeriod): string {
  const chance = period.probability ? `${period.probability} % de probabilidad` : null
  switch (period.change) {
    case 'initial':
      return 'Condición base'
    case 'from':
      return 'A partir de entonces'
    case 'becoming':
      return 'Cambio gradual'
    case 'tempo':
      return chance ? `Temporalmente · ${chance}` : 'Temporalmente'
    case 'prob':
      return chance ?? 'Probable'
    default:
      return period.change
  }
}

/** CB, TCU o tormenta: lo que más importa al planificar un vuelo. */
export function hasConvectiveSigns(period: TafPeriod): boolean {
  return (
    period.clouds.some(c => c.kind === 'CB' || c.kind === 'TCU') ||
    period.weather.some(w => w.toUpperCase().includes('TS'))
  )
}

// ------------------------------------------------------------------ horas

const LOCAL_PARTS = new Intl.DateTimeFormat('es-AR', {
  timeZone: TAF_ZONE,
  weekday: 'short',
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
})

interface LocalStamp {
  day: string
  stamp: string
  time: string
}

function localStamp(iso: string): LocalStamp {
  const parts = Object.fromEntries(LOCAL_PARTS.formatToParts(new Date(iso)).map(p => [p.type, p.value]))
  const weekday = String(parts.weekday).replace(/\.$/, '')
  const day = `${parts.day}/${parts.month}`
  const time = `${parts.hour}:${parts.minute}`
  return { day, stamp: `${weekday} ${day} ${time}`, time }
}

function utcStamp(iso: string): string {
  const date = new Date(iso)
  const dd = String(date.getUTCDate()).padStart(2, '0')
  const hh = String(date.getUTCHours()).padStart(2, '0')
  return `${dd}/${hh}Z`
}

export function formatWindow(period: Pick<TafPeriod, 'valid_from' | 'valid_to'>): { local: string; utc: string } {
  const from = localStamp(period.valid_from)
  const to = localStamp(period.valid_to)
  const end = from.day === to.day ? to.time : to.stamp
  return {
    local: `${from.stamp} → ${end}`,
    utc: `${utcStamp(period.valid_from)} → ${utcStamp(period.valid_to)}`,
  }
}

/** Un instante en hora de Argentina, por ejemplo "mié 07/10 02:00". */
export function formatLocalInstant(iso: string): string {
  return localStamp(iso).stamp
}

export function formatTemperature(temperature: TafTemperature): string {
  const label = temperature.kind === 'max' ? 'Máxima' : 'Mínima'
  return `${label} ${Math.round(temperature.celsius)} °C · ${localStamp(temperature.valid_at).stamp}`
}

// ------------------------------------------------------------------ categoría de vuelo (FAA, millas)

const CATEGORY_NOTES: Record<string, string> = {
  VFR: 'VFR: visibilidad de más de 5 millas (8 km) y techo sobre 3.000 ft',
  MVFR: 'MVFR: visibilidad de 3 a 5 millas (4,8 a 8 km) o techo de 1.000 a 3.000 ft',
  IFR: 'IFR: visibilidad de 1 a 3 millas (1,6 a 4,8 km) o techo de 500 a 999 ft',
  LIFR: 'LIFR: visibilidad de menos de 1 milla (1,6 km) o techo de menos de 500 ft',
}

export function categoryNote(category: string | null): string | null {
  return category ? (CATEGORY_NOTES[category] ?? null) : null
}

// ------------------------------------------------------------------ cuando el TAF no se puede mostrar

/** Mensaje según el estado HTTP de GET /api/taf: 404 = no hay TAF, no es una falla. */
export function tafStatusMessage(status: number | null): string {
  if (status === 404) return 'Este aeródromo no publica TAF.'
  if (status === 429) return 'Se alcanzó el límite de consultas del TAF. Probá de nuevo en un minuto.'
  return 'No se pudo obtener el TAF ahora. Probá de nuevo en unos minutos.'
}
