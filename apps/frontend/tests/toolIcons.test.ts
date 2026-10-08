import { test } from 'node:test'
import assert from 'node:assert/strict'
import { WEATHER_ICON_CODES, isWeatherIconCode } from '../src/lib/weatherIconCodes.ts'
import {
  FIRE_CONDITION_ICON_CODES,
  SNOW_STATUS_ICONS,
  SPORT_FACTOR_ICON_CODES,
  TOOL_HEADER_ICON_CODES,
  TOOL_HEADER_ICON_SIZE,
  fireConditionIconCode,
  sunIconCode,
} from '../src/lib/toolIcons.ts'
import { sunChipLabel } from '../src/lib/sunChip.ts'

test('the valid icon codes have no duplicates', () => {
  assert.equal(new Set(WEATHER_ICON_CODES).size, WEATHER_ICON_CODES.length)
})

test('isWeatherIconCode accepts known codes and rejects the rest', () => {
  assert.ok(isWeatherIconCode('snow'))
  assert.ok(!isWeatherIconCode('snowman'))
  assert.ok(!isWeatherIconCode(''))
})

test('every Incendios condition icon is a valid code', () => {
  for (const [label, code] of Object.entries(FIRE_CONDITION_ICON_CODES)) {
    assert.ok(isWeatherIconCode(code), `${label} -> ${code} is not a WeatherIcon code`)
  }
})

test('Incendios chips map to their weather icons', () => {
  assert.equal(fireConditionIconCode('Temperatura'), 'thermometer')
  assert.equal(fireConditionIconCode('Humedad'), 'humidity')
  assert.equal(fireConditionIconCode('Viento'), 'wind')
  assert.equal(fireConditionIconCode('Precipitación'), 'rain')
})

test('an unknown Incendios chip has no weather icon (the page draws a lucide fallback)', () => {
  assert.equal(fireConditionIconCode('Otra cosa'), null)
  assert.equal(fireConditionIconCode('toString'), null)
})

test('every sport factor icon is a valid code', () => {
  for (const [factor, code] of Object.entries(SPORT_FACTOR_ICON_CODES)) {
    assert.ok(isWeatherIconCode(code), `${factor} -> ${code} is not a WeatherIcon code`)
  }
})

test('sport factors map to the agreed icons', () => {
  assert.deepEqual(SPORT_FACTOR_ICON_CODES, {
    humidity: 'humidity',
    uv: 'uv-index',
    wind: 'wind',
    cold: 'thermometer',
    heat: 'thermometer',
    rain: 'rain',
    storm: 'thunderstorms',
  })
})

test('sunIconCode: night is always the clear-night icon', () => {
  assert.equal(sunIconCode(false, null), 'clear-night')
  assert.equal(sunIconCode(false, 10), 'clear-night')
})

test('sunIconCode: UV 6 or more is the UV index icon', () => {
  assert.equal(sunIconCode(true, 6), 'uv-index')
  assert.equal(sunIconCode(true, 11), 'uv-index')
})

test('sunIconCode: UV from 3 up to 6 is direct sun', () => {
  assert.equal(sunIconCode(true, 3), 'clear-day')
  assert.equal(sunIconCode(true, 5.4), 'clear-day')
})

test('sunIconCode: below UV 3, or without UV, is moderate sun', () => {
  assert.equal(sunIconCode(true, 2.4), 'partly-cloudy-day')
  assert.equal(sunIconCode(true, 0), 'partly-cloudy-day')
  assert.equal(sunIconCode(true, null), 'partly-cloudy-day')
})

test('sunIconCode: classifies the rounded UV, like the chip text (uvCategory)', () => {
  // The chip reads "UV 3" for 2.6 and "UV 6" for 5.6: the icon has to be the one of the number shown.
  assert.equal(sunIconCode(true, 2.6), 'clear-day')
  assert.equal(sunIconCode(true, 2.9), 'clear-day')
  assert.equal(sunIconCode(true, 5.6), 'uv-index')
  assert.equal(sunIconCode(true, 5.9), 'uv-index')
})

test('sunIconCode and sunChipLabel agree on every UV band', () => {
  for (const uv of [0, 1, 2.4, 2.5, 2.6, 3, 5.4, 5.5, 5.6, 6, 7.4, 11]) {
    const icon = sunIconCode(true, uv)
    const label = sunChipLabel(true, uv)
    if (label === 'UV bajo') assert.equal(icon, 'partly-cloudy-day', `uv ${uv}`)
    else if (label === 'Sol directo') assert.equal(icon, 'clear-day', `uv ${uv}`)
    else assert.equal(icon, 'uv-index', `uv ${uv}`)
  }
})

test('sunIconCode always returns a valid code', () => {
  for (const isDay of [true, false]) {
    for (const uv of [null, 0, 2.9, 3, 5.9, 6, 12]) {
      assert.ok(isWeatherIconCode(sunIconCode(isDay, uv)))
    }
  }
})

test('the three tool headers use snow, partly-cloudy-day and thermometer', () => {
  assert.deepEqual(TOOL_HEADER_ICON_CODES, {
    cotaDeNieve: 'snow',
    hacerDeporte: 'partly-cloudy-day',
    incendios: 'thermometer',
  })
  for (const code of Object.values(TOOL_HEADER_ICON_CODES)) {
    assert.ok(isWeatherIconCode(code))
  }
})

test('the header icon fits inside the 64 px PageHeader square', () => {
  assert.ok(TOOL_HEADER_ICON_SIZE <= 48)
})

test('Cota de nieve: only a low snow level uses a weather icon (rain)', () => {
  assert.deepEqual(SNOW_STATUS_ICONS.low, { kind: 'weather', code: 'rain' })
  assert.deepEqual(SNOW_STATUS_ICONS.excellent, { kind: 'status', name: 'ok' })
  assert.deepEqual(SNOW_STATUS_ICONS.good, { kind: 'status', name: 'ski' })
  assert.deepEqual(SNOW_STATUS_ICONS.moderate, { kind: 'status', name: 'warning' })
  const low = SNOW_STATUS_ICONS.low
  assert.ok(isWeatherIconCode(low.code))
})
