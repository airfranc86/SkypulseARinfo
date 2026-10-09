import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

/** Source text with CRLF normalized, so the checks do not depend on the checkout's line endings. */
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

const NOTICE = read('../src/components/clima/ForecastAgeNotice.tsx')
const PREVISION = read('../src/pages/PrevisionClima.tsx')
const NOW_CARD = read('../src/components/landing/NowCard.tsx')
const API = read('../src/lib/api.ts')

// ── El aviso (componente compartido) ─────────────────────────────────────────

test('el aviso se anuncia como estado y lleva el texto de staleForecastNotice', () => {
  assert.match(NOTICE, /role="status"/)
  assert.match(NOTICE, /staleForecastNotice\(forecastFetchedAt, nowMs\)/)
  assert.match(NOTICE, /\{text\}/)
})

test('el aviso no se pinta sin texto y se actualiza cada minuto con la página abierta', () => {
  assert.match(NOTICE, /if \(!text\) return null/)
  assert.match(NOTICE, /setInterval\(\(\) => setNowMs\(Date\.now\(\)\), CLOCK_TICK_MS\)/)
  assert.match(NOTICE, /clearInterval/)
})

test('el aviso usa el estilo ámbar de los avisos del sitio, con texto de al menos 12 px', () => {
  assert.match(NOTICE, /rgba\(240,160,48,0\.3\)/)
  assert.match(NOTICE, /rgba\(240,160,48,0\.06\)/)
  assert.doesNotMatch(NOTICE, /text-\[(?:[0-9]|1[01])(?:\.\d+)?px\]|text-\[0\.[0-6]\d*rem\]|text-\[0\.7[0-4]\d*rem\]/)
  assert.match(NOTICE, /text-sm|text-xs/)
})

test('el aviso envuelve el texto largo sin desbordar a 390 px', () => {
  assert.match(NOTICE, /min-w-0/)
  assert.doesNotMatch(NOTICE, /whitespace-nowrap/)
})

test('el icono del aviso es decorativo', () => {
  assert.match(NOTICE, /aria-hidden="true"/)
})

// ── Dónde se usa ─────────────────────────────────────────────────────────────

test('/prevision muestra el aviso con la edad calculada desde forecast_fetched_at', () => {
  assert.match(PREVISION, /import \{ ForecastAgeNotice \} from '@\/components\/clima\/ForecastAgeNotice'/)
  assert.match(PREVISION, /<ForecastAgeNotice forecastFetchedAt=\{data\.forecast_fetched_at\} \/>/)
})

test('/prevision muestra la hora del pronóstico (forecast_fetched_at ?? fetched_at) en "Actualizado"', () => {
  assert.match(PREVISION, /formatClock\(forecastUpdatedIso\(data\)\)/)
  assert.doesNotMatch(PREVISION, /formatClock\(data\?\.fetched_at\)/)
})

test('la tarjeta de la portada muestra el aviso y toma la hora del pronóstico', () => {
  assert.match(NOW_CARD, /import \{ ForecastAgeNotice \} from '@\/components\/clima\/ForecastAgeNotice'/)
  assert.match(NOW_CARD, /<ForecastAgeNotice forecastFetchedAt=\{data\.forecast_fetched_at\}/)
  assert.match(NOW_CARD, /nowFooterFor\(data\)/)
  assert.doesNotMatch(NOW_CARD, /nowFooter\(current, data\.fetched_at\)/)
})

// ── Tipo ─────────────────────────────────────────────────────────────────────

test('el tipo WeatherDashboardResponse trae forecast_fetched_at como campo opcional', () => {
  assert.match(API, /forecast_fetched_at\?: string \| null/)
})
