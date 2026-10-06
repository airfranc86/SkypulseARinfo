import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { DATA_SOURCES } from '../src/data/dataSources.ts'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')
const metar = read('../src/pages/Metar.tsx')

// FRA-365: the METAR page shows the decoded TAF from GET /api/taf (Aviation Weather Center).

test('Metar reads the TAF through api.tafDecoded, not through a raw fetch of the CheckWX raw TAF', () => {
  assert.ok(metar.includes('api.tafDecoded('), 'does not call api.tafDecoded')
  assert.ok(!metar.includes('type=taf'), 'still fetches the raw TAF with type=taf')
  assert.ok(!/\bfetch\(/.test(metar), 'Metar.tsx still calls fetch directly')
})

test('a late TAF answer cannot overwrite the TAF of a newer query', () => {
  const start = metar.indexOf('const fetchTAF')
  assert.ok(start > -1, 'fetchTAF not found')
  const body = metar.slice(start, metar.indexOf('const doFetch', start))
  assert.ok(/isCurrent/.test(body), 'fetchTAF does not check isCurrent()')
  assert.ok(metar.includes('fetchTAF(clean, isCurrent)'), 'doFetch does not pass isCurrent to fetchTAF')
})

test('the decoded TAF card is rendered and the raw TAF stays available', () => {
  assert.ok(metar.includes('<TafDecodedCard'), 'TafDecodedCard is not rendered')
  const card = read('../src/components/aeronautica/TafDecodedCard.tsx')
  assert.ok(card.includes('<details'), 'the raw TAF is not offered in a <details>')
  assert.ok(card.includes('taf.raw'), 'the raw TAF is not shown')
})

test('the TAF block credits the Aviation Weather Center and the page keeps crediting CheckWX', () => {
  const card = read('../src/components/aeronautica/TafDecodedCard.tsx')
  assert.ok(/Aviation Weather Center/.test(card), 'the card does not credit AWC')
  assert.ok(metar.includes('aviationweather.gov'), 'the page footer does not link AWC')
  assert.ok(metar.includes('checkwx.com'), 'the page footer lost the CheckWX credit')
})

test('the glossary explains the TAF groups the decoded block uses', () => {
  const start = metar.indexOf('const GLOSARIO')
  const glossary = metar.slice(start, metar.indexOf('function GlosarioSection', start))
  for (const code of ["'FM'", "'PROB30'", "'PROB40'", "'TX / TN'", "'VRB'", "'NSW'", "'NSC'"]) {
    assert.ok(glossary.includes(`code: ${code}`), `glossary is missing ${code}`)
  }
})

test('the glossary and the TAF card use the same words for BECMG, TEMPO, FM and PROB', () => {
  const start = metar.indexOf('const GLOSARIO')
  const glossary = metar.slice(start, metar.indexOf('function GlosarioSection', start))
  for (const key of ['BECMG', 'TEMPO', 'FM', 'PROB30', 'PROB40']) {
    assert.ok(glossary.includes(`TAF_GROUP_NOTES.${key}`), `the glossary does not use TAF_GROUP_NOTES.${key}`)
  }
  assert.ok(!/Becoming — cambio gradual y permanente/.test(metar), 'an old BECMG text is still in the page')
  const card = read('../src/components/aeronautica/TafDecodedCard.tsx')
  assert.ok(card.includes('changeExplanation('), 'the card does not show the explanation of the change group')
})

test('/datos says the TAF of the METAR page comes from the Aviation Weather Center', () => {
  const source = DATA_SOURCES.find(s => s.id === 'metar')
  assert.ok(source, 'missing the metar source')
  assert.ok(/TAF/.test(source.summary) && /Aviation Weather Center/.test(source.summary))
  assert.ok(source.providers.includes('CheckWX'))
  assert.ok(source.providers.includes('Aviation Weather Center (NOAA)'))
  assert.ok(!/a través de CheckWX\. Niebla/.test(source.summary), 'summary still says everything goes through CheckWX')
})

test('the flight-category colours are shared, not duplicated in the page', () => {
  assert.ok(!/const CAT_STYLES/.test(metar), 'Metar.tsx still defines its own CAT_STYLES')
  assert.ok(metar.includes('FLIGHT_CATEGORY_STYLES'))
})

test('api.ts exposes tafDecoded on /api/taf', () => {
  const api = read('../src/lib/api.ts')
  assert.ok(/tafDecoded:\s*\(icao: string\)/.test(api))
  assert.ok(api.includes("'/api/taf'"))
})
