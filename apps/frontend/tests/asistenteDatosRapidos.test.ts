import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { LaundryForecastResponse, SmnAlertasResponse, WeatherDashboardResponse } from '../src/lib/api.ts'
import { datosRapidosDesde } from '../src/lib/asistente/datosRapidos.ts'
import { respuestasRapidas } from '../src/lib/asistente/respuestasRapidas.ts'

// What the degraded mode reads from what the app already has in React Query's cache. Pure: the data and the clock come
// in. Like the mood, a forecast older than three hours counts as unknown: the quick answers would be telling the weather
// of another hour.

const HORA = 3_600_000
const AHORA = Date.UTC(2026, 8, 18, 17, 47) // 14:47 in Argentina
const PRIMERA_FRANJA_S = Date.UTC(2026, 8, 18, 17, 0) / 1000

function franjas() {
  return Array.from({ length: 48 }, (_, h) => {
    const timestamp = PRIMERA_FRANJA_S + h * 3600
    const local = new Date((timestamp - 3 * 3600) * 1000)
    return {
      timestamp,
      hour_label: `${String(local.getUTCHours()).padStart(2, '0')}:00`,
      date: local.toISOString().slice(0, 10),
      temp_c: 15,
      precip_mm: 0,
      precip_prob: 0,
      weather_code: 1,
      icon: 'clear-day',
      is_day: true,
      wind_gusts_kmh: 12,
      convective_risk: null,
    }
  })
}

function dashboard(fetchedAt: string, estado = ''): WeatherDashboardResponse {
  return {
    fetched_at: fetchedAt,
    rain_today: { status_text: estado },
    hourly: { entries: franjas() },
  } as unknown as WeatherDashboardResponse
}

const FRESCO = new Date(AHORA - 10 * 60_000).toISOString()
const SIN_AVISOS: SmnAlertasResponse = { alertas: [], available: true, fetched_at: FRESCO }

const ropa = (dias: object[]): LaundryForecastResponse =>
  ({ days: dias, source: 'openmeteo' }) as unknown as LaundryForecastResponse
const dia = (sobre: object = {}) => ({ day_label: 'Sáb 10/10', label: 'Excelente', score: 92, is_best: true, ...sobre })

test('with nothing in the cache there is nothing to offer', () => {
  assert.deepEqual(datosRapidosDesde(null, null, null, AHORA), { veredicto: null, diasRopa: null })
  assert.deepEqual(datosRapidosDesde(undefined, undefined, undefined, AHORA), { veredicto: null, diasRopa: null })
})

test('the verdict is the one the forecast page builds, measured from now', () => {
  const datos = datosRapidosDesde(dashboard(FRESCO), SIN_AVISOS, null, AHORA)
  assert.ok(datos.veredicto && datos.veredicto.length > 0)
  assert.match(datos.veredicto[0].text.replaceAll(' ', ' '), /Sin lluvia prevista hoy ni mañana/)
})

test('a forecast older than three hours counts as unknown', () => {
  const viejo = new Date(AHORA - 3 * HORA - 60_000).toISOString()
  assert.equal(datosRapidosDesde(dashboard(viejo), SIN_AVISOS, null, AHORA).veredicto, null)
  const justo = new Date(AHORA - 3 * HORA).toISOString()
  assert.notEqual(datosRapidosDesde(dashboard(justo), SIN_AVISOS, null, AHORA).veredicto, null)
})

test('an unreadable date is not "old": its age is unknown, not too big', () => {
  assert.notEqual(datosRapidosDesde(dashboard('nunca'), SIN_AVISOS, null, AHORA).veredicto, null)
})

test('a warnings feed that did not answer never becomes "no warnings" and does not break the verdict', () => {
  const sinRespuesta = { alertas: [], available: false, fetched_at: FRESCO } as SmnAlertasResponse
  assert.notEqual(datosRapidosDesde(dashboard(FRESCO), sinRespuesta, null, AHORA).veredicto, null)
  assert.notEqual(datosRapidosDesde(dashboard(FRESCO), null, null, AHORA).veredicto, null)
})

test('the drizzle hint of the forecast page is passed on', () => {
  const sinLlovizna = datosRapidosDesde(dashboard(FRESCO, 'Sin lluvia'), SIN_AVISOS, null, AHORA).veredicto
  const conLlovizna = datosRapidosDesde(dashboard(FRESCO, 'Llovizna posible'), SIN_AVISOS, null, AHORA).veredicto
  assert.notDeepEqual(conLlovizna?.map((l) => l.text), sinLlovizna?.map((l) => l.text))
})

test('the laundry days pass through as they are', () => {
  const dias = [dia(), dia({ day_label: 'Dom 11/10', label: 'Regular', score: 50, is_best: false })]
  assert.deepEqual(datosRapidosDesde(null, null, ropa(dias), AHORA).diasRopa, dias)
  assert.deepEqual(datosRapidosDesde(null, null, ropa([]), AHORA).diasRopa, [])
})

test('what it returns is what the quick answers take', () => {
  const datos = datosRapidosDesde(dashboard(FRESCO), SIN_AVISOS, ropa([dia()]), AHORA)
  assert.deepEqual(respuestasRapidas(datos).map((r) => r.id), ['dia', 'ropa'])
})

// ── The SMN warnings in the verdict ──────────────────────────────────────────

const ROJO = { nivel: 'rojo', tipo: 'Tormentas', fecha_desde: null, fecha_hasta: null, descripcion: 'Tormentas fuertes' }
const avisosCon = (sobre: Partial<SmnAlertasResponse>): SmnAlertasResponse => ({ alertas: [ROJO], available: true, fetched_at: FRESCO, ...sobre })
const primera = (avisos: SmnAlertasResponse) =>
  datosRapidosDesde(dashboard(FRESCO), avisos, null, AHORA).veredicto?.[0].text.replaceAll('\u00a0', ' ') ?? ''

test('a current red warning heads the verdict, as it does on the forecast page', () => {
  assert.equal(primera(avisosCon({})), 'Aviso rojo del SMN: Tormentas')
})

test('a warnings answer older than three hours is left out', () => {
  const viejo = new Date(AHORA - 3 * HORA - 60_000).toISOString()
  assert.doesNotMatch(primera(avisosCon({ fetched_at: viejo })), /Aviso/)
  assert.match(primera(avisosCon({ fetched_at: new Date(AHORA - 3 * HORA).toISOString() })), /Aviso rojo/)
})

test('a warnings feed that did not answer is left out even if it carries a list', () => {
  assert.doesNotMatch(primera(avisosCon({ available: false })), /Aviso/)
})
