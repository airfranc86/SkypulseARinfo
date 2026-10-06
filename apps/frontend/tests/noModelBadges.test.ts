import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8')

// FRA-347: the main view never names a weather model or provider; the explanation lives on /datos.
const TOOL_PAGES = ['CotaDeNieve', 'HacerDeporte', 'Incendios', 'LavarCoche', 'TenderRopa']

for (const page of TOOL_PAGES) {
  test(`${page} shows no model badge`, () => {
    const source = read(`../src/pages/${page}.tsx`)
    assert.ok(!source.includes('openmeteo_forecast'), 'still uses the openmeteo_forecast badge')
    assert.ok(!source.includes('ModelBadge'), 'still imports or renders ModelBadge')
  })
}

test('institution badges stay on Terremotos and Volcanes', () => {
  assert.ok(read('../src/pages/Terremotos.tsx').includes('ModelBadge'))
  assert.ok(read('../src/pages/Volcanes.tsx').includes('model="segemar"'))
})

test('Niebla no longer shows the provider name', () => {
  const source = read('../src/pages/Niebla.tsx')
  for (const removed of [
    ": 'Open-Meteo'",
    "'Estimación numérica Open-Meteo'",
    "'Inferencia OM'",
    "openmeteo:            'Open-Meteo'",
    '(Open-Meteo)',
    "'Pronóstico numérico Open-Meteo'",
  ]) {
    assert.ok(!source.includes(removed), `still has: ${removed}`)
  }
})

test('the footer credits Open-Meteo, links to /datos and to Cafecito', () => {
  const app = read('../src/App.tsx')
  assert.ok(app.includes('OPEN_METEO_URL'))
  assert.ok(app.includes('<CafecitoButton />'))
  assert.ok(app.includes('DATA_PAGE_PATH'))
  assert.ok(app.includes('Datos del tiempo:'))
  assert.ok(app.includes('De dónde salen los datos'))
  assert.ok(app.includes('Política de privacidad'))
})

test('the dynamic ModelStatusBar is gone from the footer and from disk', () => {
  assert.ok(!read('../src/App.tsx').includes('ModelStatusBar'))
  assert.ok(!existsSync(new URL('../src/components/ui/ModelStatusBar.tsx', import.meta.url)))
})

test('/datos is a lazy route of the app', () => {
  const app = read('../src/App.tsx')
  assert.match(app, /lazy\(\(\) => import\('@\/pages\/DatosFuentes'\)/)
  assert.ok(app.includes('path={DATA_PAGE_PATH}'))
})

test('the "Avanzado" panel keeps its model selector and links to the data page', () => {
  const forecast = read('../src/components/clima/Forecast7d.tsx')
  assert.ok(forecast.includes('Segmented'))
  assert.ok(forecast.includes('Más sobre de dónde salen los datos'))
  assert.ok(forecast.includes('DATA_PAGE_PATH'))
})
