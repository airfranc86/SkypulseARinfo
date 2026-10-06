import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  categoryNote,
  changeLabel,
  cloudsText,
  formatTemperature,
  formatWindow,
  hasConvectiveSigns,
  isCavok,
  tafStatusMessage,
  visibilityText,
  weatherText,
  windText,
  type TafDecoded,
} from '../src/lib/taf.ts'

// FRA-365: the decoded TAF comes from GET /api/taf. The fixtures are the real backend output
// (`normalize_taf`) for four real Argentine TAFs captured on 2026-10-06, so a change in the
// backend contract shows up here.

const load = (icao: string): TafDecoded =>
  JSON.parse(readFileSync(new URL(`./fixtures/taf${icao}.json`, import.meta.url), 'utf8')) as TafDecoded

const saco = load('SACO')
const sari = load('SARI')
const sasa = load('SASA')
const saar = load('SAAR')

// ------------------------------------------------------------------ wind

test('wind: direction with cardinal point, speed and gusts', () => {
  assert.equal(windText(saco.periods[0].wind), 'NE (050°) a 15 kt')
  assert.equal(windText(saco.periods[4].wind), 'ONO (290°) a 15 kt')
  assert.equal(windText(saar.periods[1].wind), 'E (080°) a 10 kt, ráfagas de 20 kt')
})

test('wind: variable, calm and missing', () => {
  assert.equal(windText(sasa.periods[2].wind), 'Variable a 3 kt')
  assert.equal(windText({ direction_deg: 0, variable: false, speed_kt: 0, gust_kt: null }), 'Calmo')
  assert.equal(windText({ direction_deg: null, variable: false, speed_kt: 8, gust_kt: null }), '8 kt')
  assert.equal(windText(null), 'Sin dato')
})

// ------------------------------------------------------------------ visibility

test('visibility: 10 km or more, kilometres and metres', () => {
  assert.equal(visibilityText(saco.periods[0].visibility_m, saco.periods[0].visibility_over), '10 km o más')
  assert.equal(visibilityText(7000, false), '7 km')
  assert.equal(visibilityText(4500, false), '4,5 km')
  assert.equal(visibilityText(sari.periods[2].visibility_m, false), '500 m')
  assert.equal(visibilityText(null, false), 'Sin dato')
})

// ------------------------------------------------------------------ clouds

test('clouds: layers in Spanish with thousands separator', () => {
  assert.deepEqual(cloudsText(saco.periods[0].clouds), ['Nubes dispersas a 3.500 ft'])
  assert.deepEqual(cloudsText(saco.periods[1].clouds), [
    'Nubes fragmentadas a 3.500 ft',
    'Pocas nubes a 4.000 ft · cúmulos en torre (TCU)',
  ])
})

test('clouds: CB is flagged, NSC and a ceiling at 500 ft read well', () => {
  assert.ok(cloudsText(saar.periods[2].clouds).includes('Pocas nubes a 4.000 ft · cumulonimbus (CB)'))
  assert.deepEqual(cloudsText(sari.periods[1].clouds), ['Sin nubes significativas'])
  assert.deepEqual(cloudsText(sari.periods[2].clouds), ['Cielo cubierto a 500 ft'])
  assert.deepEqual(cloudsText([]), [])
})

// ------------------------------------------------------------------ weather

test('weather: intensity, descriptors and phenomena', () => {
  assert.deepEqual(weatherText(['TSRA']), ['tormenta con lluvia'])
  assert.deepEqual(weatherText(['+TSRA']), ['tormenta con lluvia fuerte'])
  assert.deepEqual(weatherText(['-RA', '-DZ']), ['lluvia leve', 'llovizna leve'])
  assert.deepEqual(weatherText(['SHRA']), ['chubascos de lluvia'])
  assert.deepEqual(weatherText(['FZFG']), ['niebla engelante'])
  assert.deepEqual(weatherText(['BR', 'FG']), ['neblina', 'niebla'])
  assert.deepEqual(weatherText(['TS']), ['tormenta'])
})

test('weather: NSW and unknown codes are never swallowed', () => {
  assert.deepEqual(weatherText(['NSW']), ['Sin fenómenos significativos'])
  assert.deepEqual(weatherText(['ZZ']), ['ZZ'])
  assert.deepEqual(weatherText([]), [])
})

// ------------------------------------------------------------------ CAVOK, change groups, convection

test('CAVOK: visibility 10 km or more, no significant cloud and no weather', () => {
  assert.equal(isCavok(saar.periods[0]), true) // "08010KT CAVOK"
  assert.equal(isCavok(sari.periods[1]), true) // "PROB30 ... CAVOK" arrives as NSC + NSW
  assert.equal(isCavok(saco.periods[0]), false) // SCT035
  assert.equal(isCavok(sari.periods[2]), false) // fog
})

test('change groups are named in plain Spanish', () => {
  assert.equal(changeLabel(saco.periods[0]), 'Condición base')
  assert.equal(changeLabel(saco.periods[1]), 'Cambio gradual')
  assert.equal(changeLabel(saco.periods[3]), 'Temporalmente · 40 % de probabilidad')
  assert.equal(changeLabel(sari.periods[1]), '30 % de probabilidad')
  assert.equal(changeLabel({ ...saco.periods[0], change: 'from' }), 'A partir de entonces')
})

test('convective signs: CB, TCU or a thunderstorm', () => {
  assert.equal(hasConvectiveSigns(saco.periods[1]), true) // FEW040TCU
  assert.equal(hasConvectiveSigns(saar.periods[2]), true) // TSRA and CB
  assert.equal(hasConvectiveSigns(saco.periods[0]), false)
  assert.equal(hasConvectiveSigns(sari.periods[2]), false)
})

// ------------------------------------------------------------------ times (always Argentina, not the device)

test('windows show Argentina time and UTC', () => {
  assert.deepEqual(formatWindow(saco.periods[0]), {
    local: 'mar 06/10 15:00 → 20:00',
    utc: '06/18Z → 06/23Z',
  })
  assert.deepEqual(formatWindow(saco.periods[1]), {
    local: 'mar 06/10 20:00 → mié 07/10 00:00',
    utc: '06/23Z → 07/03Z',
  })
})

test('temperatures: maximum and minimum with their local time', () => {
  assert.equal(formatTemperature(saco.temperatures[0]), 'Máxima 28 °C · mar 06/10 16:00')
  assert.equal(formatTemperature(saco.temperatures[1]), 'Mínima 14 °C · mié 07/10 07:00')
})

// ------------------------------------------------------------------ flight category notes (FAA, miles)

test('category notes use the FAA thresholds in miles with their kilometre equivalent', () => {
  assert.match(categoryNote('VFR') ?? '', /más de 5 millas \(8 km\).*3\.000 ft/)
  assert.match(categoryNote('MVFR') ?? '', /3 a 5 millas \(4,8 a 8 km\).*1\.000 a 3\.000 ft/)
  assert.match(categoryNote('IFR') ?? '', /1 a 3 millas \(1,6 a 4,8 km\).*500 a 999 ft/)
  assert.match(categoryNote('LIFR') ?? '', /menos de 1 milla \(1,6 km\).*menos de 500 ft/)
  assert.equal(categoryNote(null), null)
  assert.equal(categoryNote('XYZ'), null)
})

test('CAVOK: a phenomenon (fog, rain) is never CAVOK even with clear sky and 10 km', () => {
  const clear = saar.periods[0]
  assert.equal(isCavok(clear), true)
  assert.equal(isCavok({ ...clear, weather: ['FG'] }), false)
  assert.equal(isCavok({ ...clear, weather: ['NSW'] }), true)
  assert.equal(isCavok({ ...clear, visibility_over: false, visibility_m: 9000 }), false)
})

// ------------------------------------------------------------------ honest messages when the TAF is not shown

test('TAF messages tell apart "no TAF", "too many requests" and "could not fetch"', () => {
  assert.equal(tafStatusMessage(404), 'Este aeródromo no publica TAF.')
  assert.match(tafStatusMessage(429), /límite de consultas/)
  for (const status of [503, 500, 504, null]) {
    assert.match(tafStatusMessage(status), /No se pudo obtener el TAF/, String(status))
  }
  assert.notEqual(tafStatusMessage(404), tafStatusMessage(503))
})
