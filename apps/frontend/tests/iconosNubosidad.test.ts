import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { WEATHER_ICON_CODES, isWeatherIconCode } from '../src/lib/weatherIconCodes.ts'
import { describeWeatherIcon, precipKind } from '../src/lib/weatherLabels.ts'

/** Los íconos que el backend emite según código WMO y nubosidad (sol con chubasco, tormenta o granizo). */
const CLOUD_COVER_ICONS = [
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
] as const

const WEATHER_ICON_SOURCE = readFileSync(
  join(import.meta.dirname, '..', 'src', 'components', 'ui', 'WeatherIcon.tsx'),
  'utf8',
)

test('los 13 íconos por nubosidad son códigos válidos y no se repiten', () => {
  assert.equal(CLOUD_COVER_ICONS.length, 13)
  assert.equal(new Set(CLOUD_COVER_ICONS).size, 13)
  for (const code of CLOUD_COVER_ICONS) {
    assert.ok(isWeatherIconCode(code), `${code} falta en WEATHER_ICON_CODES`)
  }
})

test('WeatherIcon importa el SVG de cada código y lo registra en ICON_MAP', () => {
  for (const code of WEATHER_ICON_CODES) {
    assert.ok(
      WEATHER_ICON_SOURCE.includes(`'@/assets/meteocons/${code}.svg?react'`),
      `${code}: falta el import del SVG en WeatherIcon.tsx`,
    )
    assert.match(WEATHER_ICON_SOURCE, new RegExp(`^\\s+'${code}':\\s+\\w+,`, 'm'), `${code}: falta en ICON_MAP`)
  }
})

test('el granizo suelto sigue disponible en el frontend aunque el backend ya no lo emite', () => {
  assert.ok(isWeatherIconCode('hail'))
  assert.equal(describeWeatherIcon('hail'), 'Granizo')
})

const LABELS: ReadonlyArray<readonly [string, string]> = [
  ['mostly-clear-day', 'Mayormente despejado'],
  ['mostly-clear-night', 'Mayormente despejado'],
  ['mostly-clear-day-rain', 'Lluvia, mayormente despejado'],
  ['mostly-clear-night-rain', 'Lluvia, mayormente despejado'],
  ['mostly-clear-day-snow', 'Nieve, mayormente despejado'],
  ['mostly-clear-night-snow', 'Nieve, mayormente despejado'],
  ['thunderstorms-mostly-clear-day', 'Tormenta, mayormente despejado'],
  ['thunderstorms-mostly-clear-night', 'Tormenta, mayormente despejado'],
  ['thunderstorms-mostly-clear-day-hail', 'Tormenta con granizo, mayormente despejado'],
  ['thunderstorms-mostly-clear-night-hail', 'Tormenta con granizo, mayormente despejado'],
  ['thunderstorms-day-hail', 'Tormenta con granizo'],
  ['thunderstorms-night-hail', 'Tormenta con granizo'],
  ['thunderstorms-overcast-hail', 'Tormenta con granizo'],
]

test('cada ícono por nubosidad tiene su descripción en español', () => {
  for (const [code, label] of LABELS) {
    assert.equal(describeWeatherIcon(code), label, code)
  }
})

test('los textos nuevos no llevan raya larga ni emoji', () => {
  for (const [, label] of LABELS) {
    assert.doesNotMatch(label, /[–—]/)
    assert.doesNotMatch(label, /\p{Extended_Pictographic}/u)
  }
})

test('los textos de los íconos de siempre no cambian', () => {
  assert.equal(describeWeatherIcon('clear-day'), 'Despejado')
  assert.equal(describeWeatherIcon('partly-cloudy-day'), 'Parcialmente nublado')
  assert.equal(describeWeatherIcon('partly-cloudy-day-rain'), 'Lluvia, parcialmente nublado')
  assert.equal(describeWeatherIcon('thunderstorms'), 'Tormenta')
  assert.equal(describeWeatherIcon('thunderstorms-day'), 'Tormenta')
  assert.equal(describeWeatherIcon('overcast'), 'Nublado')
  assert.equal(describeWeatherIcon('fog'), 'Niebla')
  assert.equal(describeWeatherIcon('wind'), null)
})

test('precipKind: la tormenta con granizo se nombra completa y la sin granizo no', () => {
  assert.equal(precipKind('thunderstorms-overcast-hail'), 'Tormenta con granizo')
  assert.equal(precipKind('thunderstorms-mostly-clear-day-hail'), 'Tormenta con granizo')
  assert.equal(precipKind('thunderstorms-mostly-clear-day'), 'Tormenta')
  assert.equal(precipKind('mostly-clear-day-rain'), 'Lluvia')
  assert.equal(precipKind('mostly-clear-night-snow'), 'Nieve')
  assert.equal(precipKind('mostly-clear-day'), null)
})
