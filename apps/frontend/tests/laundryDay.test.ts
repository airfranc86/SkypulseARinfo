import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { isQualifiedBest, laundryDayView, qualifiedBestDay } from '../src/lib/laundryDay.ts'
import { LABEL_COLOR, type QualityLabel } from '../src/lib/qualityScale.ts'

const GOLD = '#c8a84b'
const LABELS: readonly QualityLabel[] = ['Excelente', 'Bueno', 'Regular', 'No apto']

type Fixture = Parameters<typeof laundryDayView>[0] & { date: string; confidence_pct: number }

function day(over: Partial<Fixture> = {}): Fixture {
  return {
    label: 'Bueno',
    score: 60,
    is_best: false,
    day_label: 'Sáb 10/10',
    date: '2026-10-10',
    confidence_label: 'Alta',
    confidence_pct: 90,
    ...over,
  }
}

// Same rule as apps/backend/app/routers/tools.py::_confidence_label and its fixed curve.
const BACKEND_CONFIDENCE: [number, 'Alta' | 'Media' | 'Baja'][] = [
  [95, 'Alta'], [93, 'Alta'], [90, 'Alta'], [87, 'Alta'], [83, 'Media'], [80, 'Media'], [75, 'Media'],
]

test('the label color always comes from the scale, best day or not, never gold', () => {
  for (const label of LABELS) {
    for (const is_best of [true, false]) {
      const view = laundryDayView(day({ label, is_best }))
      assert.equal(view.labelColor, LABEL_COLOR[label], `${label} best=${is_best}`)
      assert.notEqual(view.labelColor.toLowerCase(), GOLD)
    }
  }
})

test('an unexpected or missing label falls back to the scale color of the score', () => {
  const cases: [number, string][] = [
    [90, LABEL_COLOR.Excelente], [60, LABEL_COLOR.Bueno], [40, LABEL_COLOR.Regular], [10, LABEL_COLOR['No apto']],
  ]
  for (const [score, color] of cases) {
    for (const label of ['Raro', undefined, null, '', 'toString']) {
      const view = laundryDayView(day({ label: label as never, score }))
      assert.equal(view.labelColor, color, `label ${String(label)} score ${score}`)
      assert.ok(!view.labelColor.includes('undefined'))
    }
  }
})

test('"Mejor día" shows only for the best day when it is Excelente or Bueno', () => {
  assert.equal(laundryDayView(day({ label: 'Excelente', is_best: true })).showBestBadge, true)
  assert.equal(laundryDayView(day({ label: 'Bueno', is_best: true })).showBestBadge, true)
  assert.equal(laundryDayView(day({ label: 'Regular', is_best: true })).showBestBadge, false)
  assert.equal(laundryDayView(day({ label: 'No apto', is_best: true })).showBestBadge, false)
  assert.equal(laundryDayView(day({ label: 'Excelente', is_best: false })).showBestBadge, false)
})

test('an unexpected label judges the best-day floor by the score too', () => {
  assert.equal(laundryDayView(day({ label: 'Raro' as never, score: 80, is_best: true })).showBestBadge, true)
  assert.equal(laundryDayView(day({ label: 'Raro' as never, score: 20, is_best: true })).showBestBadge, false)
})

test('isQualifiedBest: needs is_best and Excelente or Bueno', () => {
  assert.equal(isQualifiedBest(day({ label: 'Excelente', is_best: true })), true)
  assert.equal(isQualifiedBest(day({ label: 'Bueno', is_best: true })), true)
  assert.equal(isQualifiedBest(day({ label: 'Regular', is_best: true })), false)
  assert.equal(isQualifiedBest(day({ label: 'No apto', is_best: true })), false)
  assert.equal(isQualifiedBest(day({ label: 'Excelente', is_best: false })), false)
})

test('qualifiedBestDay: the backend best day when it reaches Bueno, none otherwise', () => {
  const good = [day({ date: 'a', label: 'Regular' }), day({ date: 'b', label: 'Bueno', is_best: true })]
  assert.equal(qualifiedBestDay(good)?.date, 'b')

  const weak = [day({ date: 'a', label: 'No apto' }), day({ date: 'b', label: 'Regular', is_best: true })]
  assert.equal(qualifiedBestDay(weak), null)
  assert.ok(weak.every((d) => !laundryDayView(d).showBestBadge), 'nobody is marked')

  assert.equal(qualifiedBestDay([day(), day()]), null)
  assert.equal(qualifiedBestDay([]), null)
})

test('two days flagged is_best: the first one wins', () => {
  const days = [day({ date: 'a', label: 'Bueno', is_best: true }), day({ date: 'b', label: 'Excelente', is_best: true })]
  assert.equal(qualifiedBestDay(days)?.date, 'a')
})

test('a tie in score: only the day the backend flagged (the first) is marked', () => {
  const days = [
    day({ date: 'a', label: 'Bueno', score: 70, is_best: true }),
    day({ date: 'b', label: 'Bueno', score: 70 }),
  ]
  assert.equal(qualifiedBestDay(days)?.date, 'a')
  assert.deepEqual(days.map((d) => laundryDayView(d).showBestBadge), [true, false])
})

test('car wash days (same shape) get the same floor: a Regular best day gets no star, no hero, no bar label', () => {
  const days = [
    { date: 'a', label: 'No apto' as const, score: 10, is_best: false },
    { date: 'b', label: 'Regular' as const, score: 45, is_best: true },
  ]
  assert.equal(qualifiedBestDay(days), null)
  assert.equal(qualifiedBestDay(days)?.label ?? '', '')
  assert.ok(days.every((d) => !isQualifiedBest(d)))
  const good = [{ date: 'a', label: 'Excelente' as const, score: 88, is_best: true }]
  assert.equal(qualifiedBestDay(good)?.label, 'Excelente')
})

test('confidence: "Confianza media" for the days the backend rates Media, also on the best day', () => {
  for (const [pct, conf] of BACKEND_CONFIDENCE) {
    const expected = conf === 'Media' ? 'Confianza media' : null
    const common = { confidence_pct: pct, confidence_label: conf }
    assert.equal(laundryDayView(day(common)).confidenceText, expected, `pct ${pct}`)
    assert.equal(laundryDayView(day({ ...common, label: 'Excelente', is_best: true })).confidenceText, expected, `best pct ${pct}`)
  }
})

test('the backend curve never reaches "Baja", so no low-confidence text shows today', () => {
  for (const [pct, conf] of BACKEND_CONFIDENCE) {
    const text = laundryDayView(day({ confidence_pct: pct, confidence_label: conf })).confidenceText
    assert.ok(text === null || !/baja/i.test(text))
  }
  // The text comes from the backend label, not from a percentage cutoff in the card.
  assert.equal(laundryDayView(day({ confidence_pct: 60, confidence_label: 'Alta' })).confidenceText, null)
})

test('if the backend ever rates a day "Baja", it says so instead of staying silent', () => {
  assert.equal(laundryDayView(day({ confidence_label: 'Baja' })).confidenceText, 'Confianza baja')
  assert.equal(
    laundryDayView(day({ confidence_label: 'Baja', label: 'Excelente', is_best: true })).confidenceText,
    'Confianza baja',
  )
})

test('the day is written once: the readable day_label, with no ISO date next to it', () => {
  const view = laundryDayView(day())
  assert.equal(view.dayText, 'Sáb 10/10')
  assert.ok(!view.dayText.includes('2026-10-10'))
})

const read = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8')

test('LaundryDayCard only draws what laundryDayView returns', () => {
  const source = read('../src/components/ui/LaundryDayCard.tsx')
  assert.match(source, /laundryDayView\(/)
  assert.ok(!/day\.date/.test(source), 'the card prints day.date again')
  assert.ok(!/confidence_pct/.test(source), 'the confidence rule is back in the card')
  assert.ok(!/day\.is_best/.test(source), 'the best-day rule is back in the card')
  assert.ok(!/Baja confianza/.test(source))
  assert.match(source, /aria-hidden="true"[^>]*>\s*✦/, 'the decorative star is not hidden from screen readers')
})

test('TenderRopa marks the scale with the same qualified best day as the cards', () => {
  const source = read('../src/pages/TenderRopa.tsx')
  assert.match(source, /qualifiedBestDay\(/)
  assert.ok(!/\.is_best/.test(source), 'TenderRopa reads is_best directly')
})

test('LavarCoche applies the same best-day floor and no longer reads is_best by hand', () => {
  const source = read('../src/pages/LavarCoche.tsx')
  assert.match(source, /qualifiedBestDay\(/)
  assert.match(source, /isQualifiedBest\(/)
  assert.ok(!/\.is_best/.test(source), 'LavarCoche reads is_best directly')
})

test('LavarCoche pill: not 10 px text, solid card background, tints from the label rather than day.color', () => {
  const source = read('../src/pages/LavarCoche.tsx')
  assert.ok(!/text-\[10px\]/.test(source), 'pill text is 10 px again')
  assert.ok(!/\$\{barColor\}20/.test(source), 'pill is tinted over the row tint again')
  assert.ok(!/day\.color/.test(source), 'the row tint reads day.color again')
})
