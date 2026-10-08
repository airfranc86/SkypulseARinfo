import { test } from 'node:test'
import assert from 'node:assert/strict'
import { phenomenonIcon, phenomenonIconsForToken } from '../src/lib/phenomenonIcons.ts'
import { isWeatherIconCode } from '../src/lib/weatherIconCodes.ts'

test('each reported phenomenon code maps to its neutral icon', () => {
  assert.equal(phenomenonIcon('BR'), 'mist')
  assert.equal(phenomenonIcon('FG'), 'fog')
  assert.equal(phenomenonIcon('HZ'), 'haze')
  assert.equal(phenomenonIcon('FU'), 'smoke')
  assert.equal(phenomenonIcon('DU'), 'dust')
})

test('every icon the map returns is a valid WeatherIcon code', () => {
  for (const code of ['BR', 'FG', 'HZ', 'FU', 'DU']) {
    const icon = phenomenonIcon(code)
    assert.ok(icon !== null && isWeatherIconCode(icon), `${code} -> ${icon}`)
  }
})

test('any other code has no icon (nothing is invented)', () => {
  for (const code of ['RA', 'TS', 'SN', 'VA', 'SA', 'SS', 'DS', 'PO', 'SQ', 'FC', '', 'XX', 'br']) {
    assert.equal(phenomenonIcon(code), null, code)
  }
})

test('a full token resolves through its intensity, vicinity and descriptor parts', () => {
  assert.deepEqual(phenomenonIconsForToken('BR'), ['mist'])
  assert.deepEqual(phenomenonIconsForToken('-BR'), ['mist'])
  assert.deepEqual(phenomenonIconsForToken('+DU'), ['dust'])
  assert.deepEqual(phenomenonIconsForToken('BCFG'), ['fog'])
  assert.deepEqual(phenomenonIconsForToken('VCFG'), ['fog'])
  assert.deepEqual(phenomenonIconsForToken('MIFG'), ['fog'])
  assert.deepEqual(phenomenonIconsForToken('FZFG'), ['fog'])
  assert.deepEqual(phenomenonIconsForToken('HZ'), ['haze'])
  assert.deepEqual(phenomenonIconsForToken('FU'), ['smoke'])
  assert.deepEqual(phenomenonIconsForToken('DU'), ['dust'])
  assert.deepEqual(phenomenonIconsForToken('BLDU'), ['dust'])
})

test('a token with several phenomena returns only the icons that exist, in order, without repeats', () => {
  assert.deepEqual(phenomenonIconsForToken('RA BR'), ['mist'])
  assert.deepEqual(phenomenonIconsForToken('BRHZ'), ['mist', 'haze'])
  assert.deepEqual(phenomenonIconsForToken('BR BR'), ['mist'])
  assert.deepEqual(phenomenonIconsForToken('HZ FU DU'), ['haze', 'smoke', 'dust'])
})

test('tokens without a mapped phenomenon, or malformed ones, give no icons', () => {
  assert.deepEqual(phenomenonIconsForToken('RA'), [])
  assert.deepEqual(phenomenonIconsForToken('TSRA'), [])
  assert.deepEqual(phenomenonIconsForToken('NSW'), [])
  assert.deepEqual(phenomenonIconsForToken('BRX'), [])
  assert.deepEqual(phenomenonIconsForToken(''), [])
  assert.deepEqual(phenomenonIconsForToken('   '), [])
})

test('the token is read case-insensitively', () => {
  assert.deepEqual(phenomenonIconsForToken('-br'), ['mist'])
})
