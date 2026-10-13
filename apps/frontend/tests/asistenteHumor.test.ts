import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  HUMORES,
  INTERVALO_MINIMO_CAMBIO_MS,
  LLUVIA_MINIMA_MM,
  humorDesdeClima,
  msHastaPoderCambiar,
  sostenerHumor,
  type DatosHumor,
  type HumorMora,
  type HumorSostenido,
} from '../src/lib/asistente/humor.ts'
import { GUST_KMH } from '../src/lib/weatherVerdict.ts'
import { WEATHER_ICON_CODES } from '../src/lib/weatherIconCodes.ts'

// Mora's mood. `humorDesdeClima` is a pure function of plain data; `sostenerHumor` is the "never more than
// one state change per minute" rule, with the clock passed in. Priority, highest first:
// alerta > pensando / respondiendo / confundido > dormido > erizado > encogido > planeando > reposo.

function aviso(nivel: string) {
  return { nivel, tipo: 'Tormentas fuertes', fecha_desde: null, fecha_hasta: null, descripcion: '' }
}

/** Nothing known and nothing happening: Mora at rest. Each case overrides only what it is about. */
const BASE: DatosHumor = {
  alertas: [],
  riesgoConvectivo: null,
  panel: null,
  esDeDia: null,
  rafagaKmh: null,
  intensidadViento: null,
  icono: null,
  precipMm: null,
}

function datos(cambios: Partial<DatosHumor> = {}): DatosHumor {
  return { ...BASE, ...cambios }
}

// One patch per trigger, from the highest priority down.
const ALERTA: Partial<DatosHumor> = { alertas: [aviso('naranja')] }
const PANEL: Partial<DatosHumor> = { panel: 'pensando' }
const NOCHE: Partial<DatosHumor> = { esDeDia: false }
const RAFAGA: Partial<DatosHumor> = { rafagaKmh: 55 }
const LLUVIA: Partial<DatosHumor> = { icono: 'rain', precipMm: 2 }
const TERMICAS: Partial<DatosHumor> = { esDeDia: true, riesgoConvectivo: 'low' }

// ── Base case ────────────────────────────────────────────────────────────────

test('with nothing known and nothing happening Mora is at rest', () => {
  assert.equal(humorDesdeClima(BASE), 'reposo')
})

// ── One case per trigger ─────────────────────────────────────────────────────

test('alerta: an orange SMN warning', () => {
  assert.equal(humorDesdeClima(datos({ alertas: [aviso('naranja')] })), 'alerta')
})

test('alerta: a red SMN warning', () => {
  assert.equal(humorDesdeClima(datos({ alertas: [aviso('rojo')] })), 'alerta')
})

test('alerta: the level is read like the rest of the app (case and spaces do not matter)', () => {
  assert.equal(humorDesdeClima(datos({ alertas: [aviso(' Rojo ')] })), 'alerta')
  assert.equal(humorDesdeClima(datos({ alertas: [aviso('NARANJA')] })), 'alerta')
})

test('alerta: one critical warning among lesser ones is enough', () => {
  assert.equal(humorDesdeClima(datos({ alertas: [aviso('amarillo'), aviso('verde'), aviso('naranja')] })), 'alerta')
})

test('alerta: high convective risk in the current slot', () => {
  assert.equal(humorDesdeClima(datos({ riesgoConvectivo: 'high' })), 'alerta')
})

test('alerta: severe convective risk in the current slot', () => {
  assert.equal(humorDesdeClima(datos({ riesgoConvectivo: 'severe' })), 'alerta')
})

test('no alerta: yellow and green warnings, unknown levels and no warnings do not count', () => {
  assert.notEqual(humorDesdeClima(datos({ alertas: [aviso('amarillo')] })), 'alerta')
  assert.notEqual(humorDesdeClima(datos({ alertas: [aviso('verde')] })), 'alerta')
  assert.notEqual(humorDesdeClima(datos({ alertas: [aviso('violeta'), aviso('')] })), 'alerta')
  assert.notEqual(humorDesdeClima(datos({ alertas: [] })), 'alerta')
})

test('no alerta: low, moderate or unknown convective risk do not count', () => {
  assert.notEqual(humorDesdeClima(datos({ riesgoConvectivo: 'low' })), 'alerta')
  assert.notEqual(humorDesdeClima(datos({ riesgoConvectivo: 'moderate' })), 'alerta')
  assert.notEqual(humorDesdeClima(datos({ riesgoConvectivo: null })), 'alerta')
  assert.notEqual(humorDesdeClima(datos({ riesgoConvectivo: undefined })), 'alerta')
})

test('the panel states pass through as they are: pensando, respondiendo, confundido', () => {
  assert.equal(humorDesdeClima(datos({ panel: 'pensando' })), 'pensando')
  assert.equal(humorDesdeClima(datos({ panel: 'respondiendo' })), 'respondiendo')
  assert.equal(humorDesdeClima(datos({ panel: 'confundido' })), 'confundido')
})

test('dormido: it is night (is_day false)', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: false })), 'dormido')
})

test('no dormido: daytime or unknown day/night', () => {
  assert.notEqual(humorDesdeClima(datos({ esDeDia: true })), 'dormido')
  assert.notEqual(humorDesdeClima(datos({ esDeDia: null })), 'dormido')
})

test('erizado: a gust at the shared threshold (40 km/h) or above', () => {
  assert.equal(humorDesdeClima(datos({ rafagaKmh: GUST_KMH })), 'erizado')
  assert.equal(humorDesdeClima(datos({ rafagaKmh: GUST_KMH + 0.1 })), 'erizado')
  assert.equal(humorDesdeClima(datos({ rafagaKmh: 95 })), 'erizado')
})

test('erizado: the threshold is the plan value, 40 km/h, and 39.9 is not enough', () => {
  assert.equal(GUST_KMH, 40)
  assert.equal(humorDesdeClima(datos({ rafagaKmh: 40 })), 'erizado')
  assert.notEqual(humorDesdeClima(datos({ rafagaKmh: 39.9 })), 'erizado')
  assert.notEqual(humorDesdeClima(datos({ rafagaKmh: GUST_KMH - 0.1 })), 'erizado')
})

test('erizado: intense sustained wind, even without a gust figure', () => {
  assert.equal(humorDesdeClima(datos({ intensidadViento: 'intensa' })), 'erizado')
  assert.equal(humorDesdeClima(datos({ intensidadViento: 'intensa', rafagaKmh: null })), 'erizado')
})

test('no erizado: light or moderate wind, unknown wind and invalid gust values', () => {
  assert.notEqual(humorDesdeClima(datos({ intensidadViento: 'leve' })), 'erizado')
  assert.notEqual(humorDesdeClima(datos({ intensidadViento: 'moderada' })), 'erizado')
  assert.notEqual(humorDesdeClima(datos({ intensidadViento: null })), 'erizado')
  assert.notEqual(humorDesdeClima(datos({ rafagaKmh: null })), 'erizado')
  assert.notEqual(humorDesdeClima(datos({ rafagaKmh: Number.NaN })), 'erizado')
  assert.notEqual(humorDesdeClima(datos({ rafagaKmh: 0 })), 'erizado')
})

// Rain rule (owner decision 2026-10-13): a rain or drizzle icon AND at least 1 mm in the slot. Both are needed.

const ICONOS_LLUVIA = [
  'rain',
  'partly-cloudy-day-rain',
  'partly-cloudy-night-rain',
  'mostly-clear-day-rain',
  'mostly-clear-night-rain',
  'drizzle',
  'overcast-drizzle',
  'partly-cloudy-day-drizzle',
  'partly-cloudy-night-drizzle',
] as const

test('encogido: a rain icon together with at least 1 mm', () => {
  for (const icono of ICONOS_LLUVIA.filter((codigo) => codigo.endsWith('rain'))) {
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 5 })), 'encogido', icono)
  }
})

test('encogido: a drizzle icon together with at least 1 mm', () => {
  for (const icono of ICONOS_LLUVIA.filter((codigo) => codigo.endsWith('drizzle'))) {
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 1.5 })), 'encogido', icono)
  }
})

test('LLUVIA_MINIMA_MM is 1 mm per 3 h slot, inclusive, and not the shared 0.1 mm limit', () => {
  assert.equal(LLUVIA_MINIMA_MM, 1)
  assert.equal(humorDesdeClima(datos({ icono: 'rain', precipMm: LLUVIA_MINIMA_MM })), 'encogido')
  assert.notEqual(humorDesdeClima(datos({ icono: 'rain', precipMm: LLUVIA_MINIMA_MM - 0.01 })), 'encogido')
})

test('encogido: heavy amounts with a rain icon', () => {
  assert.equal(humorDesdeClima(datos({ icono: 'rain', precipMm: 10 })), 'encogido')
  assert.equal(humorDesdeClima(datos({ icono: 'rain', precipMm: 80 })), 'encogido')
})

test('encogido: the mm limit is 1 and inclusive (0.99 no, 1 yes, 1.01 yes), for rain and drizzle alike', () => {
  for (const icono of ['rain', 'drizzle']) {
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 0.99 })), 'reposo', `${icono} 0.99 mm`)
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 1 })), 'encogido', `${icono} 1 mm`)
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 1.01 })), 'encogido', `${icono} 1.01 mm`)
  }
})

test('no encogido: a drizzle or rain icon with a light amount (the old 0.1 mm limit no longer counts)', () => {
  for (const icono of ['drizzle', 'rain']) {
    for (const precipMm of [0, 0.1, 0.11, 0.2, 0.5, 0.99]) {
      assert.equal(humorDesdeClima(datos({ icono, precipMm })), 'reposo', `${icono} ${precipMm} mm`)
    }
  }
})

test('no encogido: millimeters without a rain icon (no icon, an empty one or a dry one)', () => {
  for (const icono of [null, '', 'clear-day', 'overcast', 'partly-cloudy-day']) {
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 5 })), 'reposo', String(icono))
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 50 })), 'reposo', `${icono} 50 mm`)
  }
})

test('no encogido: a rain icon with unknown, NaN, infinite or negative millimeters counts as not raining', () => {
  for (const precipMm of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -1, -5, -0.5]) {
    assert.equal(humorDesdeClima(datos({ icono: 'rain', precipMm })), 'reposo', `rain with ${String(precipMm)}`)
    assert.equal(humorDesdeClima(datos({ icono: 'drizzle', precipMm })), 'reposo', `drizzle with ${String(precipMm)}`)
  }
})

test('no encogido: icons that are not rain or drizzle, even with plenty of millimeters', () => {
  for (const icono of ['clear-day', 'overcast', 'snow', 'sleet', 'fog', 'thunderstorms', 'hail', 'partly-cloudy-night', '']) {
    assert.notEqual(humorDesdeClima(datos({ icono, precipMm: 5 })), 'encogido', icono)
  }
})

test('no encogido: codes that merely contain the letters "rain" are not rain', () => {
  for (const icono of ['rainbow', 'rainbow-clear', 'terrain', 'brain-day', 'drizzles']) {
    assert.notEqual(humorDesdeClima(datos({ icono, precipMm: 5 })), 'encogido', icono)
  }
})

test('the rain icons are exactly the current rain and drizzle codes: no heavy-rain or thunderstorm code widens the list', () => {
  const comoLluvia = WEATHER_ICON_CODES.filter((icono) => humorDesdeClima(datos({ icono, precipMm: 5 })) === 'encogido')
  assert.deepEqual([...comoLluvia].sort(), [...ICONOS_LLUVIA].sort())
  for (const icono of WEATHER_ICON_CODES.filter((codigo) => codigo.startsWith('thunderstorms'))) {
    assert.equal(humorDesdeClima(datos({ icono, precipMm: 20 })), 'reposo', icono)
  }
})

test('planeando: daytime with low convective risk (thermals, no storm)', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: true, riesgoConvectivo: 'low' })), 'planeando')
})

test('planeando: daytime with moderate convective risk', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: true, riesgoConvectivo: 'moderate' })), 'planeando')
})

test('planeando: gusts just under the threshold still allow it', () => {
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, rafagaKmh: GUST_KMH - 0.1 })), 'planeando')
})

test('no planeando: night, unknown day/night, or unknown convective risk fall to reposo', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: false, riesgoConvectivo: 'low' })), 'dormido')
  assert.equal(humorDesdeClima(datos({ esDeDia: null, riesgoConvectivo: 'low' })), 'reposo')
  assert.equal(humorDesdeClima(datos({ esDeDia: true, riesgoConvectivo: null })), 'reposo')
  assert.equal(humorDesdeClima(datos({ esDeDia: true, riesgoConvectivo: undefined })), 'reposo')
})

test('no planeando: rain or strong gusts in the day turn it into encogido or erizado', () => {
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, ...LLUVIA })), 'encogido')
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, rafagaKmh: GUST_KMH })), 'erizado')
})

test('planeando: a light drizzle (under 1 mm) or millimeters without a rain icon do not stop the glide', () => {
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: 'drizzle', precipMm: 0.2 })), 'planeando')
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: 'rain', precipMm: 0.99 })), 'planeando')
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: 'clear-day', precipMm: 5 })), 'planeando')
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: null, precipMm: 5 })), 'planeando')
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: 'rain', precipMm: null })), 'planeando')
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: 'rain', precipMm: Number.NaN })), 'planeando')
})

test('planeando: at 1 mm with a rain icon the glide gives way to encogido', () => {
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: 'drizzle', precipMm: 1 })), 'encogido')
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono: 'rain', precipMm: 1.01 })), 'encogido')
})

test('encogido and planeando share one rain rule: over a grid of icons and amounts exactly one of them fires', () => {
  const iconos = [null, '', 'clear-day', 'rain', 'drizzle', 'partly-cloudy-day-rain', 'overcast-drizzle', 'rainbow', 'thunderstorms']
  const cantidades = [null, undefined, Number.NaN, Number.POSITIVE_INFINITY, -1, 0, 0.1, 0.2, 0.99, 1, 1.01, 5, 40]
  for (const icono of iconos) {
    for (const precipMm of cantidades) {
      const llueve = icono !== null && (ICONOS_LLUVIA as readonly string[]).includes(icono) && typeof precipMm === 'number' && Number.isFinite(precipMm) && precipMm >= 1
      assert.equal(humorDesdeClima(datos({ ...TERMICAS, icono, precipMm })), llueve ? 'encogido' : 'planeando', `${String(icono)} with ${String(precipMm)} mm`)
    }
  }
})

test('reposo: a calm day with light wind and no rain, but unknown convective risk', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: true, rafagaKmh: 10, intensidadViento: 'leve', icono: 'clear-day', precipMm: 0 })), 'reposo')
})

// ── Priority: every pair of triggers that can overlap ────────────────────────

const POR_PRIORIDAD: readonly (readonly [HumorMora, Partial<DatosHumor>])[] = [
  ['alerta', ALERTA],
  ['pensando', PANEL],
  ['dormido', NOCHE],
  ['erizado', RAFAGA],
  ['encogido', LLUVIA],
]

for (let i = 0; i < POR_PRIORIDAD.length; i++) {
  for (let j = i + 1; j < POR_PRIORIDAD.length; j++) {
    const [mayor, parcheMayor] = POR_PRIORIDAD[i]
    const [menor, parcheMenor] = POR_PRIORIDAD[j]
    test(`priority: ${mayor} wins over ${menor} when both apply`, () => {
      assert.equal(humorDesdeClima(datos(parcheMenor)), menor, `${menor} alone`)
      assert.equal(humorDesdeClima(datos(parcheMayor)), mayor, `${mayor} alone`)
      assert.equal(humorDesdeClima(datos({ ...parcheMenor, ...parcheMayor })), mayor)
    })
  }
}

const MOODS_PANEL = ['pensando', 'respondiendo', 'confundido'] as const

test('priority: the alert also wins over the panel states and over a calm planeando day', () => {
  for (const panel of MOODS_PANEL) {
    assert.equal(humorDesdeClima(datos({ ...ALERTA, panel })), 'alerta', panel)
  }
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, ...ALERTA })), 'alerta')
})

test('priority: high or severe convective risk wins over every panel mood', () => {
  for (const riesgoConvectivo of ['high', 'severe'] as const) {
    for (const panel of MOODS_PANEL) {
      assert.equal(humorDesdeClima(datos({ riesgoConvectivo, panel })), 'alerta', `${riesgoConvectivo} + ${panel}`)
    }
  }
})

test('priority: high convective risk at night is alerta, not dormido', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: false, riesgoConvectivo: 'high' })), 'alerta')
})

test('priority: intense sustained wind alone (no gust figure) wins over rain and loses to night and the panel', () => {
  const vientoIntenso: Partial<DatosHumor> = { intensidadViento: 'intensa', rafagaKmh: null }
  assert.equal(humorDesdeClima(datos(vientoIntenso)), 'erizado')
  assert.equal(humorDesdeClima(datos({ ...vientoIntenso, ...LLUVIA })), 'erizado')
  assert.equal(humorDesdeClima(datos({ ...vientoIntenso, ...TERMICAS })), 'erizado')
  assert.equal(humorDesdeClima(datos({ ...vientoIntenso, ...NOCHE })), 'dormido')
  for (const panel of MOODS_PANEL) {
    assert.equal(humorDesdeClima(datos({ ...vientoIntenso, panel })), panel, panel)
  }
  assert.equal(humorDesdeClima(datos({ ...vientoIntenso, ...ALERTA })), 'alerta')
})

test('priority: planeando loses to every panel mood and to the alert', () => {
  assert.equal(humorDesdeClima(datos(TERMICAS)), 'planeando')
  for (const panel of MOODS_PANEL) {
    assert.equal(humorDesdeClima(datos({ ...TERMICAS, panel })), panel, panel)
  }
  assert.equal(humorDesdeClima(datos({ ...TERMICAS, ...ALERTA })), 'alerta')
})

test('alertas null or undefined behave as an empty list: nothing fires and nothing throws', () => {
  assert.equal(humorDesdeClima(datos({ alertas: undefined })), 'reposo')
  assert.equal(humorDesdeClima(datos({ alertas: null })), 'reposo')
  // the other signals keep working without the warnings list
  assert.equal(humorDesdeClima(datos({ alertas: undefined, riesgoConvectivo: 'high' })), 'alerta')
  assert.equal(humorDesdeClima(datos({ alertas: null, esDeDia: false })), 'dormido')
  assert.equal(humorDesdeClima(datos({ alertas: undefined, ...TERMICAS })), 'planeando')
})

test('priority: the panel states wake Mora up at night and beat gusts and rain', () => {
  for (const panel of ['pensando', 'respondiendo', 'confundido'] as const) {
    assert.equal(humorDesdeClima(datos({ ...NOCHE, ...RAFAGA, ...LLUVIA, panel })), panel, panel)
  }
})

test('priority: a red warning at night is alerta, not dormido', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: false, alertas: [aviso('rojo')] })), 'alerta')
})

test('priority: severe convective risk at night is alerta, not dormido', () => {
  assert.equal(humorDesdeClima(datos({ esDeDia: false, riesgoConvectivo: 'severe' })), 'alerta')
})

test('priority: peeling the signals off one by one walks down the whole ladder', () => {
  const todo = datos({
    alertas: [aviso('rojo')],
    panel: 'respondiendo',
    esDeDia: false,
    rafagaKmh: 70,
    intensidadViento: 'intensa',
    icono: 'rain',
    precipMm: 5,
    riesgoConvectivo: 'low',
  })
  assert.equal(humorDesdeClima(todo), 'alerta')
  const sinAlerta = { ...todo, alertas: [] }
  assert.equal(humorDesdeClima(sinAlerta), 'respondiendo')
  const sinPanel = { ...sinAlerta, panel: null }
  assert.equal(humorDesdeClima(sinPanel), 'dormido')
  const deDia = { ...sinPanel, esDeDia: true }
  assert.equal(humorDesdeClima(deDia), 'erizado')
  const sinViento = { ...deDia, rafagaKmh: 12, intensidadViento: 'leve' }
  assert.equal(humorDesdeClima(sinViento), 'encogido')
  const sinLluvia = { ...sinViento, icono: 'clear-day', precipMm: 0 }
  assert.equal(humorDesdeClima(sinLluvia), 'planeando')
  const sinRiesgo = { ...sinLluvia, riesgoConvectivo: null }
  assert.equal(humorDesdeClima(sinRiesgo), 'reposo')
})

/** The data that makes each mood fire on its own. */
const DISPARADORES: Readonly<Record<HumorMora, Partial<DatosHumor>>> = {
  alerta: ALERTA,
  pensando: { panel: 'pensando' },
  respondiendo: { panel: 'respondiendo' },
  confundido: { panel: 'confundido' },
  dormido: NOCHE,
  erizado: RAFAGA,
  encogido: LLUVIA,
  planeando: TERMICAS,
  reposo: {},
}

test('HUMORES lists every mood once', () => {
  assert.deepEqual([...HUMORES].sort(), Object.keys(DISPARADORES).sort())
  assert.equal(new Set(HUMORES).size, HUMORES.length)
})

test('HUMORES is the real priority order: each mood beats every mood listed after it', () => {
  // Derived from the declared order, not copied from it: reordering the checks in `humorDesdeClima` (or the
  // list) breaks this. Where two triggers write the same field (the two panel moods; night against day for
  // planeando) the earlier mood's value is kept, since both cannot hold at once.
  HUMORES.forEach((mayor, indice) => {
    assert.equal(humorDesdeClima(datos(DISPARADORES[mayor])), mayor, `${mayor} on its own`)
    for (const menor of HUMORES.slice(indice + 1)) {
      assert.equal(humorDesdeClima(datos({ ...DISPARADORES[menor], ...DISPARADORES[mayor] })), mayor, `${mayor} over ${menor}`)
    }
  })
})

// ── Purity ───────────────────────────────────────────────────────────────────

function congelarProfundo<T>(valor: T): T {
  if (valor !== null && typeof valor === 'object') {
    for (const hijo of Object.values(valor)) congelarProfundo(hijo)
    Object.freeze(valor)
  }
  return valor
}

test('the mood does not modify its input and gives the same answer every time', () => {
  const entrada = congelarProfundo(datos({ alertas: [aviso('amarillo'), aviso('rojo')], esDeDia: false, rafagaKmh: 50 }))
  assert.equal(humorDesdeClima(entrada), 'alerta')
  assert.equal(humorDesdeClima(entrada), 'alerta')
  assert.equal(entrada.alertas.length, 2)
  assert.equal(entrada.alertas[0].nivel, 'amarillo')
})

// ── One state change per minute ──────────────────────────────────────────────

const T0 = Date.UTC(2026, 9, 13, 15, 0, 0)

test('the minimum gap between mood changes is one minute', () => {
  assert.equal(INTERVALO_MINIMO_CAMBIO_MS, 60_000)
})

test('the first mood is adopted right away, stamped with the current time', () => {
  assert.deepEqual(sostenerHumor(null, 'planeando', T0), { humor: 'planeando', cambioEnMs: T0 })
})

test('the same mood proposed again changes nothing, not even the stamp', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.deepEqual(sostenerHumor(previo, 'reposo', T0 + 5 * 60_000), { humor: 'reposo', cambioEnMs: T0 })
})

test('a different mood is held back until a full minute has passed since the last change', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.deepEqual(sostenerHumor(previo, 'erizado', T0), previo)
  assert.deepEqual(sostenerHumor(previo, 'erizado', T0 + 1), previo)
  assert.deepEqual(sostenerHumor(previo, 'erizado', T0 + 30_000), previo)
  assert.deepEqual(sostenerHumor(previo, 'erizado', T0 + 59_999), previo)
})

test('at exactly one minute, and after it, the change goes through and the timer restarts', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.deepEqual(sostenerHumor(previo, 'erizado', T0 + 60_000), { humor: 'erizado', cambioEnMs: T0 + 60_000 })
  assert.deepEqual(sostenerHumor(previo, 'dormido', T0 + 61_000), { humor: 'dormido', cambioEnMs: T0 + 61_000 })
  assert.deepEqual(sostenerHumor(previo, 'alerta', T0 + 3_600_000), { humor: 'alerta', cambioEnMs: T0 + 3_600_000 })
})

test('after a change the next one has to wait a full minute counted from that change', () => {
  const cambiado = sostenerHumor({ humor: 'reposo', cambioEnMs: T0 }, 'erizado', T0 + 90_000)
  assert.deepEqual(cambiado, { humor: 'erizado', cambioEnMs: T0 + 90_000 })
  assert.equal(sostenerHumor(cambiado, 'encogido', T0 + 90_000 + 59_999).humor, 'erizado')
  assert.equal(sostenerHumor(cambiado, 'encogido', T0 + 90_000 + 60_000).humor, 'encogido')
})

test('proposals flipping every second never move Mora more than once per minute', () => {
  let estado: HumorSostenido | null = null
  const cambios: number[] = []
  for (let segundo = 0; segundo <= 600; segundo++) {
    const propuesto: HumorMora = segundo % 2 === 0 ? 'reposo' : 'erizado'
    const siguiente: HumorSostenido = sostenerHumor(estado, propuesto, T0 + segundo * 1000)
    if (estado === null || siguiente.humor !== estado.humor) cambios.push(segundo * 1000)
    estado = siguiente
  }
  assert.equal(cambios[0], 0)
  for (let i = 1; i < cambios.length; i++) {
    assert.ok(cambios[i] - cambios[i - 1] >= INTERVALO_MINIMO_CAMBIO_MS, `gap before change ${i}: ${cambios[i] - cambios[i - 1]} ms`)
  }
  assert.equal(cambios.length, 10)
})

test('a clock that jumps backwards or is invalid does not freeze Mora', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.deepEqual(sostenerHumor(previo, 'erizado', T0 - 10 * 60_000), { humor: 'erizado', cambioEnMs: T0 - 10 * 60_000 })
  assert.deepEqual(sostenerHumor(previo, 'erizado', Number.NaN).humor, 'erizado')
})

test('the held state is never modified: a new object comes back', () => {
  const previo = Object.freeze({ humor: 'reposo', cambioEnMs: T0 } as HumorSostenido)
  const nuevo = sostenerHumor(previo, 'erizado', T0 + 120_000)
  assert.notEqual(nuevo, previo)
  assert.deepEqual(previo, { humor: 'reposo', cambioEnMs: T0 })
  assert.ok(Object.isFrozen(nuevo))
})

// ── How long until a held mood can change (arms one setTimeout) ──────────────

test('msHastaPoderCambiar: with no mood shown yet there is nothing to wait for', () => {
  assert.equal(msHastaPoderCambiar(null, T0), 0)
})

test('msHastaPoderCambiar: counts down the one-minute window from the last change', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.equal(msHastaPoderCambiar(previo, T0), 60_000)
  assert.equal(msHastaPoderCambiar(previo, T0 + 1), 59_999)
  assert.equal(msHastaPoderCambiar(previo, T0 + 20_000), 40_000)
  assert.equal(msHastaPoderCambiar(previo, T0 + 59_999), 1)
})

test('msHastaPoderCambiar: is 0 from exactly one minute on', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.equal(msHastaPoderCambiar(previo, T0 + 60_000), 0)
  assert.equal(msHastaPoderCambiar(previo, T0 + 60_001), 0)
  assert.equal(msHastaPoderCambiar(previo, T0 + 3_600_000), 0)
})

test('msHastaPoderCambiar: a clock that went backwards or is not a number means no wait', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.equal(msHastaPoderCambiar(previo, T0 - 1), 0)
  assert.equal(msHastaPoderCambiar(previo, T0 - 10 * 60_000), 0)
  assert.equal(msHastaPoderCambiar(previo, Number.NaN), 0)
  assert.equal(msHastaPoderCambiar({ humor: 'reposo', cambioEnMs: Number.NaN }, T0), 0)
})

test('msHastaPoderCambiar: only looks at the one-minute window, whatever the mood is', () => {
  for (const humor of HUMORES) {
    assert.equal(msHastaPoderCambiar({ humor, cambioEnMs: T0 }, T0 + 25_000), 35_000, humor)
  }
})

test('msHastaPoderCambiar: waiting that long is exactly what lets a held weather change through', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  for (const transcurrido of [0, 1, 999, 20_000, 59_998, 59_999, 60_000, 90_000]) {
    const ahoraMs = T0 + transcurrido
    const espera = msHastaPoderCambiar(previo, ahoraMs)
    assert.equal(sostenerHumor(previo, 'erizado', ahoraMs).humor === 'erizado', espera === 0, `at +${transcurrido} ms`)
    assert.equal(sostenerHumor(previo, 'erizado', ahoraMs + espera).humor, 'erizado', `after waiting ${espera} ms from +${transcurrido}`)
    if (espera > 0) assert.equal(sostenerHumor(previo, 'erizado', ahoraMs + espera - 1).humor, 'reposo', `one ms before the wait ends`)
  }
})

test('msHastaPoderCambiar: a fractional clock is rounded up so a timer of that length is never early', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  const ahoraMs = T0 + 0.5
  const espera = msHastaPoderCambiar(previo, ahoraMs)
  assert.equal(espera, 60_000)
  assert.equal(sostenerHumor(previo, 'erizado', ahoraMs + espera).humor, 'erizado')
  assert.equal(msHastaPoderCambiar(previo, T0 + 59_999.25), 1)
})

test('msHastaPoderCambiar: does not modify the held state and always gives a whole, non-negative, finite number', () => {
  const previo = Object.freeze({ humor: 'dormido', cambioEnMs: T0 } as HumorSostenido)
  for (const ahoraMs of [T0 - 5, T0, T0 + 17, T0 + 60_000, Number.NaN]) {
    const espera = msHastaPoderCambiar(previo, ahoraMs)
    assert.ok(Number.isInteger(espera) && espera >= 0 && espera <= INTERVALO_MINIMO_CAMBIO_MS, `value ${espera}`)
  }
  assert.deepEqual(previo, { humor: 'dormido', cambioEnMs: T0 })
})

// ── The panel moods are exempt from the one-change-per-minute rule ───────────

test('panel: entering the panel passes at once, even 20 s after a weather mood was adopted', () => {
  const previo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  for (const panel of MOODS_PANEL) {
    assert.deepEqual(sostenerHumor(previo, panel, T0 + 20_000), { humor: panel, cambioEnMs: T0 + 20_000 }, panel)
  }
})

test('panel: pensando to respondiendo 2 s later passes and restarts the stamp', () => {
  const pensando = sostenerHumor({ humor: 'reposo', cambioEnMs: T0 }, 'pensando', T0 + 20_000)
  assert.deepEqual(sostenerHumor(pensando, 'respondiendo', T0 + 22_000), { humor: 'respondiendo', cambioEnMs: T0 + 22_000 })
})

test('panel: any panel mood can follow any other one without waiting', () => {
  for (const desde of MOODS_PANEL) {
    for (const hasta of MOODS_PANEL) {
      if (desde === hasta) continue
      assert.deepEqual(sostenerHumor({ humor: desde, cambioEnMs: T0 }, hasta, T0 + 1_000), { humor: hasta, cambioEnMs: T0 + 1_000 }, `${desde} to ${hasta}`)
    }
  }
})

test('panel: leaving it 3 s after its last change (opened 71 s earlier) follows the weather at once', () => {
  let estado = sostenerHumor(null, 'reposo', T0)
  estado = sostenerHumor(estado, 'pensando', T0 + 1_000) // the panel opens
  estado = sostenerHumor(estado, 'respondiendo', T0 + 69_000) // the answer arrives
  assert.equal(estado.humor, 'respondiendo')
  // the panel closes 3 s later, 71 s after it opened: the weather says erizado and Mora must follow
  estado = sostenerHumor(estado, 'erizado', T0 + 72_000)
  assert.deepEqual(estado, { humor: 'erizado', cambioEnMs: T0 + 72_000 })
})

test('panel: leaving it works the same from every panel mood, to every weather mood, within a second', () => {
  for (const panel of MOODS_PANEL) {
    for (const clima of ['alerta', 'dormido', 'erizado', 'encogido', 'planeando', 'reposo'] as const) {
      assert.deepEqual(sostenerHumor({ humor: panel, cambioEnMs: T0 }, clima, T0 + 1_000), { humor: clima, cambioEnMs: T0 + 1_000 }, `${panel} to ${clima}`)
    }
  }
})

test('panel: after leaving it, the next weather change waits one minute from that stamp', () => {
  const salida = sostenerHumor({ humor: 'respondiendo', cambioEnMs: T0 }, 'erizado', T0 + 3_000)
  assert.deepEqual(salida, { humor: 'erizado', cambioEnMs: T0 + 3_000 })
  assert.equal(sostenerHumor(salida, 'encogido', T0 + 3_000 + 59_999).humor, 'erizado')
  assert.deepEqual(sostenerHumor(salida, 'encogido', T0 + 3_000 + 60_000), { humor: 'encogido', cambioEnMs: T0 + 3_000 + 60_000 })
})

test('panel: a weather mood that comes back after the panel keeps the stamp of the moment it came back', () => {
  let estado = sostenerHumor(null, 'reposo', T0)
  estado = sostenerHumor(estado, 'pensando', T0 + 10_000)
  estado = sostenerHumor(estado, 'reposo', T0 + 12_000)
  assert.deepEqual(estado, { humor: 'reposo', cambioEnMs: T0 + 12_000 })
})

test('panel: the same panel mood proposed again changes nothing', () => {
  const previo: HumorSostenido = { humor: 'pensando', cambioEnMs: T0 }
  assert.deepEqual(sostenerHumor(previo, 'pensando', T0 + 500), previo)
})

test('panel: weather to weather, alerta included, still waits one minute', () => {
  const reposo: HumorSostenido = { humor: 'reposo', cambioEnMs: T0 }
  assert.deepEqual(sostenerHumor(reposo, 'alerta', T0 + 20_000), reposo)
  const alerta: HumorSostenido = { humor: 'alerta', cambioEnMs: T0 }
  assert.deepEqual(sostenerHumor(alerta, 'reposo', T0 + 20_000), alerta)
  assert.deepEqual(sostenerHumor(alerta, 'dormido', T0 + 59_999), alerta)
  assert.equal(sostenerHumor(alerta, 'dormido', T0 + 60_000).humor, 'dormido')
})

test('panel: with one panel visit in a flipping-weather run, weather-to-weather changes still come a minute after any previous change', () => {
  const esPanel = (humor: HumorMora): boolean => (MOODS_PANEL as readonly HumorMora[]).includes(humor)
  let estado: HumorSostenido = sostenerHumor(null, 'reposo', T0)
  let ultimoCambioMs = T0
  const cambiosDeClima: number[] = []
  for (let segundo = 1; segundo <= 400; segundo++) {
    const ahoraMs = T0 + segundo * 1000
    const panelAbierto = segundo >= 130 && segundo < 134
    const clima: HumorMora = segundo % 2 === 0 ? 'erizado' : 'encogido'
    const siguiente: HumorSostenido = sostenerHumor(estado, panelAbierto ? 'pensando' : clima, ahoraMs)
    if (siguiente.humor !== estado.humor) {
      if (!esPanel(estado.humor) && !esPanel(siguiente.humor)) {
        assert.ok(ahoraMs - ultimoCambioMs >= INTERVALO_MINIMO_CAMBIO_MS, `weather change at ${segundo} s came ${ahoraMs - ultimoCambioMs} ms after the previous change`)
        cambiosDeClima.push(segundo)
      }
      ultimoCambioMs = ahoraMs
    }
    estado = siguiente
  }
  assert.ok(cambiosDeClima.length >= 4, `weather-to-weather changes: ${cambiosDeClima.join(', ')}`)
})
