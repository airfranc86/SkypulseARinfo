import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { MIN_TEXT_CONTRAST, contrastRatio } from '../src/lib/navContrast.ts'
import {
  SPORT_DANGER_TEXT,
  rainIndicatorText,
  scoredHumidity,
  scoredWindSpeed,
  severityPrefix,
  sportDetail,
  type SportLabel,
} from '../src/lib/sportBlock.ts'

test('scoredWindSpeed: muestra el viento que puntúa (data.wind_speed), no el observado', () => {
  // Caso del reporte: el puntaje usó 15 km/h ("viento suave") y la observación dice 24.
  assert.equal(scoredWindSpeed(15, 24), 15)
})

test('scoredWindSpeed: con 0 km/h puntuado muestra 0, no cae al observado', () => {
  assert.equal(scoredWindSpeed(0, 24), 0)
})

test('scoredWindSpeed: solo si el puntuado falta usa el observado', () => {
  assert.equal(scoredWindSpeed(null, 24), 24)
  assert.equal(scoredWindSpeed(undefined, 24), 24)
})

test('scoredWindSpeed: sin ningún dato es null', () => {
  assert.equal(scoredWindSpeed(null, null), null)
  assert.equal(scoredWindSpeed(undefined, undefined), null)
})

test('rainIndicatorText: usa los mm del backend y la misma ventana del puntaje (12 h)', () => {
  assert.equal(rainIndicatorText(2), 'Lluvia prevista: 2 mm en 12 h')
  assert.equal(rainIndicatorText(0.5), 'Lluvia prevista: 0,5 mm en 12 h')
  assert.equal(rainIndicatorText(2.34), 'Lluvia prevista: 2,3 mm en 12 h')
})

test('rainIndicatorText: lo que redondea a cero no se muestra como "0 mm"', () => {
  assert.equal(rainIndicatorText(0.02), 'Lluvia prevista: menos de 0,1 mm en 12 h')
})

test('rainIndicatorText: sin lluvia o sin dato no hay indicador', () => {
  assert.equal(rainIndicatorText(0), null)
  assert.equal(rainIndicatorText(null), null)
  assert.equal(rainIndicatorText(undefined), null)
  assert.equal(rainIndicatorText(Number.NaN), null)
})

test('scoredHumidity: muestra la humedad que puntúa (data.humidity), no la observada', () => {
  assert.equal(scoredHumidity(60, 85), 60)
  assert.equal(scoredHumidity(0, 85), 0)
})

test('scoredHumidity: solo si el puntaje no trae humedad usa la observada; sin datos es null', () => {
  assert.equal(scoredHumidity(null, 85), 85)
  assert.equal(scoredHumidity(undefined, 85), 85)
  assert.equal(scoredHumidity(null, null), null)
})

const LABELS: SportLabel[] = ['Excelente', 'Bueno', 'Regular', 'No apto']
const REASON = 'Calor: 30,0 °C, por encima del rango ideal. Factores favorables: humedad tolerable.'

test('sportDetail: con indicadores del frontend se muestran ellos, sea cual sea la etiqueta', () => {
  for (const label of LABELS) {
    assert.deepEqual(sportDetail({ label, reason: REASON, indicatorCount: 1 }), { kind: 'indicators' })
  }
})

test('sportDetail: sin indicadores y sin ser "Excelente" se muestra el motivo del backend (también en "Bueno")', () => {
  for (const label of ['Bueno', 'Regular', 'No apto'] as const) {
    assert.deepEqual(sportDetail({ label, reason: REASON, indicatorCount: 0 }), { kind: 'reason', text: REASON })
  }
})

test('sportDetail: "Condiciones favorables" solo si la etiqueta es "Excelente"', () => {
  assert.deepEqual(sportDetail({ label: 'Excelente', reason: REASON, indicatorCount: 0 }), { kind: 'favorable' })
  for (const label of ['Bueno', 'Regular', 'No apto'] as const) {
    assert.notDeepEqual(sportDetail({ label, reason: REASON, indicatorCount: 0 }), { kind: 'favorable' })
  }
})

test('sportDetail: sin indicadores, no "Excelente" y sin motivo no se inventa nada', () => {
  for (const reason of ['', '   ']) {
    for (const label of ['Bueno', 'Regular', 'No apto'] as const) {
      assert.deepEqual(sportDetail({ label, reason, indicatorCount: 0 }), { kind: 'none' })
    }
  }
})

test('severityPrefix: peligro y atención se distinguen con palabras, no solo por color', () => {
  assert.equal(severityPrefix('danger'), 'Peligro:')
  assert.equal(severityPrefix('warning'), 'Atención:')
})

test('SPORT_DANGER_TEXT: el rojo del texto de 12 px llega a 4,5:1 sobre la tarjeta (tema y variante verde)', () => {
  const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
  const card = css.match(/--color-card:\s*(#[0-9a-fA-F]{6})/)?.[1]
  assert.ok(card, '--color-card no está definido en index.css')
  assert.ok(contrastRatio(SPORT_DANGER_TEXT, card) >= MIN_TEXT_CONTRAST, `contraste ${contrastRatio(SPORT_DANGER_TEXT, card)}`)
  // Fondo del BorderGlow de la tarjeta "Excelente" (SportBlock.tsx).
  assert.ok(contrastRatio(SPORT_DANGER_TEXT, '#0d1625') >= MIN_TEXT_CONTRAST)
})
