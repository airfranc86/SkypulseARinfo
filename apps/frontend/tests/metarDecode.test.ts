import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  FLIGHT_CATEGORY_RULES,
  cloudNote,
  dewpointText,
  observedLabel,
  qnhHpa,
  qnhNote,
  temperatureNote,
  visibilityNote,
  windDisplay,
} from '../src/lib/metarDecode.ts'
import { categoryNote } from '../src/lib/taf.ts'

// FRA-367 parte 2: decoding of the METAR cards, as pure functions. The real METAR below comes from the
// owner's screen on 2026-10-06 (SACO, wind varying between 010 and 090, QNH 1008 shown as 1008.1).
const RAW = 'METAR SACO 062300Z 06009KT 010V090 9999 BKN048 21/15 Q1008 NOSIG'

// ------------------------------------------------------------------ wind

test('wind: direction with three digits, speed, and the direction range when the METAR has one (010V090)', () => {
  const wind = windDisplay({ degrees: 60, speed_kts: 9 }, RAW)
  assert.equal(wind?.value, '060° / 9 kt')
  assert.match(wind?.note ?? '', /varía entre 010° y 090°/)
  assert.match(wind?.note ?? '', /Sin ráfagas reportadas/)
})

test('wind: gusts are reported', () => {
  const wind = windDisplay({ degrees: 290, speed_kts: 15, gust_kts: 28 }, 'METAR SAEZ 062100Z 29015G28KT 9999 SCT030 20/10 Q1012')
  assert.equal(wind?.value, '290° / 15 kt G28')
  assert.match(wind?.note ?? '', /Ráfagas de 28 kt/)
})

test('wind: VRB has no degree sign and is said as variable (raw text or missing direction)', () => {
  const byRaw = windDisplay({ degrees: 0, speed_kts: 3 }, 'METAR SASA 062100Z VRB03KT CAVOK 22/10 Q1010')
  assert.equal(byRaw?.value, 'Variable / 3 kt')
  assert.ok(!byRaw?.value.includes('°'))
  const byMissing = windDisplay({ speed_kts: 4 }, 'METAR SASA 062100Z 00004KT CAVOK 22/10 Q1010')
  assert.equal(byMissing?.value, 'Variable / 4 kt')
})

test('wind: calm is "Calmo", not "0° / 0 kt"', () => {
  const calm = windDisplay({ degrees: 0, speed_kts: 0 }, 'METAR SAEZ 062100Z 00000KT CAVOK 20/10 Q1012')
  assert.equal(calm?.value, 'Calmo')
})

test('wind: no wind data gives nothing to show', () => {
  assert.equal(windDisplay(undefined, RAW), null)
})

// ------------------------------------------------------------------ visibility (FAA, statute miles)

test('visibility note follows the FAA limits in miles, not the old limits in metres', () => {
  assert.match(visibilityNote(9999), /Excelente visibilidad — VFR sin restricciones/)
  assert.match(visibilityNote(9000), /VFR/)
  assert.match(visibilityNote(8100), /VFR/) // 5.03 SM
  assert.match(visibilityNote(8046), /MVFR/) // 5 SM or less
  assert.match(visibilityNote(7000), /MVFR/) // used to say "VFR posible"
  assert.match(visibilityNote(4829), /MVFR/) // just over 3 SM (3 SM = 4828.03 m)
  assert.match(visibilityNote(4828), /IFR/) // just under 3 SM
  assert.match(visibilityNote(4000), /IFR/) // used to say "MVFR"
  assert.ok(!/MVFR/.test(visibilityNote(4000)))
  assert.match(visibilityNote(1609), /IFR/) // 1 SM
  assert.match(visibilityNote(1500), /LIFR/)
  assert.match(visibilityNote(500), /LIFR/)
  assert.equal(visibilityNote(null), '')
})

// ------------------------------------------------------------------ flight category cards (miles with km)

test('the category cards say miles with their kilometre equivalent, not miles as kilometres', () => {
  const byCat = Object.fromEntries(FLIGHT_CATEGORY_RULES.map(r => [r.cat, r]))
  assert.deepEqual(Object.keys(byCat), ['VFR', 'MVFR', 'IFR', 'LIFR'])
  assert.equal(byCat.VFR.vis, 'Visib. más de 5 millas (8 km)')
  assert.equal(byCat.MVFR.vis, 'Visib. 3 a 5 millas (4,8 a 8 km)')
  assert.equal(byCat.IFR.vis, 'Visib. 1 a 3 millas (1,6 a 4,8 km)')
  assert.equal(byCat.LIFR.vis, 'Visib. menos de 1 milla (1,6 km)')
  assert.equal(byCat.IFR.ceiling, 'Techo 500 a 999 ft')
})

test('the page cards and the TAF card quote the same limits', () => {
  for (const rule of FLIGHT_CATEGORY_RULES) {
    const taf = categoryNote(rule.cat) ?? ''
    const kmPart = /\(([^)]*km)\)/.exec(rule.vis)?.[1]
    assert.ok(kmPart && taf.includes(kmPart), `${rule.cat}: "${kmPart}" is not in the TAF note "${taf}"`)
  }
})

// ------------------------------------------------------------------ temperature and dew point

test('temperature: a missing dew point never prints "undefined"', () => {
  assert.equal(dewpointText(21, 15), '21°C / Rocío 15°C')
  assert.equal(dewpointText(21, undefined), '21°C')
  assert.equal(dewpointText(21, null), '21°C')
  assert.ok(!dewpointText(21, undefined).includes('undefined'))
})

test('temperature note: spread and fog risk, and a plain note when the dew point is missing', () => {
  assert.equal(temperatureNote(21, 15), 'Diferencia Temp–Rocío: 6°C')
  assert.equal(temperatureNote(9, 8), 'Diferencia Temp–Rocío: 1°C — riesgo de niebla')
  assert.equal(temperatureNote(21, undefined), 'Temperatura registrada')
})

// ------------------------------------------------------------------ QNH

test('QNH is read from the METAR text: Q1008 is 1008 hPa, not 1008.1', () => {
  assert.equal(qnhHpa(RAW, 1008.1), 1008)
  assert.equal(qnhHpa('METAR SACO 062100Z 04012KT CAVOK 23/13 Q1007 NOSIG', 1007.1), 1007)
})

test('QNH in inches (A2992) is converted to whole hPa; without text it falls back to the rounded decoded value', () => {
  assert.equal(qnhHpa('METAR KJFK 062100Z 18010KT 10SM CLR 20/10 A2992', undefined), 1013)
  assert.equal(qnhHpa('METAR XXXX 062100Z 18010KT 9999 CLR 20/10', 1004.4), 1004)
})

test('a missing or null QNH shows no card and is never read as "muy baja"', () => {
  assert.equal(qnhHpa('METAR XXXX 062100Z 18010KT 9999 CLR 20/10', null), null)
  assert.equal(qnhHpa(undefined, undefined), null)
  assert.equal(qnhNote(null), null)
})

test('QNH note: low below 1009, normal from 1009 to 1022, high from 1023, with the extremes the site already had', () => {
  assert.match(qnhNote(975) ?? '', /muy baja/i)
  assert.match(qnhNote(1008) ?? '', /^Presión baja/)
  assert.match(qnhNote(1009) ?? '', /^Presión normal/)
  assert.match(qnhNote(1013) ?? '', /^Presión normal/)
  assert.match(qnhNote(1022) ?? '', /^Presión normal/)
  assert.match(qnhNote(1023) ?? '', /^Presión alta/)
  assert.match(qnhNote(1031) ?? '', /muy alta/i)
})

// ------------------------------------------------------------------ report time

test('report time: a CheckWX time without Z is UTC and is shown in Argentina time and UTC, in Spanish', () => {
  const label = observedLabel('2026-10-06T23:00:00')
  assert.equal(label, 'mar 06/10 20:00 (hora de Argentina) · 23:00 UTC')
  assert.ok(!/GMT/.test(label ?? ''))
})

test('report time: with Z it gives the same instant, and a missing or broken time gives null', () => {
  assert.equal(observedLabel('2026-10-06T23:00:00Z'), 'mar 06/10 20:00 (hora de Argentina) · 23:00 UTC')
  assert.equal(observedLabel(undefined), null)
  assert.equal(observedLabel('no es una fecha'), null)
})

// ------------------------------------------------------------------ clouds

test('clouds: ceiling in feet, and never "undefined ft"', () => {
  assert.equal(cloudNote([{ code: 'BKN', base_feet_agl: 4800 }], RAW), 'Techo definido a 4800 ft AGL')
  assert.equal(cloudNote([{ code: 'BKN' }], 'METAR SACO 062300Z 06009KT 9999 BKN 21/15 Q1008'), 'Techo definido')
  assert.ok(!cloudNote([{ code: 'OVC' }], '').includes('undefined'))
  assert.equal(cloudNote([{ code: 'FEW', base_feet_agl: 2000 }], 'METAR X 062300Z 06009KT 9999 FEW020 21/15 Q1008'), 'Sin capa de techo definida')
  assert.equal(cloudNote([], RAW), '')
  assert.equal(cloudNote(undefined, RAW), '')
})

test('clouds: CB and TCU are detected in the METAR text, because CheckWX is not known to send the type', () => {
  const cb = cloudNote([{ code: 'FEW', base_feet_agl: 2000 }], 'METAR X 062300Z 06009KT 9999 FEW020CB 21/15 Q1008')
  assert.match(cb, /Cumulonimbus/)
  const tcu = cloudNote([{ code: 'SCT', base_feet_agl: 3000 }], 'METAR X 062300Z 06009KT 9999 SCT030TCU 21/15 Q1008')
  assert.match(tcu, /Cúmulo|cúmulos en torre/i)
  const bySchema = cloudNote([{ code: 'FEW', base_feet_agl: 2000, type: 'CB' }], '')
  assert.match(bySchema, /Cumulonimbus/)
})
