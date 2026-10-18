import { test } from 'node:test'
import assert from 'node:assert/strict'
import { prepararPregunta } from '../src/lib/asistente/preparar.ts'

// What the panel does when the person presses "Preguntar": the text, the place and the page checked and shaped in one
// pure step, before anything leaves the browser. The first thing that is wrong is what the panel tells the person.

test('a good question, a place in Argentina and a page become the question the client sends', () => {
  assert.deepEqual(prepararPregunta('  ¿Va a llover?  ', -31.4167, -64.1833, '/prevision'), {
    ok: true,
    pregunta: { pregunta: '¿Va a llover?', pagina: '/prevision', lat: -31.42, lon: -64.18 },
  })
})

test('an empty or too long question is rejected with the reason', () => {
  assert.deepEqual(prepararPregunta('   ', -31.42, -64.19, '/'), { ok: false, motivo: 'vacia' })
  assert.deepEqual(prepararPregunta('a'.repeat(301), -31.42, -64.19, '/'), { ok: false, motivo: 'larga' })
})

test('without a place, or with one outside Argentina, there is no question to send', () => {
  assert.deepEqual(prepararPregunta('¿Va a llover?', null, null, '/'), { ok: false, motivo: 'sin-ubicacion' })
  assert.deepEqual(prepararPregunta('¿Va a llover?', undefined, -64, '/'), { ok: false, motivo: 'sin-ubicacion' })
  assert.deepEqual(prepararPregunta('¿Va a llover?', 40.4, -3.7, '/'), { ok: false, motivo: 'sin-ubicacion' })
})

test('the text is checked before the place: an empty question says so even with no place', () => {
  assert.deepEqual(prepararPregunta('', null, null, null), { ok: false, motivo: 'vacia' })
})

test('a page that is not a plain path is simply not sent, the question still goes', () => {
  const r = prepararPregunta('¿Va a llover?', -31.42, -64.19, '//evil.com')
  assert.equal(r.ok, true)
  assert.equal(r.ok && r.pregunta.pagina, null)
})

test('the query of the page never travels', () => {
  const r = prepararPregunta('¿Va a llover?', -31.42, -64.19, '/mapa?lat=-31.42&lon=-64.19')
  assert.equal(r.ok && r.pregunta.pagina, '/mapa')
})
