import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { weatherDashboardQueryKey } from '../src/lib/weatherQueryKeys.ts'

// The key of the forecast dashboard in React Query's cache is shared on purpose: every page that loads it and Mora's
// floating bubble (which only READS the cache) must land on the same entry. A swapped argument or another model in
// either side would leave the bubble reading an entry nobody fills, silently, so the key lives in ONE function.

const SRC = new URL('../src/', import.meta.url)

function leer(ruta: string): string {
  return readFileSync(new URL(ruta, SRC), 'utf8').replaceAll('\r\n', '\n')
}

test('the key is [name, lat, lon, model], in that order', () => {
  assert.deepEqual(weatherDashboardQueryKey(-31.42, -64.19, 'consensus'), ['weather-dashboard', -31.42, -64.19, 'consensus'])
  assert.deepEqual(weatherDashboardQueryKey(null, null, 'gfs'), ['weather-dashboard', null, null, 'gfs'])
})

test('lat and lon are not swapped and the model is part of the key', () => {
  assert.notDeepEqual(weatherDashboardQueryKey(1, 2, 'consensus'), weatherDashboardQueryKey(2, 1, 'consensus'))
  assert.notDeepEqual(weatherDashboardQueryKey(1, 2, 'consensus'), weatherDashboardQueryKey(1, 2, 'gfs'))
})

test('the dashboard hook and the bubble hook build their key with the same function', () => {
  const pagina = leer('hooks/useWeather.ts')
  const burbuja = leer('hooks/useHumorMora.ts')
  assert.match(pagina, /queryKey:\s*weatherDashboardQueryKey\(lat,\s*lon,\s*model\)/)
  assert.match(burbuja, /queryKey:\s*weatherDashboardQueryKey\(lat,\s*lon,\s*'consensus'\)/)
})

test('the pages load the consensus model by default: that is the entry the bubble reads', () => {
  assert.match(leer('hooks/useWeather.ts'), /model:\s*'gfs'\s*\|\s*'ecmwf'\s*\|\s*'consensus'\s*=\s*'consensus'/)
})
