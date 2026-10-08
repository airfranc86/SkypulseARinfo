import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { WEATHER_ICON_CODES, isWeatherIconCode } from '../src/lib/weatherIconCodes.ts'
import { describeWeatherIcon } from '../src/lib/weatherLabels.ts'
import { glowFilter } from '../src/lib/iconGlow.ts'
import { weatherItems, weatherText } from '../src/lib/taf.ts'

const NEW_ICONS = ['mist', 'haze', 'smoke', 'dust'] as const
const src = (path: string) => readFileSync(join(import.meta.dirname, '..', path), 'utf8').replaceAll('\r\n', '\n')

const weatherIconSource = src('src/components/ui/WeatherIcon.tsx')
const metar = src('src/pages/Metar.tsx')
const tafCard = src('src/components/aeronautica/TafDecodedCard.tsx')

function glossarySource(): string {
  const start = metar.indexOf('const GLOSARIO')
  return metar.slice(start, metar.indexOf('function GlosarioSection', start))
}

test('the four phenomenon icons are valid codes with their SVG file', () => {
  for (const code of NEW_ICONS) {
    assert.ok(isWeatherIconCode(code), `${code} is missing in WEATHER_ICON_CODES`)
    assert.ok(WEATHER_ICON_CODES.includes(code))
    assert.ok(existsSync(join(import.meta.dirname, '..', 'src', 'assets', 'meteocons', `${code}.svg`)), code)
  }
})

test('WeatherIcon imports and registers the four phenomenon icons', () => {
  for (const code of NEW_ICONS) {
    assert.ok(weatherIconSource.includes(`'@/assets/meteocons/${code}.svg?react'`), `${code}: no import`)
    assert.match(weatherIconSource, new RegExp(`^\\s+'${code}':\\s+\\w+,`, 'm'), `${code}: not in ICON_MAP`)
  }
})

test('the four icons have their Spanish label', () => {
  assert.equal(describeWeatherIcon('mist'), 'Neblina')
  assert.equal(describeWeatherIcon('haze'), 'Calima')
  assert.equal(describeWeatherIcon('smoke'), 'Humo')
  assert.equal(describeWeatherIcon('dust'), 'Polvo')
})

test('the four icons get no glow', () => {
  for (const code of NEW_ICONS) assert.equal(glowFilter(code), undefined, code)
})

test('the glossary shows an icon for BR, FG, HZ, FU and DU', () => {
  const glossary = glossarySource()
  const expected: Record<string, string> = { BR: 'mist', FG: 'fog', HZ: 'haze', FU: 'smoke', DU: 'dust' }
  for (const [code, icon] of Object.entries(expected)) {
    const row = glossary.split('\n').find((line) => line.includes(`code: '${code}'`))
    assert.ok(row, `the glossary has no ${code} row`)
    assert.ok(row.includes(`icon: '${icon}'`), `${code} must use the ${icon} icon`)
  }
  assert.ok(glossary.includes('Smoke — humo'))
  assert.ok(glossary.includes('Dust — polvo'))
})

test('only the phenomenon rows carry an icon and the section renders it decorative', () => {
  const glossary = glossarySource()
  assert.equal(glossary.split('\n').filter((line) => line.includes("icon: '")).length, 5)
  const section = metar.slice(metar.indexOf('function GlosarioSection'))
  assert.match(section, /<WeatherIcon[^>]*code=\{g\.icon\}/)
  assert.ok(!/<WeatherIcon[^>]*label=/.test(section), 'the glossary icons must be decorative')
})

test('weatherItems keeps the decoded texts and adds the icons per token', () => {
  const codes = ['-RA', 'BR', 'HZ', 'FU', 'DU', 'FG', 'TSRA']
  assert.deepEqual(weatherItems(codes).map((item) => item.text), weatherText(codes))
  assert.deepEqual(weatherItems(codes).map((item) => item.icons), [[], ['mist'], ['haze'], ['smoke'], ['dust'], ['fog'], []])
})

test('the TAF card renders the icons through weatherItems', () => {
  assert.ok(tafCard.includes('weatherItems(period.weather)'), 'the card does not decode with weatherItems')
  assert.ok(!tafCard.includes('weatherText'), 'the card still uses weatherText')
  assert.ok(tafCard.includes('WeatherIcon'), 'the card does not render WeatherIcon')
})
