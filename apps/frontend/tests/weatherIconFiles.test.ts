import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { WEATHER_ICON_CODES } from '../src/lib/weatherIconCodes.ts'

const DIR = join(import.meta.dirname, '..', 'src', 'assets', 'meteocons')

test('cada código de WEATHER_ICON_CODES tiene su archivo .svg', () => {
  const absent = WEATHER_ICON_CODES.filter((code) => !existsSync(join(DIR, `${code}.svg`)))
  assert.deepEqual(absent, [])
})

test('cada SVG de un código es un SVG sin scripts ni enlaces externos', () => {
  for (const code of WEATHER_ICON_CODES) {
    const svg = readFileSync(join(DIR, `${code}.svg`), 'utf8')
    assert.match(svg, /<svg[\s>]/, `${code}: no es un SVG`)
    assert.doesNotMatch(svg, /<script/i, `${code}: lleva un script`)
    assert.doesNotMatch(svg, /\son\w+\s*=/i, `${code}: lleva un manejador de eventos`)
    assert.doesNotMatch(svg, /(?:xlink:)?href\s*=\s*["'](?!#)/i, `${code}: enlaza a un recurso externo`)
    assert.doesNotMatch(svg, /<foreignObject/i, `${code}: lleva foreignObject`)
  }
})
