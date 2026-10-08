import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cloudBaseFeet, cloudBaseMeters, cloudBaseText, cloudType } from '../src/lib/cloudBase.ts'

// B4: the cloud base height of a CheckWX METAR layer. The documented (and real) layer is
// { code, feet, meters, text }; `base_feet_agl` was an invented field and stays only as a fallback.

test('cloud base: the real CheckWX layer (SACO 2026-10-08) reads "3500 ft (1067 m)"', () => {
  const layer = { code: 'SCT', feet: 3500, meters: 1067.0, text: 'Scattered' }
  assert.equal(cloudBaseFeet(layer), 3500)
  assert.equal(cloudBaseMeters(layer), 1067)
  assert.equal(cloudBaseText(layer), '3500 ft (1067 m)')
})

test('cloud base: without meters they are computed from the feet (x 0.3048) and rounded', () => {
  assert.equal(cloudBaseText({ code: 'BKN', feet: 4800 }), '4800 ft (1463 m)')
  assert.equal(cloudBaseMeters({ feet: 4800 }), 1463)
  assert.equal(cloudBaseMeters({ feet: 2000 }), 610) // 609.6
})

test('cloud base: the meters the API sends win over the computed ones', () => {
  assert.equal(cloudBaseText({ feet: 3500, meters: 1070 }), '3500 ft (1070 m)')
})

test('cloud base: base_feet_agl is only a fallback, and `feet` wins when both are there', () => {
  assert.equal(cloudBaseText({ code: 'BKN', base_feet_agl: 2000 }), '2000 ft (610 m)')
  assert.equal(cloudBaseFeet({ feet: 3500, base_feet_agl: 2000 }), 3500)
})

test('cloud base: no usable height gives null, never "undefined ft" or "NaN"', () => {
  assert.equal(cloudBaseText({ code: 'BKN' }), null)
  assert.equal(cloudBaseText({}), null)
  assert.equal(cloudBaseText({ feet: Number.NaN }), null)
  assert.equal(cloudBaseText({ feet: '3500' as unknown as number }), null)
  assert.equal(cloudBaseText({ feet: -100 }), null)
  assert.equal(cloudBaseFeet({ code: 'OVC' }), null)
  assert.equal(cloudBaseMeters({ code: 'OVC' }), null)
})

test('cloud type: a string or the documented { code, text } object, normalised to the upper-case code', () => {
  assert.equal(cloudType({ type: 'CB' }), 'CB')
  assert.equal(cloudType({ type: ' tcu ' }), 'TCU')
  assert.equal(cloudType({ type: { code: 'CB', text: 'Cumulonimbus' } }), 'CB')
  assert.equal(cloudType({ type: { code: 'tcu', text: 'Towering Cumulus' } }), 'TCU')
})

test('cloud type: missing, null or empty gives undefined', () => {
  assert.equal(cloudType({ code: 'FEW' }), undefined)
  assert.equal(cloudType({ type: null }), undefined)
  assert.equal(cloudType({ type: {} }), undefined)
  assert.equal(cloudType({ type: '' }), undefined)
})
