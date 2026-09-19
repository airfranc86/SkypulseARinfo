import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildVerdict, rainIntensity, slotHours } from '../src/lib/weatherVerdict.ts'

// Hora de referencia: 14:47 hora argentina (UTC-3) del 18/09/2026.
const NOW_MS = Date.UTC(2026, 8, 18, 17, 47)
const FIRST_SLOT_S = Date.UTC(2026, 8, 18, 17, 0) / 1000 // 14:00 AR

interface TestEntry {
  timestamp: number
  hour_label: string
  date: string
  temp_c: number
  precip_mm: number
  precip_prob: number
  weather_code: number
  icon: string
  is_day: boolean
  wind_gusts_kmh?: number
  convective_risk?: 'low' | 'moderate' | 'high' | 'severe' | null
}

/**
 * 48 h de franjas desde las 14:00 AR. `mm` mapea hora local (0–47 desde las 14:00 de hoy,
 * contada en horas reales) a milímetros de esa franja.
 */
function hourly(
  mm: Record<number, number> = {},
  { stepHours = 1, gust = {}, convective = {} }: {
    stepHours?: number
    gust?: Record<number, number>
    convective?: Record<number, 'high' | 'severe'>
  } = {},
): TestEntry[] {
  const out: TestEntry[] = []
  for (let h = 0; h < 48; h += stepHours) {
    const ts = FIRST_SLOT_S + h * 3600
    const local = new Date((ts - 3 * 3600) * 1000)
    const hh = String(local.getUTCHours()).padStart(2, '0')
    out.push({
      timestamp: ts,
      hour_label: `${hh}:00`,
      date: local.toISOString().slice(0, 10),
      temp_c: 15,
      precip_mm: mm[h] ?? 0,
      precip_prob: (mm[h] ?? 0) > 0.1 ? 100 : 0,
      weather_code: 1,
      icon: 'clear-day',
      is_day: true,
      wind_gusts_kmh: gust[h] ?? 12,
      convective_risk: convective[h] ?? null,
    })
  }
  return out
}

const norm = (lines: { text: string }[]) => lines.map((l) => l.text.replaceAll(String.fromCharCode(0xa0), " "))
const verdict = (entries: TestEntry[], drizzle = false) =>
  norm(buildVerdict(entries as never, NOW_MS, drizzle))

test('sin lluvia: lo dice con el horizonte real', () => {
  assert.deepEqual(verdict(hourly()), ['Sin lluvia prevista en las próximas 24 h'])
})

test('una franja: intensidad, horas y total', () => {
  // 16:00, 17:00 y 18:00 AR = horas 2, 3 y 4 desde las 14:00. Máx. 2,0 mm/h: débil.
  assert.deepEqual(verdict(hourly({ 2: 1.2, 3: 2.0, 4: 0.6 })), [
    'Lluvia débil prevista de 16:00 a 18:00 · ≈ 4 mm en total',
  ])
})

test('una llovizna previa no tapa el chaparrón posterior', () => {
  // 15:00 → hora 1 (0,2 mm); 21:00 y 22:00 → horas 7 y 8 (8 y 9 mm/h).
  assert.deepEqual(verdict(hourly({ 1: 0.2, 7: 8.0, 8: 9.0 })), [
    'Lluvia fuerte prevista de 21:00 a 22:00 · ≈ 17 mm en total',
    'Antes: lluvia débil a las 15:00 · menos de 1 mm',
  ])
})

test('si la más fuerte va primero, la otra se anuncia como "Después"', () => {
  // 16:00 y 17:00 → horas 2 y 3 (8 mm/h cada una); 23:00 → hora 9 (0,3 mm).
  assert.deepEqual(verdict(hourly({ 2: 8.0, 3: 8.0, 9: 0.3 })), [
    'Lluvia fuerte prevista de 16:00 a 17:00 · ≈ 16 mm en total',
    'Después: lluvia débil a las 23:00 · menos de 1 mm',
  ])
})

test('una sola franja mínima no dice "≈ < 1 mm"', () => {
  assert.deepEqual(verdict(hourly({ 2: 0.3 })), ['Lluvia débil prevista a las 16:00 · menos de 1 mm en total'])
})

test('con franjas de 3 h la intensidad se calcula por hora', () => {
  // 17 mm en una franja de 3 h = 5,7 mm/h: moderada, no fuerte.
  assert.deepEqual(verdict(hourly({ 6: 17 }, { stepHours: 3 })), [
    'Lluvia moderada prevista a las 20:00 · ≈ 17 mm en total',
  ])
})

test('lluvia en curso', () => {
  // La franja de las 14:00 ya empezó (son las 14:47); 15:00 sigue.
  assert.deepEqual(verdict(hourly({ 0: 0.8, 1: 1.0 })), [
    'Lluvia débil prevista ahora, hasta las 15:00 · ≈ 2 mm en total',
  ])
})

test('lluvia solo mañana lleva el día', () => {
  // 05:00 a 08:00 de mañana = horas 15 a 18 desde las 14:00 de hoy.
  assert.deepEqual(verdict(hourly({ 15: 0.5, 16: 0.5, 17: 0.5, 18: 0.5 })), [
    'Lluvia débil prevista mañana de 05:00 a 08:00 · ≈ 2 mm en total',
  ])
})

test('llovizna sin lluvia medida', () => {
  assert.deepEqual(verdict(hourly(), true), ['Llovizna posible, sin lluvia medida en el pronóstico'])
})

test('riesgo de tormentas reemplaza a las ráfagas', () => {
  const lines = verdict(hourly({ 2: 1 }, { gust: { 3: 55 }, convective: { 4: 'high' } }))
  assert.equal(lines.length, 2)
  assert.equal(lines[1], 'Riesgo alto de tormentas a las 18:00')
})

test('ráfagas fuertes se avisan con hora', () => {
  const lines = verdict(hourly({}, { gust: { 3: 55 } }))
  assert.deepEqual(lines, ['Sin lluvia prevista en las próximas 24 h', 'Ráfagas de hasta 55 km/h a las 17:00'])
})

const NBSP = String.fromCharCode(0xa0)

test('los datos duros del titular viajan marcados como hechos', () => {
  const [headline] = buildVerdict(hourly({ 2: 1.2, 3: 2.0, 4: 0.6 }) as never, NOW_MS, false)
  assert.deepEqual(
    headline.segments.filter((s) => s.fact).map((s) => s.text.replaceAll(NBSP, ' ')),
    ['de 16:00 a 18:00', '≈ 4 mm'],
  )
  assert.equal(headline.segments.map((s) => s.text).join(''), headline.text)
})

test('ráfagas y tormentas: velocidad y hora son hechos', () => {
  const lines = buildVerdict(hourly({}, { gust: { 3: 55 } }) as never, NOW_MS, false)
  assert.deepEqual(
    lines[1].segments.filter((s) => s.fact).map((s) => s.text.replaceAll(NBSP, ' ')),
    ['55 km/h', '17:00'],
  )
  const storm = buildVerdict(hourly({}, { convective: { 4: 'high' } }) as never, NOW_MS, false)
  assert.deepEqual(storm[1].segments.filter((s) => s.fact).map((s) => s.text), ['18:00'])
})

test('"24 h" no se parte entre renglones', () => {
  const [line] = buildVerdict(hourly() as never, NOW_MS, false)
  assert.ok(line.text.includes(`24${NBSP}h`))
})

test('"mañana" se cuenta desde el día argentino de la hora de referencia, no desde la primera franja', () => {
  // 23:30 AR del 18/09. Con franjas de 3 h la próxima ya es la de las 00:00 del 19/09: esa lluvia es de mañana.
  const at = (hoursFromMidnightAr: number, mm: number) => {
    const ts = Date.UTC(2026, 8, 18, 3, 0) / 1000 + hoursFromMidnightAr * 3600
    const local = new Date((ts - 3 * 3600) * 1000)
    return {
      timestamp: ts,
      hour_label: `${String(local.getUTCHours()).padStart(2, '0')}:00`,
      date: local.toISOString().slice(0, 10),
      temp_c: 15, precip_mm: mm, precip_prob: 0, weather_code: 1, icon: 'clear-night', is_day: false,
      wind_gusts_kmh: 10, convective_risk: null,
    }
  }
  const entries = [at(18, 0), at(21, 0), at(24, 1.5), at(27, 0), at(30, 0)]
  const nowMs = Date.UTC(2026, 8, 19, 2, 30) // 23:30 AR del 18/09
  assert.deepEqual(
    buildVerdict(entries as never, nowMs, false).map((l) => l.text.replaceAll(String.fromCharCode(0xa0), ' ')),
    ['Lluvia débil prevista mañana a las 00:00 · ≈ 2 mm en total'],
  )
})

test('rainIntensity: límites de las clases AMS/NWS', () => {
  assert.equal(rainIntensity(0.3), 'débil')
  assert.equal(rainIntensity(2.4), 'débil')
  assert.equal(rainIntensity(2.5), 'moderada')
  assert.equal(rainIntensity(7.6), 'moderada')
  assert.equal(rainIntensity(7.7), 'fuerte')
})

test('slotHours infiere el paso entre franjas', () => {
  assert.equal(slotHours(hourly({}, { stepHours: 1 }) as never, 4), 1)
  assert.equal(slotHours(hourly({}, { stepHours: 3 }) as never, 4), 3)
  assert.equal(slotHours(hourly({}, { stepHours: 3 }) as never, 15), 3) // la última usa el paso anterior
  assert.equal(slotHours(hourly().slice(0, 1) as never, 0), 1) // sin vecinos: 1 h
})
