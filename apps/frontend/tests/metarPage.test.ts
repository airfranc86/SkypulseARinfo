import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const metar = read('../src/pages/Metar.tsx')

// FRA-367 parte 2: the cards of the decoded METAR use lib/metarDecode.ts; the page keeps no copy of that logic.

test('the page takes its card texts from lib/metarDecode and keeps no local copy', () => {
  assert.ok(metar.includes("from '@/lib/metarDecode'"), 'Metar.tsx does not import lib/metarDecode')
  assert.ok(!/function visNote\b/.test(metar), 'a local visNote is still in the page')
  assert.ok(!/function cloudNote\b/.test(metar), 'a local cloudNote is still in the page')
})

test('the report time is no longer printed with toUTCString (it can be 3 h off and says GMT in English)', () => {
  assert.ok(!metar.includes('toUTCString'), 'toUTCString is still used')
  assert.ok(metar.includes('observedLabel('), 'observedLabel is not used')
})

test('wind, dew point and QNH go through the pure functions, not through inline template strings', () => {
  assert.ok(metar.includes('windDisplay('), 'windDisplay is not used')
  assert.ok(!/'VRB'\}°/.test(metar), 'the "VRB°" template is still in the page')
  assert.ok(metar.includes('dewpointText('), 'dewpointText is not used')
  assert.ok(!/Rocío \$\{dewC\}/.test(metar), 'the "Rocío undefined" template is still in the page')
  assert.ok(metar.includes('qnhHpa(') && metar.includes('qnhNote('), 'QNH is not read through qnhHpa/qnhNote')
  assert.ok(!/qnhHpa !== undefined/.test(metar), 'a null QNH can still pass as a value')
})

test('the flight category cards come from FLIGHT_CATEGORY_RULES (miles with kilometres)', () => {
  assert.ok(metar.includes('FLIGHT_CATEGORY_RULES.map('), 'the category cards are not rendered from FLIGHT_CATEGORY_RULES')
  assert.ok(!/Visib\. > 5 km/.test(metar), 'the old "Visib. > 5 km" text is still in the page')
})
