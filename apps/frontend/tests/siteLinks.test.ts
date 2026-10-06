import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  CAFECITO_URL,
  DATA_PAGE_PATH,
  OPEN_METEO_LICENCE_URL,
  OPEN_METEO_URL,
} from '../src/lib/siteLinks.ts'

test('the Open-Meteo credit and licence point to the exact https pages', () => {
  assert.equal(OPEN_METEO_URL, 'https://open-meteo.com/')
  assert.equal(OPEN_METEO_LICENCE_URL, 'https://open-meteo.com/en/licence')
})

test('the voluntary contribution link is the Cafecito page of SkyPulse', () => {
  assert.equal(CAFECITO_URL, 'https://cafecito.app/skypulse-ar')
})

test('the data page lives at /datos', () => {
  assert.equal(DATA_PAGE_PATH, '/datos')
})

test('every external link is https', () => {
  for (const url of [OPEN_METEO_URL, OPEN_METEO_LICENCE_URL, CAFECITO_URL]) {
    assert.ok(url.startsWith('https://'), url)
  }
})
