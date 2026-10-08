import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  PRECISION_THRESHOLDS,
  RANGE_LABEL,
  SNOW_SCALE,
  SNOW_THRESHOLDS,
  SPREAD_LABEL,
  groupThousands,
  methodsRange,
  precisionLabel,
  rangeText,
  scaleAriaLabel,
  snowStatus,
  spreadText,
} from '../src/lib/cotaDeNieve.ts'
import { SNOW_STATUS_ICONS } from '../src/lib/toolIcons.ts'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

/** Every cota from 0 to 4000 m in steps of 50, plus each boundary and its neighbours. */
const SWEEP: number[] = [
  ...Array.from({ length: 81 }, (_, i) => i * 50),
  ...[-3, -0.4, 0.4, 999, 999.4, 999.5, 1000, 1000.1, 1799, 1799.4, 1799.5, 1800, 1800.1, 2499, 2499.4, 2499.5, 2499.9, 2500, 2500.1],
]

// ── Thresholds: one source of truth ──────────────────────────────────────────

test('the snow thresholds are 2500, 1800 and 1000 m', () => {
  assert.deepEqual({ ...SNOW_THRESHOLDS }, { veryHigh: 2500, high: 1800, medium: 1000 })
})

test('snowStatus switches band exactly at each threshold', () => {
  assert.equal(snowStatus(2500).key, 'veryHigh')
  assert.equal(snowStatus(2499.4).key, 'high')
  assert.equal(snowStatus(1800).key, 'high')
  assert.equal(snowStatus(1799.4).key, 'medium')
  assert.equal(snowStatus(1000).key, 'medium')
  assert.equal(snowStatus(999.4).key, 'low')
  assert.equal(snowStatus(0).key, 'low')
})

test('the band is decided on the rounded metres the card shows', () => {
  // 2499.5 shows as "2.500": it must be the very-high band, not "high".
  assert.equal(snowStatus(2499.4).key, 'high')
  assert.equal(snowStatus(2499.5).key, 'veryHigh')
  assert.equal(snowStatus(2499.9).key, 'veryHigh')
  assert.equal(snowStatus(1799.4).key, 'medium')
  assert.equal(snowStatus(1799.5).key, 'high')
  assert.equal(snowStatus(999.4).key, 'low')
  assert.equal(snowStatus(999.5).key, 'medium')
})

test('the number in the message and the band never disagree', () => {
  for (const avg of SWEEP) {
    const shown = Math.round(avg)
    const key = snowStatus(avg).key
    const expected = shown >= 2500 ? 'veryHigh' : shown >= 1800 ? 'high' : shown >= 1000 ? 'medium' : 'low'
    assert.equal(key, expected, `${avg} shows as ${shown}`)
  }
})

test('SNOW_SCALE has one entry per band, from the highest cota to the lowest', () => {
  assert.deepEqual(SNOW_SCALE.map((s) => s.key), ['veryHigh', 'high', 'medium', 'low'])
})

test('the scale bar and the status card always point at the same band', () => {
  for (const avg of SWEEP) {
    const status = snowStatus(avg)
    const entry = SNOW_SCALE.find((s) => s.key === status.key)
    assert.ok(entry, `no scale entry for ${status.key} at ${avg}`)
    assert.equal(entry.label, status.scaleLabel, `scale label differs at ${avg}`)
    assert.equal(entry.color, status.color, `colour differs at ${avg}`)
  }
})

test('changing a threshold moves the status (the thresholds are the only source)', () => {
  // 2450 m is "high" only because the very-high threshold is above it.
  assert.equal(snowStatus(SNOW_THRESHOLDS.veryHigh - 50).key, 'high')
  assert.equal(snowStatus(SNOW_THRESHOLDS.high - 50).key, 'medium')
  assert.equal(snowStatus(SNOW_THRESHOLDS.medium - 50).key, 'low')
})

test('the page does not repeat the thresholds in comparisons', () => {
  const page = read('../src/pages/CotaDeNieve.tsx')
  assert.ok(!/[<>]=?\s*(2_?500|1_?800|1_?000)\b/.test(page), 'CotaDeNieve.tsx compares against a threshold literal')
  assert.ok(!/\b(2_?500|1_?800)\b/.test(page), 'CotaDeNieve.tsx repeats a threshold number')
  assert.match(page, /from '@\/lib\/cotaDeNieve'/)
})

test('the page feeds the lib with the average and the three methods', () => {
  const page = read('../src/pages/CotaDeNieve.tsx')
  assert.match(page, /snowStatus\(data\.average_m\)/)
  assert.match(page, /methodsRange\(\s*data\.alcaide_m,\s*data\.gradiente_m,\s*data\.m850_hpa_m\s*\)/)
  assert.match(page, /precisionLabel\(\s*data\.alcaide_m,\s*data\.gradiente_m,\s*data\.m850_hpa_m\s*\)/)
  assert.match(page, /rangeText\(range\)/)
  assert.match(page, /spreadText\(range\.spread\)/)
})

test('the page formats every number of the card with groupThousands', () => {
  const page = read('../src/pages/CotaDeNieve.tsx')
  assert.ok(!page.includes("toLocaleString('es-AR')"), 'mixed thousands formatting')
  assert.ok(!page.includes('average_m.toFixed(0)'), 'mixed thousands formatting')
  assert.match(page, /groupThousands\(Math\.round\(data\.average_m\)\)/)
})

test('the method is called Alcaide, not Alcaidé', () => {
  const page = read('../src/pages/CotaDeNieve.tsx')
  assert.ok(!page.includes('Alcaidé'))
  assert.ok(page.includes("label: 'Alcaide'"))
})

test('groupThousands separates thousands with a dot', () => {
  assert.equal(groupThousands(0), '0')
  assert.equal(groupThousands(999), '999')
  assert.equal(groupThousands(1000), '1.000')
  assert.equal(groupThousands(2500), '2.500')
  assert.equal(groupThousands(1234567), '1.234.567')
  assert.equal(groupThousands(-2500), '-2.500')
})

// ── The scale is informative: no good or bad judgment ────────────────────────

const JUDGMENT = /\b(excelentes?|abundante|ideal|favorable|buenas?|malas?|moderadas?)\b|centros? de esqu|hasta en zonas altas/i

test('no cota gets the old inverted or judgmental texts', () => {
  for (const avg of SWEEP) {
    const s = snowStatus(avg)
    for (const text of [s.label, s.msg, s.scaleLabel]) {
      assert.ok(!JUDGMENT.test(text), `"${text}" at ${avg} m reads as a judgment`)
    }
  }
  for (const entry of SNOW_SCALE) {
    assert.ok(!JUDGMENT.test(entry.label), `scale label "${entry.label}" reads as a judgment`)
  }
})

test('the page source no longer holds the old judgment texts', () => {
  const page = read('../src/pages/CotaDeNieve.tsx')
  assert.ok(!JUDGMENT.test(page), 'CotaDeNieve.tsx still has a judgmental text')
})

test('the four band messages are fixed, conditional and parallel', () => {
  assert.equal(snowStatus(2600).msg, 'Si precipita, la lluvia llega hasta unos 2.600 m y nieva por encima.')
  assert.equal(snowStatus(2000).msg, 'Si precipita, la lluvia llega hasta unos 2.000 m y nieva por encima.')
  assert.equal(snowStatus(1400).msg, 'Si precipita, nieva desde unos 1.400 m; por debajo cae como lluvia.')
  assert.equal(snowStatus(600).msg, 'La cota ronda los 600 m: puede nevar a baja altura.')
})

test('the band titles and scale labels are fixed', () => {
  assert.deepEqual(
    [2600, 2000, 1400, 600].map((a) => snowStatus(a).label),
    ['Cota muy alta', 'Cota alta', 'Cota media', 'Cota baja'],
  )
  assert.deepEqual(SNOW_SCALE.map((s) => s.label), ['Muy alta', 'Alta', 'Media', 'Baja'])
})

test('no message states that it is raining or snowing now', () => {
  for (const avg of SWEEP) {
    const { msg } = snowStatus(avg)
    assert.ok(/^Si precipita|puede nevar/.test(msg), `"${msg}" is not conditional`)
    assert.ok(!/—|–/.test(msg), 'long dash')
  }
})

test('a snow line at sea level or below has its own text, without "0 m"', () => {
  const text = 'La cota está a nivel del mar o por debajo: puede nevar a baja altura.'
  assert.equal(snowStatus(0).msg, text)
  assert.equal(snowStatus(-12).msg, text)
  assert.equal(snowStatus(0.4).msg, text)
  assert.equal(snowStatus(-0.4).msg, text)
  assert.ok(!/ 0 m/.test(snowStatus(0).msg))
  assert.equal(snowStatus(0.5).msg, 'La cota ronda los 1 m: puede nevar a baja altura.')
})

test('the message uses the rounded average with the same thousands format', () => {
  assert.match(snowStatus(2775.4).msg, /2\.775 m/)
  assert.match(snowStatus(2499.6).msg, /2\.500 m/)
})

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) =>
    v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4,
  )
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)]
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05)
}

const CARD_BG = '#0d1e38'

test('the scale colours are a neutral blue gradient, never green to red', () => {
  const colors = [...SNOW_SCALE.map((s) => s.color), ...SWEEP.map((a) => snowStatus(a).color)]
  for (const color of colors) {
    assert.match(color, /^#[0-9a-f]{6}$/i)
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(color.slice(i, i + 2), 16))
    assert.ok(b > g && g >= r, `${color} is not a blue (r=${r}, g=${g}, b=${b})`)
  }
  assert.equal(new Set(SNOW_SCALE.map((s) => s.color)).size, SNOW_SCALE.length, 'bands share a colour')
})

test('every scale colour has WCAG contrast of at least 4.5:1 on the card', () => {
  for (const { key, color } of SNOW_SCALE) {
    assert.ok(contrast(color, CARD_BG) >= 4.5, `${key} ${color} has ${contrast(color, CARD_BG).toFixed(2)}:1`)
  }
})

test('the higher the snow line, the lighter the colour', () => {
  const lums = SNOW_SCALE.map((s) => luminance(s.color))
  for (let i = 1; i < lums.length; i++) assert.ok(lums[i] < lums[i - 1], `band ${i} is not darker than band ${i - 1}`)
})

test('the scale announces the current band for screen readers', () => {
  assert.equal(scaleAriaLabel(2600), 'Cota de nieve: muy alta, escala de cuatro tramos')
  assert.equal(scaleAriaLabel(2000), 'Cota de nieve: alta, escala de cuatro tramos')
  assert.equal(scaleAriaLabel(1400), 'Cota de nieve: media, escala de cuatro tramos')
  assert.equal(scaleAriaLabel(0), 'Cota de nieve: baja, escala de cuatro tramos')
})

test('the scale bar is accessible and respects reduced motion', () => {
  const page = read('../src/pages/CotaDeNieve.tsx')
  assert.match(page, /role="img"/)
  assert.match(page, /aria-label=\{scaleAriaLabel\(avg\)\}/)
  assert.match(page, /aria-hidden="true"/)
  assert.match(page, /motion-reduce:transition-none/)
  assert.ok(!/text-\[\.[0-5]\d*rem\]/.test(page), 'scale labels are too small')
  assert.match(page, /text-\[\.65rem\]/)
})

// ── Icons follow the informative reading ─────────────────────────────────────

test('every band has a status icon (and only the bands)', () => {
  assert.deepEqual(Object.keys(SNOW_STATUS_ICONS).sort(), SNOW_SCALE.map((s) => s.key).sort())
})

// ── Range, spread and precision agree ────────────────────────────────────────

test('methodsRange uses the three methods and the total spread', () => {
  // The real case of the bug: Alcaide 2797, gradient 2935, 850 hPa 2593.
  assert.deepEqual(methodsRange(2797, 2935, 2593), { min: 2593, max: 2935, spread: 342 })
})

test('methodsRange without the 850 hPa method uses the other two', () => {
  assert.deepEqual(methodsRange(2797, 2935, null), { min: 2797, max: 2935, spread: 138 })
  assert.deepEqual(methodsRange(2935, 2797, null), { min: 2797, max: 2935, spread: 138 })
})

test('methodsRange must include the 850 hPa value at either end', () => {
  assert.equal(methodsRange(1000, 1200, 1800).max, 1800)
  assert.equal(methodsRange(1000, 1200, 400).min, 400)
})

test('methodsRange ignores a missing or non-finite 850 hPa value', () => {
  const two = { min: 2797, max: 2935, spread: 138 }
  assert.deepEqual(methodsRange(2797, 2935, undefined), two)
  assert.deepEqual(methodsRange(2797, 2935, Number.NaN), two)
  assert.deepEqual(methodsRange(2797, 2935, Number.POSITIVE_INFINITY), two)
  assert.deepEqual(methodsRange(2797, 2935, Number.NEGATIVE_INFINITY), two)
  assert.equal(precisionLabel(2797, 2935, undefined).label, 'Alta precisión')
  assert.equal(precisionLabel(2797, 2935, Number.NaN).spread, 138)
})

test('the displayed difference is the max minus the min of the displayed range', () => {
  const r = methodsRange(2000.4, 2199.6, null)
  assert.equal(r.spread, r.max - r.min)
  assert.deepEqual(r, { min: 2000, max: 2200, spread: 200 })
})

test('range and difference texts', () => {
  const r = methodsRange(2797, 2935, 2593)
  assert.equal(rangeText(r), '2.593 a 2.935 m')
  assert.equal(spreadText(r.spread), '342 m')
  assert.equal(RANGE_LABEL, 'Rango de los métodos:')
  assert.equal(SPREAD_LABEL, 'Diferencia entre métodos:')
})

test('the difference text is the total, never a half or a plus-minus', () => {
  const text = `${SPREAD_LABEL} ${spreadText(methodsRange(2797, 2935, 2593).spread)}`
  assert.equal(text, 'Diferencia entre métodos: 342 m')
  assert.ok(!text.includes('±'))
  assert.ok(!text.includes('171'))
  assert.ok(!read('../src/pages/CotaDeNieve.tsx').includes('±'))
})

test('rangeText when all the methods agree shows a single value', () => {
  assert.equal(rangeText(methodsRange(1500, 1500, 1500)), '1.500 m')
})

test('precision thresholds are 200 and 500 m', () => {
  assert.deepEqual({ ...PRECISION_THRESHOLDS }, { high: 200, medium: 500 })
})

test('precisionLabel compares the TOTAL spread with 200 and 500', () => {
  assert.equal(precisionLabel(1000, 1199, null).label, 'Alta precisión')
  assert.equal(precisionLabel(1000, 1200, null).label, 'Precisión media')
  assert.equal(precisionLabel(1000, 1499, null).label, 'Precisión media')
  assert.equal(precisionLabel(1000, 1500, null).label, 'Estimación variable')
})

test('precisionLabel returns the total spread and counts the 850 hPa method', () => {
  const p = precisionLabel(2797, 2935, 2593)
  assert.equal(p.spread, 342)
  assert.equal(p.label, 'Precisión media')
  // Without the 850 hPa method the spread is 138 and the label changes.
  assert.equal(precisionLabel(2797, 2935, null).label, 'Alta precisión')
})

test('precisionLabel decides on the same rounded numbers the page shows', () => {
  // 199.6 raw would be "alta", but the page shows 2000 a 2200 (a difference of 200 m).
  const p = precisionLabel(2000.4, 2199.6, null)
  assert.equal(p.spread, 200)
  assert.equal(p.label, 'Precisión media')
})

test('range, average and precision agree for many combinations', () => {
  const values = [0, 120, 800, 1450, 1999, 2593, 2775, 2935, 3400]
  for (const a of values) for (const g of values) for (const m of [...values, null]) {
    const range = methodsRange(a, g, m)
    const methods = [a, g, ...(m === null ? [] : [m])]
    for (const v of methods) assert.ok(range.min <= Math.round(v) && Math.round(v) <= range.max)
    const average = methods.reduce((x, y) => x + y, 0) / methods.length
    assert.ok(range.min <= average && average <= range.max)
    const p = precisionLabel(a, g, m)
    assert.equal(p.spread, range.spread)
    const expected = range.spread < 200 ? 'Alta precisión' : range.spread < 500 ? 'Precisión media' : 'Estimación variable'
    assert.equal(p.label, expected)
  }
})

test('the lib is a pure module: relative imports, no alias, no import.meta.env', () => {
  const lib = read('../src/lib/cotaDeNieve.ts')
  assert.ok(!lib.includes('import.meta.env'))
  assert.ok(!/from '@\//.test(lib))
  assert.ok(!lib.includes('±'))
})
