import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { LABEL_COLOR, resolveLabel, scoreToLabel, type QualityLabel } from '../src/lib/qualityScale.ts'
import { MIN_TEXT_CONTRAST, contrastRatio } from '../src/lib/navContrast.ts'

/** Background of the cards where the scale is drawn (`--color-card` in index.css). */
const CARD = '#0d1e38'
/** Minimum CIE76 delta E between two consecutive labels of the scale. */
const MIN_DELTA_E = 25

const ORDER: readonly QualityLabel[] = ['Excelente', 'Bueno', 'Regular', 'No apto']

// ── CIE76 delta E (sRGB, D65), test-only ─────────────────────────────────────

function toLab(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  const x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
  const y = 0.2126729 * r + 0.7151522 * g + 0.072175 * b
  const z = (0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : ((24389 / 27) * t + 16) / 116)
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))]
}

function deltaE76(a: string, b: string): number {
  const [la, aa, ba] = toLab(a)
  const [lb, ab, bb] = toLab(b)
  return Math.hypot(la - lb, aa - ab, ba - bb)
}

test('deltaE76 helper: identical colors are 0, black vs white is 100', () => {
  assert.equal(deltaE76('#336699', '#336699'), 0)
  assert.ok(Math.abs(deltaE76('#000000', '#ffffff') - 100) < 0.01)
})

test('the scale has the four labels, each with its own hex color', () => {
  assert.deepEqual(Object.keys(LABEL_COLOR).sort(), [...ORDER].sort())
  for (const label of ORDER) assert.match(LABEL_COLOR[label], /^#[0-9a-f]{6}$/)
  assert.equal(new Set(Object.values(LABEL_COLOR)).size, 4)
})

for (let i = 0; i < ORDER.length - 1; i++) {
  const [a, b] = [ORDER[i], ORDER[i + 1]]
  test(`consecutive labels ${a} / ${b} are at least ${MIN_DELTA_E} delta E apart`, () => {
    const d = deltaE76(LABEL_COLOR[a], LABEL_COLOR[b])
    assert.ok(d >= MIN_DELTA_E, `${a} ${LABEL_COLOR[a]} vs ${b} ${LABEL_COLOR[b]}: delta E ${d.toFixed(1)}`)
  })
}

for (const label of ORDER) {
  test(`${label} text reaches ${MIN_TEXT_CONTRAST}:1 over the card background`, () => {
    const ratio = contrastRatio(LABEL_COLOR[label], CARD)
    assert.ok(ratio >= MIN_TEXT_CONTRAST, `${label} ${LABEL_COLOR[label]}: ${ratio.toFixed(2)}:1`)
  })
}

test('scoreToLabel repeats the backend cutoffs 75 / 50 / 30 (calculators._label_and_color)', () => {
  const cases: [number, QualityLabel][] = [
    [100, 'Excelente'], [75, 'Excelente'],
    [74, 'Bueno'], [50, 'Bueno'],
    [49, 'Regular'], [30, 'Regular'],
    [29, 'No apto'], [0, 'No apto'],
  ]
  for (const [score, label] of cases) assert.equal(scoreToLabel(score), label, `score ${score}`)
})

test('consumers read the scale from the single source, with no hex of it repeated by hand', () => {
  const retired = ['#e05545', '#ff6b6b']
  const hexes = [...Object.values(LABEL_COLOR), ...retired]
  for (const file of ['../src/pages/LavarCoche.tsx', '../src/components/ui/QualityScaleBar.tsx']) {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8').toLowerCase()
    for (const hex of hexes) assert.ok(!source.includes(hex), `${file} repeats ${hex}`)
    assert.ok(!/rgba\(\s*(62,\s*207,\s*122|224,\s*85,\s*69|155,\s*32,\s*32)/.test(source), `${file} repeats an rgba of the scale`)
  }
})

test('resolveLabel keeps a known label and falls back to the score for anything else', () => {
  for (const label of ORDER) assert.equal(resolveLabel({ label, score: 0 }), label)
  for (const label of ['Raro', '', undefined, null, 'toString', '__proto__']) {
    assert.equal(resolveLabel({ label, score: 80 }), 'Excelente', String(label))
    assert.equal(resolveLabel({ label, score: 10 }), 'No apto', String(label))
  }
})

test('QualityScaleBar keeps the bars solid and the scale text readable', () => {
  const source = readFileSync(new URL('../src/components/ui/QualityScaleBar.tsx', import.meta.url), 'utf8')
  const opacities = [...source.matchAll(/opacity:\s*([0-9.]+)/g)].map((m) => Number(m[1]))
  assert.ok(opacities.length > 0, 'the bars should state their opacity')
  for (const o of opacities) assert.ok(o >= 0.85, `bar opacity ${o} dims the colors`)
  assert.ok(!/\bopacity-\d+\b/.test(source), 'a Tailwind opacity class dims the scale')
  const sizes = [...source.matchAll(/text-\[(\.\d+)rem\]/g)].map((m) => Number(m[1]))
  assert.ok(sizes.length >= 2, 'title and labels state their size')
  for (const size of sizes) assert.ok(size >= 0.65, `text-[${size}rem] is under .65rem`)
})
