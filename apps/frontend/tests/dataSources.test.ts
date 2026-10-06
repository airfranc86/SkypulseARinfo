import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { DATA_SOURCES } from '../src/data/dataSources.ts'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

const byId = (id: string) => {
  const source = DATA_SOURCES.find(s => s.id === id)
  assert.ok(source, `missing source "${id}"`)
  return source
}

test('every source has a non-empty title and summary', () => {
  assert.ok(DATA_SOURCES.length > 0)
  for (const source of DATA_SOURCES) {
    assert.ok(source.title.trim().length > 0, `${source.id}: title`)
    assert.ok(source.summary.trim().length > 0, `${source.id}: summary`)
    assert.ok(Array.isArray(source.providers), `${source.id}: providers`)
  }
})

test('source ids are unique', () => {
  const ids = DATA_SOURCES.map(s => s.id)
  assert.equal(new Set(ids).size, ids.length)
})

test('Open-Meteo is credited as a provider of the forecast', () => {
  assert.ok(byId('pronostico').providers.includes('Open-Meteo'))
})

test('the page names the institutions behind each live tool', () => {
  assert.ok(byId('terremotos').providers.some(p => p.includes('EMSC')))
  assert.ok(byId('terremotos').providers.some(p => p.includes('USGS')))
  assert.ok(byId('volcanes').providers.some(p => p.includes('SEGEMAR')))
  assert.ok(byId('avisos').providers.some(p => p.includes('SMN')))
})

test('no source uses commercial wording', () => {
  const text = DATA_SOURCES.map(s => `${s.title} ${s.summary} ${s.providers.join(' ')}`).join(' ')
  assert.doesNotMatch(text, /perk|premium|precio|suscripci|plan pago|\$\s?\d/i)
})

test('the consensus sentence matches the one in the "Avanzado" panel of Previsión', () => {
  const sentence =
    'El consenso toma la temperatura del promedio de GFS y ECMWF; la lluvia, el viento y el ícono siguen a ECMWF.'
  assert.ok(byId('consenso').summary.includes(sentence))
  assert.ok(read('../src/components/clima/Forecast7d.tsx').includes(sentence))
})
