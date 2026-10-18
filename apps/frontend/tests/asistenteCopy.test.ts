import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  AVISO_PRIMER_USO,
  esperaLegible,
  TITULO_RESPUESTAS_RAPIDAS,
  textoDeError,
  textoDeValidacion,
} from '../src/lib/asistente/copy.ts'
import type { ErrorPanel } from '../src/lib/asistente/cliente.ts'

// The texts the panel shows (rioplatense voseo). They never name the model or the provider, never alarm, never use
// Markdown (React escapes the text, but the rules of the answers apply here too), and always give a way forward.

const ERRORES: ErrorPanel[] = [
  { tipo: 'cupo-diario', segundos: 7200 },
  { tipo: 'espera', motivo: 'ritmo', segundos: 30 },
  { tipo: 'espera', motivo: 'en-curso', segundos: 5 },
  { tipo: 'no-disponible', segundos: 90 },
  { tipo: 'no-disponible', segundos: null },
  { tipo: 'apagado' },
  { tipo: 'invalida' },
  { tipo: 'sin-conexion' },
]

test('every error has a text, in Spanish, without markup', () => {
  for (const error of ERRORES) {
    const texto = textoDeError(error)
    assert.ok(texto.trim().length > 15, JSON.stringify(error))
    for (const marca of ['**', '](', '<', '>', '`', '{', 'undefined', 'NaN']) assert.ok(!texto.includes(marca), `${error.tipo}: ${marca}`)
  }
})

test('no text names the model, the provider or an error code', () => {
  const todo = [
    ...ERRORES.map(textoDeError),
    textoDeValidacion('vacia'),
    textoDeValidacion('larga'),
    textoDeValidacion('sin-ubicacion'),
    AVISO_PRIMER_USO.titulo,
    AVISO_PRIMER_USO.boton,
    TITULO_RESPUESTAS_RAPIDAS,
  ].join(' ')
  assert.doesNotMatch(todo, /groq|openai|llama|gpt|\b(404|422|429|503)\b|asistente_no_disponible|cupo_diario/i)
})

test('the daily limit says it comes back tomorrow', () => {
  assert.match(textoDeError({ tipo: 'cupo-diario', segundos: 7200 }), /ma[ñn]ana/i)
})

test('waiting errors say how long, in readable units', () => {
  assert.match(textoDeError({ tipo: 'espera', motivo: 'ritmo', segundos: 30 }), /30 s/)
  assert.match(textoDeError({ tipo: 'no-disponible', segundos: 300 }), /5 min/)
})

test('"in flight" says the previous question is still running', () => {
  assert.match(textoDeError({ tipo: 'espera', motivo: 'en-curso', segundos: 5 }), /anterior/)
})

test('"not available" and "off" send the person to the forecast page and do not promise a time without a wait', () => {
  for (const error of [{ tipo: 'no-disponible', segundos: null }, { tipo: 'apagado' }] as ErrorPanel[]) {
    assert.match(textoDeError(error), /Previsi[oó]n/)
  }
  assert.doesNotMatch(textoDeError({ tipo: 'no-disponible', segundos: null }), /\d+ ?(s|min|h)\b/)
})

test('no connection asks to check the connection', () => {
  assert.match(textoDeError({ tipo: 'sin-conexion' }), /conexi[oó]n/)
})

test('esperaLegible: seconds, minutes and hours, always rounded up', () => {
  assert.equal(esperaLegible(1), '1 s')
  assert.equal(esperaLegible(59), '59 s')
  assert.equal(esperaLegible(60), '1 min')
  assert.equal(esperaLegible(61), '2 min')
  assert.equal(esperaLegible(3599), '60 min')
  assert.equal(esperaLegible(3600), '1 h')
  assert.equal(esperaLegible(3601), '2 h')
  assert.equal(esperaLegible(86400), '24 h')
})

test('esperaLegible: a missing or odd number never prints garbage', () => {
  for (const valor of [0, -5, Number.NaN, Number.POSITIVE_INFINITY]) assert.equal(esperaLegible(valor), '1 s', String(valor))
})

test('the validation texts say what to do', () => {
  assert.match(textoDeValidacion('vacia'), /Escrib[ií]/)
  assert.match(textoDeValidacion('larga'), /300/)
  assert.match(textoDeValidacion('sin-ubicacion'), /lugar/)
})

test('the first-use notice is the one the owner approved (D6) and has a button', () => {
  assert.equal(
    AVISO_PRIMER_USO.texto,
    'Lo que escribís se envía a un proveedor de IA en EE. UU. para redactar la respuesta. No incluyas datos personales. No guardamos lo que escribís.',
  )
  assert.equal(AVISO_PRIMER_USO.boton, 'Entendido')
  assert.ok(AVISO_PRIMER_USO.titulo.length > 0)
})
