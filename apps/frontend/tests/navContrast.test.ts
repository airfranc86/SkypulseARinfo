import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  LAYER_PRESENCE,
  LAYER_STATES,
  MIN_TEXT_CONTRAST,
  NAV_PILL_COLORS,
  PILL_BORDER_ALPHA,
  PILL_TINT_ALPHA,
  blendHex,
  contrastRatio,
  layerPillBackground,
  layerPillLabelColor,
  layerPillContrast,
  oklabDistance,
  oklchHue,
  pillLabelColor,
  pillLabelContrast,
  relativeLuminance,
  toOklab,
  type PillState,
} from '../src/lib/navContrast.ts'
import { LAYER_INK, TOOLS, toolByPath } from '../src/lib/toolRegistry.ts'

const lookOf = (route: string) => {
  const tool = toolByPath(route)
  assert.ok(tool, `${route} no está en el registro`)
  return tool.look
}

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

test('toOklab: blanco L=1 y negro L=0, ambos sin croma', () => {
  const [lw, aw, bw] = toOklab('#ffffff')
  assert.ok(Math.abs(lw - 1) < 1e-3 && Math.abs(aw) < 1e-3 && Math.abs(bw) < 1e-3)
  assert.deepEqual(toOklab('#000000').map((v) => Math.abs(v) < 1e-9), [true, true, true])
})

test('oklabDistance: 0 para el mismo color, simétrica, y blanco/negro a distancia 1', () => {
  assert.equal(oklabDistance('#7cc4f2', '#7cc4f2'), 0)
  assert.equal(oklabDistance('#e05545', '#40d9c1'), oklabDistance('#40d9c1', '#e05545'))
  assert.ok(Math.abs(oklabDistance('#000000', '#ffffff') - 1) < 1e-3)
})

test('oklchHue: el rojo puro cae cerca de 29°, el verde de 142° y el azul de 264°', () => {
  assert.ok(Math.abs(oklchHue('#ff0000') - 29.2) < 1)
  assert.ok(Math.abs(oklchHue('#00ff00') - 142.5) < 1)
  assert.ok(Math.abs(oklchHue('#0000ff') - 264.1) < 1)
})

test('la barra de navegación tiene los 16 destinos', () => {
  assert.equal(Object.keys(NAV_PILL_COLORS).length, 16)
})

test('NAV_PILL_COLORS sale del registro (un solo lugar para los colores)', () => {
  assert.deepEqual(
    NAV_PILL_COLORS,
    Object.fromEntries(TOOLS.map((tool) => [tool.path, tool.colors])),
  )
})

test('la presencia legada es la de origin/main: fondo 0d/18, borde 2a, texto activo = acento', () => {
  assert.deepEqual(PILL_TINT_ALPHA, { idle: '0d', active: '18' })
  assert.equal(PILL_BORDER_ALPHA, '2a')
  const colors = { accent: '#c8a84b', label: '#937e3e' }
  assert.equal(pillLabelColor(colors, 'idle'), '#937e3e')
  assert.equal(pillLabelColor(colors, 'active'), '#c8a84b')
})

test('la presencia de capa es la de la maqueta: tinte 13 %/22 %, borde 34 %/85 %', () => {
  assert.deepEqual(LAYER_PRESENCE.tint, { idle: '21', hover: '38' })
  assert.deepEqual(LAYER_PRESENCE.border, { idle: '57', hover: 'd9' })
  const alpha = (hex: string) => Math.round((parseInt(hex, 16) / 255) * 100)
  assert.deepEqual([alpha('21'), alpha('38'), alpha('57'), alpha('d9')], [13, 22, 34, 85])
})

test('pill de capa: texto claro en reposo y hover, tinta sobre el color pleno cuando es la página actual', () => {
  const colors = { accent: '#7db9f2', label: '#dcebfc' }
  assert.equal(layerPillLabelColor(colors, LAYER_INK, 'idle'), '#dcebfc')
  assert.equal(layerPillLabelColor(colors, LAYER_INK, 'hover'), '#dcebfc')
  assert.equal(layerPillLabelColor(colors, LAYER_INK, 'current'), LAYER_INK)
  assert.equal(layerPillBackground('#7db9f2', '#060d1a', 'current'), '#7db9f2')
  assert.equal(layerPillBackground('#7db9f2', '#060d1a', 'idle'), blendHex('#7db9f2', '#060d1a', 0x21 / 255))
})

test('todas las pills tienen texto >= 4,5:1 contra su fondo real, en cada estado', () => {
  const surface = cssToken('color-background')
  const failures: string[] = []
  for (const [route, colors] of Object.entries(NAV_PILL_COLORS)) {
    const ratios = lookOf(route) === 'legacy'
      ? STATES.map((state) => [state, pillLabelContrast(colors, surface, state)] as const)
      : LAYER_STATES.map((state) => [state, layerPillContrast(colors, LAYER_INK, surface, state)] as const)
    for (const [state, ratio] of ratios) {
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
