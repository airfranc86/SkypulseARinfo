import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  CAFECITO_BUTTON_ALT,
  CAFECITO_BUTTON_SRC,
  CAFECITO_BUTTON_SRCSET,
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

test('the Cafecito button is the official one: 1x, 2x and 3.75x images, exact alt text', () => {
  assert.equal(CAFECITO_BUTTON_SRC, 'https://cdn.cafecito.app/imgs/buttons/button_5.png')
  assert.equal(
    CAFECITO_BUTTON_SRCSET,
    'https://cdn.cafecito.app/imgs/buttons/button_5.png 1x, '
      + 'https://cdn.cafecito.app/imgs/buttons/button_5_2x.png 2x, '
      + 'https://cdn.cafecito.app/imgs/buttons/button_5_3.75x.png 3.75x',
  )
  assert.equal(CAFECITO_BUTTON_ALT, 'Invitame un café en cafecito.app')
})
