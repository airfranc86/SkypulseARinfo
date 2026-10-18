import { test } from 'node:test'
import assert from 'node:assert/strict'
import { destinoDelTab } from '../src/lib/asistente/foco.ts'

// On a phone the panel is a sheet that covers most of the screen and behaves as a modal dialog: Tab must not walk out of it
// to what is hidden under it. This is the rule of where the focus goes (pure); the panel only reads the DOM and applies it.

test('Tab on the last element wraps to the first, Shift+Tab on the first wraps to the last', () => {
  assert.equal(destinoDelTab(2, 3, false), 0)
  assert.equal(destinoDelTab(0, 3, true), 2)
})

test('in the middle the browser moves the focus by itself', () => {
  assert.equal(destinoDelTab(1, 3, false), null)
  assert.equal(destinoDelTab(1, 3, true), null)
  assert.equal(destinoDelTab(0, 3, false), null)
  assert.equal(destinoDelTab(2, 3, true), null)
})

test('a focus that is outside the panel is brought in, at the end it would reach first', () => {
  assert.equal(destinoDelTab(-1, 3, false), 0)
  assert.equal(destinoDelTab(-1, 3, true), 2)
})

test('with a single element it stays on it', () => {
  assert.equal(destinoDelTab(0, 1, false), 0)
  assert.equal(destinoDelTab(0, 1, true), 0)
})

test('with nothing to focus there is no destination', () => {
  assert.equal(destinoDelTab(-1, 0, false), null)
  assert.equal(destinoDelTab(0, 0, true), null)
})
