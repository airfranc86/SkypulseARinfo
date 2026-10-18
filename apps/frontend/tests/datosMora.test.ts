import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { DATA_SOURCES, SOBRE_MORA } from '../src/data/dataSources.ts'
import { AVES_ARGENTINAS_URL, SIB_URL } from '../src/lib/siteLinks.ts'

// The credit of the species Mora is inspired by (owner decision D10), on the "De dónde salen los datos" page. It is only
// shown with the assistant flag on: the page cannot credit something the site does not show yet. Every statement was
// checked: "águila mora" is the common name of Geranoaetus melanoleucus (EcoRegistros, Birds of the World); it is NOT
// Geranoaetus polyosoma, which is the "aguilucho común". The two links exist (checked 2026-10-18).

const pagina = readFileSync(new URL('../src/pages/DatosFuentes.tsx', import.meta.url), 'utf8').replaceAll('\r\n', '\n')

test('the credit names the species by its common and scientific name, and the right one', () => {
  const texto = `${SOBRE_MORA.title} ${SOBRE_MORA.summary}`
  assert.match(texto, /águila mora/i)
  assert.match(texto, /Geranoaetus melanoleucus/)
  assert.doesNotMatch(texto, /polyosoma|aguilucho/i, 'that is another species')
  assert.doesNotMatch(texto, /c[óo]ndor/i)
})

test('it says Mora is inspired by the species and points to where to learn more, without claiming data we did not use', () => {
  assert.match(SOBRE_MORA.summary, /inspirad[ao]/)
  assert.match(SOBRE_MORA.summary, /Para saber más/)
  assert.doesNotMatch(SOBRE_MORA.summary, /datos de|según el|conservaci[óo]n (es|est[aá])|en peligro|amenazad/i)
  assert.deepEqual([...SOBRE_MORA.providers], ['Sistema de Información de Biodiversidad (SIB, Parques Nacionales)', 'Aves Argentinas'])
})

test('it has the shape of a source of the page and a stable anchor, and it is not in the list of data sources', () => {
  assert.equal(SOBRE_MORA.id, 'mora')
  assert.ok(SOBRE_MORA.title.trim().length > 0 && SOBRE_MORA.summary.trim().length > 20)
  assert.equal(DATA_SOURCES.some((s) => s.id === SOBRE_MORA.id), false, 'it only shows with the flag')
})

test('no commercial wording and no provider or model names', () => {
  const texto = `${SOBRE_MORA.title} ${SOBRE_MORA.summary} ${SOBRE_MORA.providers.join(' ')}`
  assert.doesNotMatch(texto, /perk|premium|precio|suscripci|plan pago|\$\s?\d/i)
  assert.doesNotMatch(texto, /groq|openai|llama|gpt/i)
})

test('the two links are the real sites, over https', () => {
  assert.equal(new URL(SIB_URL).protocol, 'https:')
  assert.equal(new URL(SIB_URL).hostname, 'sib.gob.ar')
  assert.equal(new URL(AVES_ARGENTINAS_URL).protocol, 'https:')
  assert.equal(new URL(AVES_ARGENTINAS_URL).hostname, 'www.avesargentinas.org.ar')
})

test('the page shows the section only with the assistant flag on, with both links opening safely', () => {
  assert.match(pagina, /leerConfigAsistente\(import\.meta\.env\)\.visible/)
  assert.match(pagina, /ASISTENTE_VISIBLE && \(/)
  assert.match(pagina, /id=\{SOBRE_MORA\.id\}/)
  assert.match(pagina, /href=\{SIB_URL\} target="_blank" rel="noopener noreferrer"/)
  assert.match(pagina, /href=\{AVES_ARGENTINAS_URL\} target="_blank" rel="noopener noreferrer"/)
})

test('the credit sits before the licences section', () => {
  assert.ok(pagina.indexOf('id={SOBRE_MORA.id}') < pagina.indexOf('<section id="creditos"'))
})
