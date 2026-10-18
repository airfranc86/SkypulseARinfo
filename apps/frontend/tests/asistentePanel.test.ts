import { test } from 'node:test'
import assert from 'node:assert/strict'
import { humorDelPanel, reducirPanel, type EstadoPanel } from '../src/lib/asistente/panel.ts'
import type { ResultadoPregunta } from '../src/lib/asistente/cliente.ts'
import { HUMORES } from '../src/lib/asistente/humor.ts'

// The state of the question panel as a reducer, plus the mood Mora shows for it. Pure: the panel (PR 4b) only draws it.

const REPOSO: EstadoPanel = { fase: 'reposo' }
const ENVIANDO: EstadoPanel = { fase: 'enviando', pregunta: '¿Va a llover?' }

const enviar = (estado: EstadoPanel, pregunta = '¿Va a llover?') => reducirPanel(estado, { tipo: 'enviar', pregunta })
const resultado = (estado: EstadoPanel, r: ResultadoPregunta) => reducirPanel(estado, { tipo: 'resultado', resultado: r })

test('sending from rest starts sending, with the question', () => {
  assert.deepEqual(enviar(REPOSO), ENVIANDO)
})

test('there is only one question in flight: sending while sending changes nothing', () => {
  assert.equal(enviar(ENVIANDO, 'otra'), ENVIANDO)
})

test('a new question can be sent after an answer or an error', () => {
  const respondida = resultado(ENVIANDO, { tipo: 'respuesta', estado: 'ok', texto: 'Hola' })
  assert.deepEqual(enviar(respondida, 'otra'), { fase: 'enviando', pregunta: 'otra' })
  const error = resultado(ENVIANDO, { tipo: 'sin-conexion' })
  assert.deepEqual(enviar(error, 'otra'), { fase: 'enviando', pregunta: 'otra' })
})

test('an answer keeps the question, the state and the text', () => {
  assert.deepEqual(resultado(ENVIANDO, { tipo: 'respuesta', estado: 'sin_dato', texto: 'No tengo ese dato.' }), {
    fase: 'respondida',
    pregunta: '¿Va a llover?',
    estado: 'sin_dato',
    texto: 'No tengo ese dato.',
  })
})

test('every kind of failure becomes an error that keeps the question and the kind', () => {
  const fallas: ResultadoPregunta[] = [
    { tipo: 'cupo-diario', segundos: 3600 },
    { tipo: 'espera', motivo: 'ritmo', segundos: 30 },
    { tipo: 'espera', motivo: 'en-curso', segundos: 5 },
    { tipo: 'no-disponible', segundos: null },
    { tipo: 'apagado' },
    { tipo: 'invalida' },
    { tipo: 'sin-conexion' },
  ]
  for (const falla of fallas) {
    assert.deepEqual(resultado(ENVIANDO, falla), { fase: 'error', pregunta: '¿Va a llover?', error: falla })
  }
})

test('a cancelled question goes back to rest', () => {
  assert.deepEqual(resultado(ENVIANDO, { tipo: 'cancelada' }), REPOSO)
})

test('a result that arrives when nothing is in flight is stale and is ignored', () => {
  const respuesta: ResultadoPregunta = { tipo: 'respuesta', estado: 'ok', texto: 'Tarde' }
  assert.equal(resultado(REPOSO, respuesta), REPOSO)
  const respondida = resultado(ENVIANDO, { tipo: 'respuesta', estado: 'ok', texto: 'Hola' })
  assert.equal(resultado(respondida, respuesta), respondida)
})

test('clearing goes back to rest from anywhere, even while sending (the panel was closed)', () => {
  const respondida = resultado(ENVIANDO, { tipo: 'respuesta', estado: 'ok', texto: 'Hola' })
  for (const estado of [REPOSO, ENVIANDO, respondida, resultado(ENVIANDO, { tipo: 'apagado' })]) {
    assert.deepEqual(reducirPanel(estado, { tipo: 'limpiar' }), REPOSO)
  }
})

test('the reducer never mutates its input', () => {
  const antes = JSON.stringify(ENVIANDO)
  resultado(ENVIANDO, { tipo: 'respuesta', estado: 'ok', texto: 'Hola' })
  reducirPanel(ENVIANDO, { tipo: 'limpiar' })
  assert.equal(JSON.stringify(ENVIANDO), antes)
})

// ── humorDelPanel ────────────────────────────────────────────────────────────

test('Mora thinks while the question is in flight', () => {
  assert.equal(humorDelPanel(ENVIANDO), 'pensando')
})

test('Mora answers when there is an answer, and is confused when the answer says there is no data', () => {
  assert.equal(humorDelPanel(resultado(ENVIANDO, { tipo: 'respuesta', estado: 'ok', texto: 'Hola' })), 'respondiendo')
  assert.equal(humorDelPanel(resultado(ENVIANDO, { tipo: 'respuesta', estado: 'sin_dato', texto: 'No' })), 'confundido')
  assert.equal(humorDelPanel(resultado(ENVIANDO, { tipo: 'respuesta', estado: 'fuera_de_alcance', texto: 'No' })), null)
})

test('Mora is confused when the model could not answer, but not when the user only has to wait', () => {
  for (const r of [{ tipo: 'no-disponible', segundos: 60 }, { tipo: 'apagado' }, { tipo: 'sin-conexion' }] as ResultadoPregunta[]) {
    assert.equal(humorDelPanel(resultado(ENVIANDO, r)), 'confundido', r.tipo)
  }
  for (const r of [{ tipo: 'cupo-diario', segundos: 60 }, { tipo: 'espera', motivo: 'ritmo', segundos: 5 }, { tipo: 'invalida' }] as ResultadoPregunta[]) {
    assert.equal(humorDelPanel(resultado(ENVIANDO, r)), null, r.tipo)
  }
})

test('at rest the panel does not set a mood (the bubble keeps the one the weather gives)', () => {
  assert.equal(humorDelPanel(REPOSO), null)
})

test('every mood the panel can set exists in the list of moods', () => {
  for (const humor of ['pensando', 'respondiendo', 'confundido']) assert.ok((HUMORES as readonly string[]).includes(humor), humor)
})
