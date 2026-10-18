import { test } from 'node:test'
import assert from 'node:assert/strict'
import { respuestasRapidas } from '../src/lib/asistente/respuestasRapidas.ts'

// The "quick answers" shown when the model cannot answer: computed in the browser, with what the app already loaded and
// with the same rules the pages use (buildVerdict's lines, the best-day floor of the laundry tool). Nothing is requested.

const dia = (sobre: object) => ({ day_label: 'Sáb 10/10', label: 'Excelente', score: 92, is_best: true, ...sobre }) as never

test('with no data there are no quick answers', () => {
  assert.deepEqual(respuestasRapidas({ veredicto: null, diasRopa: null }), [])
  assert.deepEqual(respuestasRapidas({ veredicto: [], diasRopa: [] }), [])
})

test('the day answer is the first two lines of the verdict the forecast page shows', () => {
  const r = respuestasRapidas({
    veredicto: [{ text: 'Sin lluvia prevista en las próximas 24 h' }, { text: 'Mañana, lluvia desde las 15' }, { text: 'tercera' }],
    diasRopa: null,
  })
  assert.deepEqual(r, [
    { id: 'dia', pregunta: '¿Cómo viene el día?', texto: 'Sin lluvia prevista en las próximas 24 h. Mañana, lluvia desde las 15.' },
  ])
})

test('verdict lines are not doubled up with punctuation and blank lines are skipped', () => {
  const r = respuestasRapidas({ veredicto: [{ text: '  ' }, { text: 'Tormenta probable.' }], diasRopa: null })
  assert.equal(r[0].texto, 'Tormenta probable.')
})

test('the laundry answer names the best day, only when it qualifies (Excelente or Bueno)', () => {
  const buena = respuestasRapidas({ veredicto: null, diasRopa: [dia({})] })
  assert.deepEqual(buena, [
    { id: 'ropa', pregunta: '¿Cuándo conviene tender la ropa?', texto: 'El mejor día para tender la ropa es Sáb 10/10.' },
  ])
  assert.deepEqual(respuestasRapidas({ veredicto: null, diasRopa: [dia({ label: 'Regular', score: 50 })] }), [])
  assert.deepEqual(respuestasRapidas({ veredicto: null, diasRopa: [dia({ is_best: false })] }), [])
})

test('both answers come in a fixed order: day first, laundry second', () => {
  const r = respuestasRapidas({ veredicto: [{ text: 'Sin lluvia.' }], diasRopa: [dia({})] })
  assert.deepEqual(r.map((x) => x.id), ['dia', 'ropa'])
})

test('no quick answer names the model, a provider or an official warning', () => {
  const r = respuestasRapidas({ veredicto: [{ text: 'Sin lluvia.' }], diasRopa: [dia({})] })
  assert.doesNotMatch(JSON.stringify(r), /groq|openai|llama|inteligencia artificial|aviso oficial/i)
})
