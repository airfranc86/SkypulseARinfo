import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { WEATHER_ICON_CODES } from '../src/lib/weatherIconCodes.ts'
import { glowFilter } from '../src/lib/iconGlow.ts'

const PRECIP = /brightness\(1\.35\) saturate\(1\.6\)/
const GOLD = 'drop-shadow(0 0 8px rgba(200,168,75,0.4))'
const LAVENDER = 'drop-shadow(0 0 6px rgba(168,180,234,0.35))'
const PRECIP_WORDS = ['rain', 'drizzle', 'snow', 'sleet', 'hail', 'thunderstorm']

const isPrecip = (code: string) => PRECIP_WORDS.some((word) => code.includes(word))

test('glowFilter: lluvia, nieve, granizo y tormenta llevan el realce de gotas de día y de noche', () => {
  for (const code of WEATHER_ICON_CODES.filter(isPrecip)) {
    assert.match(glowFilter(code) ?? '', PRECIP, code)
  }
})

test('glowFilter: las variantes nocturnas con precipitación ya no pierden el realce', () => {
  for (const code of [
    'partly-cloudy-night-rain',
    'partly-cloudy-night-snow',
    'partly-cloudy-night-drizzle',
    'thunderstorms-night',
    'thunderstorms-night-hail',
    'mostly-clear-night-rain',
    'mostly-clear-night-snow',
    'thunderstorms-mostly-clear-night',
    'thunderstorms-mostly-clear-night-hail',
  ]) {
    assert.match(glowFilter(code) ?? '', PRECIP, code)
  }
})

test('glowFilter: sin precipitación, el sol es dorado y la noche lavanda', () => {
  for (const code of ['clear-day', 'partly-cloudy-day', 'mostly-clear-day']) {
    assert.equal(glowFilter(code), GOLD, code)
  }
  for (const code of ['clear-night', 'partly-cloudy-night', 'mostly-clear-night', 'overcast-night', 'moon-full']) {
    assert.equal(glowFilter(code), LAVENDER, code)
  }
})

test('glowFilter: sin sol, luna ni precipitación no hay realce', () => {
  for (const code of ['overcast', 'fog', 'wind', 'thermometer', 'humidity', 'uv-index']) {
    assert.equal(glowFilter(code), undefined, code)
  }
})

test('WeatherIcon usa el glowFilter de la librería y no define otro', () => {
  const source = readFileSync(join(import.meta.dirname, '..', 'src', 'components', 'ui', 'WeatherIcon.tsx'), 'utf8')
  assert.match(source, /import \{ glowFilter \} from '@\/lib\/iconGlow'/)
  assert.doesNotMatch(source, /function glowFilter/)
})
