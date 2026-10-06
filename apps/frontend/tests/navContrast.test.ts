import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  MIN_TEXT_CONTRAST,
  NAV_PILL_COLORS,
  blendHex,
  contrastRatio,
  pillLabelContrast,
  relativeLuminance,
  type PillState,
} from '../src/lib/navContrast.ts'

// The surface the pills are drawn on comes from the real stylesheet, so a theme change re-runs the check.
const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')

function cssToken(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`))
  assert.ok(match, `--${name} no está definido en index.css`)
  return match[1]
}

function hue(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const max = Math.max(r, g, b)
  const delta = max - Math.min(r, g, b)
  if (delta === 0) return 0
  const sector = max === r ? ((g - b) / delta + 6) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4
  return sector * 60
}

const STATES: readonly PillState[] = ['idle', 'active']

test('contrastRatio: valores de referencia de WCAG (negro/blanco y el corte AA de #767676)', () => {
  assert.ok(Math.abs(contrastRatio('#000000', '#ffffff') - 21) < 0.001)
  assert.equal(contrastRatio('#336699', '#336699'), 1)
  assert.ok(contrastRatio('#767676', '#ffffff') >= MIN_TEXT_CONTRAST) // 4,54:1
  assert.ok(contrastRatio('#777777', '#ffffff') < MIN_TEXT_CONTRAST) // 4,48:1
})

test('contrastRatio: no depende del orden de los colores', () => {
  assert.equal(contrastRatio('#e05545', '#060d1a'), contrastRatio('#060d1a', '#e05545'))
})

test('relativeLuminance: blanco 1, negro 0', () => {
  assert.equal(relativeLuminance('#ffffff'), 1)
  assert.equal(relativeLuminance('#000000'), 0)
})

test('blendHex: alfa 0 deja el fondo, alfa 1 el primer plano, y redondea al canal entero', () => {
  assert.equal(blendHex('#ffffff', '#000000', 0), '#000000')
  assert.equal(blendHex('#ffffff', '#000000', 1), '#ffffff')
  assert.equal(blendHex('#ffffff', '#000000', 0.5), '#808080')
})

test('la barra de navegación tiene los 16 destinos', () => {
  assert.equal(Object.keys(NAV_PILL_COLORS).length, 16)
})

test('todas las pills (reposo y activa) tienen texto >= 4,5:1 contra su fondo real', () => {
  const surface = cssToken('color-background')
  const failures: string[] = []
  for (const [route, colors] of Object.entries(NAV_PILL_COLORS)) {
    for (const state of STATES) {
      const ratio = pillLabelContrast(colors, surface, state)
      if (ratio < MIN_TEXT_CONTRAST) failures.push(`${route} ${state}: ${ratio.toFixed(2)}:1`)
    }
  }
  assert.deepEqual(failures, [])
})

test('el texto aclarado conserva el matiz del color de cada pill (±10°)', () => {
  for (const [route, colors] of Object.entries(NAV_PILL_COLORS)) {
    const drift = Math.abs(hue(colors.label) - hue(colors.accent))
    assert.ok(Math.min(drift, 360 - drift) <= 10, `${route}: el matiz se corrió ${drift.toFixed(1)}°`)
  }
})

test('el enlace "Saltar al contenido" (primary sobre primary-foreground) cumple 4,5:1', () => {
  const ratio = contrastRatio(cssToken('color-primary-foreground'), cssToken('color-primary'))
  assert.ok(ratio >= MIN_TEXT_CONTRAST, `${ratio.toFixed(2)}:1`)
})

test('el aviso de ubicación (destructive sobre el fondo del header) cumple 4,5:1', () => {
  const ratio = contrastRatio(cssToken('color-destructive'), cssToken('color-background'))
  assert.ok(ratio >= MIN_TEXT_CONTRAST, `${ratio.toFixed(2)}:1`)
})
