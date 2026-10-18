import { test } from 'node:test'
import assert from 'node:assert/strict'
import { alturaMaximaDelPanel, desplazamientoInferior } from '../src/lib/asistente/viewport.ts'

// On iOS Safari the on-screen keyboard does not resize the layout viewport: an element fixed to the bottom hides behind
// it. The visual viewport says how much of the screen is really visible; the panel lifts itself by the difference.
// Pure: the sizes come in as numbers, the hook only reads them from `window.visualViewport`.

test('without a keyboard the panel stays at the bottom', () => {
  assert.equal(desplazamientoInferior(800, 800, 0), 0)
})

test('with the keyboard open the panel lifts by what it covers', () => {
  assert.equal(desplazamientoInferior(800, 500, 0), 300)
})

test('a visual viewport scrolled down (pinch-zoom, the page pushed up) counts too', () => {
  assert.equal(desplazamientoInferior(800, 500, 40), 260)
})

test('it never goes negative nor lifts by a fraction of a pixel', () => {
  assert.equal(desplazamientoInferior(800, 820, 0), 0)
  assert.equal(desplazamientoInferior(800, 799.6, 0), 0)
  assert.equal(desplazamientoInferior(800, 500.4, 0), 300)
})

test('missing or odd numbers mean no lift', () => {
  for (const [a, b, c] of [[Number.NaN, 500, 0], [800, undefined, 0], [800, 500, Number.NaN], [undefined, undefined, undefined]] as const) {
    assert.equal(desplazamientoInferior(a as number, b as number, c as number), 0)
  }
})

test('the maximum height is the visible height minus the margins, and the usual 85 % of the screen otherwise', () => {
  assert.equal(alturaMaximaDelPanel(800, 800, 24), 680) // 85 % of 800
  assert.equal(alturaMaximaDelPanel(800, 500, 24), 476) // the keyboard leaves 500: 500 - 24
  assert.equal(alturaMaximaDelPanel(800, 100, 24), 200) // never smaller than a usable minimum
})

test('the maximum height falls back to 85 % of the window when the visual viewport is unknown', () => {
  assert.equal(alturaMaximaDelPanel(800, undefined, 24), 680)
  assert.equal(alturaMaximaDelPanel(Number.NaN, undefined, 24), 200)
})

// ── On a wide screen the card floats above the bubble: that separation is not available height ──

test('the margin counts: a wide-screen card leaves room for the bubble under it', () => {
  assert.equal(alturaMaximaDelPanel(657, 657, 24 + 108), 525) // a laptop: 657 - 132, not 85 % of 657
  assert.equal(alturaMaximaDelPanel(300, 300, 24 + 108), 200) // 200 % zoom: never below the usable minimum
})

test('with an unknown visual viewport the window height is the visible height, margin included', () => {
  assert.equal(alturaMaximaDelPanel(400, undefined, 24 + 108), 268)
  assert.equal(alturaMaximaDelPanel(800, undefined, 24), 680)
})
