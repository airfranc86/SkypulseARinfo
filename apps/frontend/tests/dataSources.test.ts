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

test('the official alerts credit the SMN with the licence its own feed declares, linked to the legal text', () => {
  const page = read('../src/pages/DatosFuentes.tsx')
  assert.match(page, /Avisos oficiales/)
  assert.match(page, /Servicio Meteorológico Nacional/)
  assert.match(page, /CC BY 4\.0/)
  assert.match(page, /href=\{SMN_URL\}/)
  assert.match(page, /href=\{CC_BY_4_URL\}/)
  assert.match(page, /según la propia fuente/)
  assert.doesNotMatch(page, /CC BY 2\.5/)
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

test('the pressure map credits NOAA GFS, CARTO and OpenStreetMap and says it is not an official warning', () => {
  const source = byId('mapa-presion')
  assert.equal(source.title, 'Mapa de presión')
  for (const provider of ['GFS (NOAA, EE. UU.)', 'CARTO', 'OpenStreetMap']) {
    assert.ok(source.providers.includes(provider), `credits ${provider}`)
  }
  assert.match(source.summary, /no es un aviso oficial/)
  assert.match(source.summary, /smn\.gob\.ar|SMN/)
  // NOAA's terms (Open Data on AWS) forbid implying endorsement OR affiliation, and the data are modified here.
  assert.match(source.summary, /modificados por SkyPulse: SkyPulse no está afiliado a NOAA ni cuenta con su aval/)
  assert.match(source.summary, /© OpenStreetMap contributors, © CARTO/)
})

test('the pressure map says what it shows: 0.25 degrees, up to 5 days in 3-hour steps, 4 times a day', () => {
  const { summary } = byId('mapa-presion')
  assert.match(summary, /a 0,25° de resolución/)
  assert.match(summary, /(^|\D)5 días \(120 horas\) desde la corrida del modelo/)
  assert.match(summary, /en pasos de 3 horas/)
  assert.match(summary, /Se recalculan 4 veces al día, unas 5 horas después de cada corrida del modelo \(00, 06, 12 y 18 UTC\)/)
  assert.match(summary, /centros sobre terreno de más de 1500 m no se marcan/)
})

// The numbers in the text must be the ones the pipeline really uses: read them from its code.
const pipeline = (archivo: string) =>
  read(`../../../scripts/isobaras/isobaras_core/${archivo}`).replaceAll('\r\n', '\n')

test('the pressure map figures match the pipeline code and the workflow', () => {
  assert.match(pipeline('centros.py'), /^ALTURA_MAXIMA_M = 1500\.0$/m)
  assert.match(pipeline('ciclo.py'), /tuple\(range\(0, 121, 3\)\)/)
  assert.match(pipeline('ciclo.py'), /pgrb2\.0p25/)
  const workflow = read('../../../.github/workflows/isobaras.yml')
  assert.match(workflow, /cron: "45 4,10,16,22 \* \* \*"/)
})
