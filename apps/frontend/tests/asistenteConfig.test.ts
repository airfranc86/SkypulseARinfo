import { test } from 'node:test'
import assert from 'node:assert/strict'
import { VARIABLE_ASISTENTE_VISIBLE, leerConfigAsistente } from '../src/lib/asistente/config.ts'

// Mora, Phase 1 (PR 1): the assistant mascot is hidden unless the build env says otherwise. The read is pure
// (the env comes in as a parameter), so it is tested here without `import.meta.env`.

test('the flag lives in VITE_ASISTENTE_VISIBLE', () => {
  assert.equal(VARIABLE_ASISTENTE_VISIBLE, 'VITE_ASISTENTE_VISIBLE')
})

test('the assistant is visible only when the flag is exactly the string "true"', () => {
  assert.equal(leerConfigAsistente({ VITE_ASISTENTE_VISIBLE: 'true' }).visible, true)
})

test('any other value keeps the assistant hidden (strict flag)', () => {
  const laxos = ['TRUE', 'True', 'tRuE', '1', 'yes', 'on', 'false', '', ' true', 'true ', 'true\n', '\ttrue', ' ', true, 1, 0, null, undefined, {}, [], ['true']]
  for (const valor of laxos) {
    assert.equal(leerConfigAsistente({ [VARIABLE_ASISTENTE_VISIBLE]: valor }).visible, false, `value ${JSON.stringify(valor) ?? String(valor)}`)
  }
})

test('without the flag in the env the assistant is hidden (off by default)', () => {
  assert.equal(leerConfigAsistente({}).visible, false)
  assert.equal(leerConfigAsistente({ VITE_OTRA_COSA: 'true' }).visible, false)
})

test('the bell flag does not turn the assistant on', () => {
  assert.equal(leerConfigAsistente({ VITE_ALERTAS_VISIBLE: 'true' }).visible, false)
})

test('the assistant flag is read even when other variables are present', () => {
  assert.equal(leerConfigAsistente({ VITE_ALERTAS_VISIBLE: 'false', VITE_ASISTENTE_VISIBLE: 'true', MODE: 'production' }).visible, true)
})

test('an undefined or odd env does not throw and leaves everything off', () => {
  const apagado = { visible: false }
  assert.deepEqual(leerConfigAsistente(undefined), apagado)
  assert.deepEqual(leerConfigAsistente(null as unknown as undefined), apagado)
  assert.deepEqual(leerConfigAsistente('true' as unknown as undefined), apagado)
  assert.deepEqual(leerConfigAsistente(42 as unknown as undefined), apagado)
  assert.deepEqual(leerConfigAsistente({}), apagado)
})

test('the config has exactly one field, visible', () => {
  assert.deepEqual(leerConfigAsistente({ VITE_ASISTENTE_VISIBLE: 'true' }), { visible: true })
})

test('the result is frozen and the env is left untouched', () => {
  const env = { VITE_ASISTENTE_VISIBLE: 'true' }
  const config = leerConfigAsistente(env)
  assert.ok(Object.isFrozen(config))
  assert.deepEqual(env, { VITE_ASISTENTE_VISIBLE: 'true' })
})
