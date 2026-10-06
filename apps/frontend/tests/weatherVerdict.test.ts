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
  assert.deepEqual(verdict(hourly()), ['Sin lluvia prevista hoy ni mañana'])
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

test('riesgo de tormentas reemplaza a las ráfagas y encabeza', () => {
  const lines = verdict(hourly({ 2: 1 }, { gust: { 3: 55 }, convective: { 4: 'high' } }))
  assert.equal(lines.length, 2)
  assert.equal(lines[0], 'Riesgo alto de tormentas a las 18:00')
  assert.ok(lines[1].startsWith('Lluvia'))
  assert.ok(!lines.some((l) => l.includes('Ráfagas')))
})

test('ráfagas fuertes se avisan con hora', () => {
  const lines = verdict(hourly({}, { gust: { 3: 55 } }))
  assert.deepEqual(lines, ['Sin lluvia prevista hoy ni mañana', 'Ráfagas de hasta 55 km/h a las 17:00'])
})

const NBSP = String.fromCharCode(0xa0)

const alerta = (nivel: string, tipo: string, hasta: string | null = null) => ({
  nivel, tipo, fecha_desde: null, fecha_hasta: hasta, descripcion: '',
})
const ROJO = alerta('rojo', 'Tormentas', '2026-09-19T00:00:00Z') // hasta las 21:00 AR
const NARANJA = alerta('naranja', 'Viento', '2026-09-20T02:00:00Z') // hasta el sáb 23:00 AR
const withAlerts = (entries: TestEntry[], alertas: ReturnType<typeof alerta>[]) =>
  buildVerdict(entries as never, NOW_MS, false, alertas as never)
const plain = (lines: { text: string }[]) => norm(lines)

test('un aviso rojo es el titular y no hay línea de lluvia ni de "sin lluvia"', () => {
  const lines = withAlerts(hourly(), [ROJO])
  assert.deepEqual(plain(lines), ['Aviso rojo del SMN: Tormentas · hasta las 21:00'])
  assert.equal(lines[0].tone, 'alert')
  assert.equal(lines[0].level, 'rojo')
})

test('con aviso crítico la lluvia prevista tampoco entra: los avisos y el modelo no se contradicen', () => {
  assert.deepEqual(plain(withAlerts(hourly({ 2: 1.2, 3: 2.0, 4: 0.6 }), [NARANJA])), [
    'Aviso naranja del SMN: Viento · hasta el sáb 23:00',
  ])
})

test('con aviso crítico se conservan las ráfagas y el riesgo de tormentas del modelo', () => {
  assert.deepEqual(plain(withAlerts(hourly({}, { gust: { 3: 55 } }), [ROJO])), [
    'Aviso rojo del SMN: Tormentas · hasta las 21:00',
    'Ráfagas de hasta 55 km/h a las 17:00',
  ])
  assert.deepEqual(plain(withAlerts(hourly({}, { convective: { 4: 'high' } }), [ROJO])), [
    'Aviso rojo del SMN: Tormentas · hasta las 21:00',
    'Riesgo alto de tormentas a las 18:00',
  ])
})

test('un aviso de nivel desconocido o verde no cambia el veredicto', () => {
  const rain = hourly({ 2: 1.2, 3: 2.0, 4: 0.6 })
  const base = plain(buildVerdict(rain as never, NOW_MS, false))
  assert.deepEqual(plain(withAlerts(rain, [alerta('sin especificar', 'X')])), base)
  assert.deepEqual(plain(withAlerts(rain, [alerta('verde', 'X')])), base)
})

test('varios avisos críticos: titular el más grave y se cuenta el resto', () => {
  assert.deepEqual(plain(withAlerts(hourly(), [NARANJA, ROJO])), [
    'Aviso rojo del SMN: Tormentas · hasta las 21:00 · +1 aviso más',
  ])
  assert.deepEqual(plain(withAlerts(hourly(), [NARANJA, ROJO, alerta('naranja', 'Nevadas')])), [
    'Aviso rojo del SMN: Tormentas · hasta las 21:00 · +2 avisos más',
  ])
})

test('un aviso sin vigencia no inventa una hora', () => {
  assert.deepEqual(plain(withAlerts(hourly(), [alerta('rojo', 'Tormentas')])), ['Aviso rojo del SMN: Tormentas'])
})

test('del aviso, el tipo y la vigencia viajan marcados como hechos', () => {
  const [line] = withAlerts(hourly(), [ROJO])
  assert.deepEqual(
    line.segments.filter((s) => s.fact).map((s) => s.text.replaceAll(NBSP, ' ')),
    ['Tormentas', 'hasta las 21:00'],
  )
})

test('riesgo alto de tormentas sin aviso es el titular y no se le pone debajo un "sin lluvia"', () => {
  const lines = buildVerdict(hourly({}, { convective: { 4: 'high' } }) as never, NOW_MS, false)
  assert.deepEqual(plain(lines), ['Riesgo alto de tormentas a las 18:00'])
  assert.equal(lines[0].tone, 'storm')
})

test('tormenta con lluvia prevista: la tormenta encabeza y la lluvia acompaña', () => {
  assert.deepEqual(
    plain(buildVerdict(hourly({ 2: 1.2, 3: 2.0, 4: 0.6 }, { convective: { 4: 'high' } }) as never, NOW_MS, false)),
    ['Riesgo alto de tormentas a las 18:00', 'Lluvia débil prevista de 16:00 a 18:00 · ≈ 4 mm en total'],
  )
})

test('tormenta y llovizna posible: tampoco se dice "llovizna" bajo un riesgo alto', () => {
  assert.deepEqual(plain(buildVerdict(hourly({}, { convective: { 4: 'severe' } }) as never, NOW_MS, true)), [
    'Riesgo severo de tormentas a las 18:00',
  ])
})

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
  assert.deepEqual(storm[0].segments.filter((s) => s.fact).map((s) => s.text), ['18:00'])
})

test('sin lluvia con franjas que no llegan al fin de mañana: "en las próximas horas"', () => {
  assert.deepEqual(verdict(hourly().slice(0, 10)), ['Sin lluvia prevista en las próximas horas'])
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

// ── FRA-362: manda nuestro pronóstico; el amarillo es contexto y solo naranja/rojo encabezan ──────────

const ZONED = (date: string, time: string) => `${date}T${time}:00-03:00`
const alertaEntre = (nivel: string, tipo: string, desde: string | null, hasta: string | null) => ({
  nivel, tipo, fecha_desde: desde, fecha_hasta: hasta, descripcion: '',
})
// Hora de referencia de los casos: 14:47 AR del 18/09/2026; el horizonte llega hasta las 00:00 del 20/09.
const AMARILLO = alertaEntre('amarillo', 'Tormentas', ZONED('2026-09-19', '09:00'), ZONED('2026-09-19', '20:59'))
const AMARILLO_LINE = 'Aviso amarillo del SMN: Tormentas · desde el sáb 09:00 hasta el sáb 20:59'
const RAIN_16_18 = 'Lluvia débil prevista de 16:00 a 18:00 · ≈ 4 mm en total'

test('un aviso amarillo no oculta el pronóstico: la lluvia va primero y el aviso al final', () => {
  const lines = withAlerts(hourly({ 2: 1.2, 3: 2.0, 4: 0.6 }), [AMARILLO])
  assert.deepEqual(plain(lines), [RAIN_16_18, AMARILLO_LINE])
  const last = lines[lines.length - 1]
  assert.equal(last.tone, 'alert')
  assert.equal(last.level, 'amarillo')
})

test('un aviso amarillo sin lluvia prevista: el "sin lluvia" y las ráfagas van antes que el aviso', () => {
  assert.deepEqual(plain(withAlerts(hourly({}, { gust: { 3: 55 } }), [AMARILLO])), [
    'Sin lluvia prevista hoy ni mañana',
    'Ráfagas de hasta 55 km/h a las 17:00',
    AMARILLO_LINE,
  ])
})

test('un aviso amarillo conserva la segunda línea de lluvia y el riesgo de tormentas del modelo', () => {
  assert.deepEqual(plain(withAlerts(hourly({ 1: 0.2, 7: 8.0, 8: 9.0 }), [AMARILLO])), [
    'Lluvia fuerte prevista de 21:00 a 22:00 · ≈ 17 mm en total',
    'Antes: lluvia débil a las 15:00 · menos de 1 mm',
    AMARILLO_LINE,
  ])
  assert.deepEqual(plain(withAlerts(hourly({}, { convective: { 4: 'high' } }), [AMARILLO])), [
    'Riesgo alto de tormentas a las 18:00',
    AMARILLO_LINE,
  ])
})

test('amarillo + naranja: solo el naranja, sin repetir el amarillo ni contarlo', () => {
  assert.deepEqual(plain(withAlerts(hourly({ 2: 1.2 }), [AMARILLO, NARANJA])), [
    'Aviso naranja del SMN: Viento · hasta el sáb 23:00',
  ])
})

test('varios críticos: el más grave y, a igual nivel, el que empieza antes', () => {
  const tarde = alertaEntre('naranja', 'Nevadas', ZONED('2026-09-19', '15:00'), ZONED('2026-09-19', '20:00'))
  const temprano = alertaEntre('naranja', 'Viento', ZONED('2026-09-19', '06:00'), ZONED('2026-09-19', '20:00'))
  assert.deepEqual(plain(withAlerts(hourly(), [tarde, temprano])), [
    'Aviso naranja del SMN: Viento · desde el sáb 06:00 hasta el sáb 20:00 · +1 aviso más',
  ])
})

test('dos amarillos: una sola línea, la que empieza antes, con "+1 aviso más"; tres, "+2 avisos más"', () => {
  const tarde = alertaEntre('amarillo', 'Viento', ZONED('2026-09-19', '15:00'), ZONED('2026-09-19', '20:00'))
  const otra = alertaEntre('amarillo', 'Lluvias', ZONED('2026-09-19', '18:00'), ZONED('2026-09-19', '22:00'))
  assert.deepEqual(plain(withAlerts(hourly({}, {}), [tarde, AMARILLO])), [
    'Sin lluvia prevista hoy ni mañana',
    `${AMARILLO_LINE} · +1 aviso más`,
  ])
  assert.deepEqual(plain(withAlerts(hourly({}, {}), [tarde, otra, AMARILLO])), [
    'Sin lluvia prevista hoy ni mañana',
    `${AMARILLO_LINE} · +2 avisos más`,
  ])
})

test('un amarillo en curso va antes que uno futuro', () => {
  const enCurso = alertaEntre('amarillo', 'Viento', ZONED('2026-09-18', '10:00'), ZONED('2026-09-18', '22:00'))
  assert.deepEqual(plain(withAlerts(hourly(), [AMARILLO, enCurso])), [
    'Sin lluvia prevista hoy ni mañana',
    'Aviso amarillo del SMN: Viento · hasta las 22:00 · +1 aviso más',
  ])
})

test('un aviso vencido no aparece, sea amarillo o crítico', () => {
  const rain = hourly({ 2: 1.2, 3: 2.0, 4: 0.6 })
  const base = plain(buildVerdict(rain as never, NOW_MS, false))
  const amarillo = alertaEntre('amarillo', 'Tormentas', ZONED('2026-09-18', '06:00'), ZONED('2026-09-18', '14:00'))
  const rojo = alertaEntre('rojo', 'Tormentas', ZONED('2026-09-18', '06:00'), ZONED('2026-09-18', '14:00'))
  assert.deepEqual(plain(withAlerts(rain, [amarillo, rojo])), base)
})

test('un aviso que empieza después del fin de mañana no aparece; uno de mañana a la noche sí', () => {
  const rain = hourly({ 2: 1.2, 3: 2.0, 4: 0.6 })
  const base = plain(buildVerdict(rain as never, NOW_MS, false))
  const amarilloPasado = alertaEntre('amarillo', 'Tormentas', ZONED('2026-09-20', '00:00'), ZONED('2026-09-20', '12:00'))
  const rojoPasado = alertaEntre('rojo', 'Tormentas', ZONED('2026-09-20', '00:00'), ZONED('2026-09-20', '12:00'))
  assert.deepEqual(plain(withAlerts(rain, [amarilloPasado, rojoPasado])), base)
  const nocheDeManana = alertaEntre('amarillo', 'Tormentas', ZONED('2026-09-19', '23:59'), ZONED('2026-09-20', '06:00'))
  assert.deepEqual(plain(withAlerts(rain, [nocheDeManana])), [
    RAIN_16_18,
    'Aviso amarillo del SMN: Tormentas · desde el sáb 23:59 hasta el dom 06:00',
  ])
})

test('sin avisos el veredicto no cambia (hoy y mañana)', () => {
  assert.deepEqual(plain(withAlerts(hourly({ 2: 1.2, 3: 2.0, 4: 0.6 }), [])), [RAIN_16_18])
})

test('el fin del horizonte se calcula en hora argentina: 23:30 y 00:30 AR', () => {
  const lateNight = Date.UTC(2026, 8, 19, 2, 30) // 23:30 AR del 18/09 -> fin: 00:00 del 20/09
  const early = Date.UTC(2026, 8, 19, 3, 30) // 00:30 AR del 19/09 -> fin: 00:00 del 21/09
  const run = (nowMs: number, nivel: string, desde: string) =>
    buildVerdict(
      hourly() as never,
      nowMs,
      false,
      [alertaEntre(nivel, 'Tormentas', desde, null)] as never,
    ).some((l) => l.tone === 'alert')
  for (const nivel of ['amarillo', 'naranja']) {
    assert.equal(run(lateNight, nivel, ZONED('2026-09-19', '23:00')), true)
    assert.equal(run(lateNight, nivel, ZONED('2026-09-20', '00:30')), false)
    assert.equal(run(early, nivel, ZONED('2026-09-20', '23:00')), true)
    assert.equal(run(early, nivel, ZONED('2026-09-21', '00:30')), false)
  }
})

// Caso real: Córdoba, 2026-10-07. Hora de referencia 14:43 AR del 06/10; franjas de 3 h.
const CBA_NOW_MS = 1791308614602
const CBA_SLOTS: [string, string, number, number, 'low' | 'moderate'][] = [
  ['2026-10-06', '15:00', 0, 20, 'low'],
  ['2026-10-06', '18:00', 0, 30, 'low'],
  ['2026-10-06', '21:00', 0, 42, 'low'],
  ['2026-10-07', '00:00', 0, 29.2, 'low'],
  ['2026-10-07', '03:00', 0, 22.3, 'moderate'],
  ['2026-10-07', '06:00', 0, 20.5, 'moderate'],
  ['2026-10-07', '09:00', 0.1, 15.1, 'moderate'],
  ['2026-10-07', '12:00', 0.8, 30.2, 'moderate'],
  ['2026-10-07', '15:00', 3.3, 59, 'moderate'],
  ['2026-10-07', '18:00', 3.0, 44.6, 'low'],
  ['2026-10-07', '21:00', 0, 16.2, 'low'],
]
const CBA_ENTRIES = CBA_SLOTS.map(([date, hour, mm, gust, risk]) => ({
  timestamp: Date.parse(`${date}T${hour}:00-03:00`) / 1000,
  hour_label: hour,
  date,
  temp_c: 20,
  precip_mm: mm,
  precip_prob: mm > 0.1 ? 80 : 10,
  weather_code: 1,
  icon: 'clear-day',
  is_day: true,
  wind_gusts_kmh: gust,
  convective_risk: risk,
}))
const CBA_AMARILLO = alertaEntre('amarillo', 'Tormentas', '2026-10-07T09:00:00-03:00', '2026-10-07T20:59:00-03:00')
const RIO_CUARTO_NARANJA = alertaEntre('naranja', 'Tormentas', '2026-10-07T03:00:00-03:00', '2026-10-07T08:59:00-03:00')

test('caso Córdoba con el aviso amarillo: el pronóstico primero y el aviso al final', () => {
  const lines = buildVerdict(CBA_ENTRIES as never, CBA_NOW_MS, false, [CBA_AMARILLO] as never)
  assert.deepEqual(plain(lines), [
    'Lluvia débil prevista mañana de 12:00 a 18:00 · ≈ 7 mm en total',
    'Ráfagas de hasta 59 km/h mañana a las 15:00',
    'Aviso amarillo del SMN: Tormentas · desde el mié 09:00 hasta el mié 20:59',
  ])
  assert.deepEqual(lines.map((l) => l.tone), ['rain', 'wind', 'alert'])
  assert.equal(lines[2].level, 'amarillo')
})

test('caso Córdoba sin aviso: la lluvia completa de 12:00 a 18:00 de mañana y las ráfagas', () => {
  assert.deepEqual(plain(buildVerdict(CBA_ENTRIES as never, CBA_NOW_MS, false)), [
    'Lluvia débil prevista mañana de 12:00 a 18:00 · ≈ 7 mm en total',
    'Ráfagas de hasta 59 km/h mañana a las 15:00',
  ])
})

test('caso con aviso naranja (Río Cuarto): el aviso encabeza y no hay línea de lluvia', () => {
  const lines = buildVerdict(CBA_ENTRIES as never, CBA_NOW_MS, false, [RIO_CUARTO_NARANJA] as never)
  assert.deepEqual(plain(lines), [
    'Aviso naranja del SMN: Tormentas · desde el mié 03:00 hasta el mié 08:59',
    'Ráfagas de hasta 59 km/h mañana a las 15:00',
  ])
  assert.equal(lines[0].level, 'naranja')
  assert.ok(!plain(lines).some((l) => l.includes('Lluvia')))
})
