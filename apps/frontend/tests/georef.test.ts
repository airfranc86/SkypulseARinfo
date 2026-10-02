import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildGeorefUrl,
  dedupePlaces,
  GEOREF_COORD_DECIMALS,
  GEOREF_DEFAULT_MAX,
  GEOREF_MAX_QUERY_LENGTH,
  GEOREF_MAX_RESULTS,
  GEOREF_MAX_ROWS,
  GEOREF_MAX_TEXT_LENGTH,
  GEOREF_MIN_QUERY_LENGTH,
  isSearchableQuery,
  isWithinBounds,
  mergeResults,
  normalizeGeorefQuery,
  parseGeorefResponse,
  placeDetail,
  placeKey,
  placeLabel,
  processGeorefResponse,
  rankPlaces,
  searchHint,
  type Place,
  type SearchHintInput,
} from '../src/lib/georef.ts'
import type { City } from '../src/lib/cities-ar.ts'

// ── Helpers ──────────────────────────────────────────────────────────────────

const place = (
  name: string,
  province: string,
  department: string | null,
  lat = -31.4,
  lon = -64.2,
): Place => ({ name, province, department, lat, lon })

const city = (name: string, province: string, lat = -31.4, lon = -64.2): City => ({
  name,
  province,
  lat,
  lon,
})

const row = (overrides: Record<string, unknown> = {}): Record<string, unknown> => ({
  id: '1',
  nombre: 'Villa General Belgrano',
  provincia: { nombre: 'Córdoba' },
  departamento: { nombre: 'Calamuchita' },
  centroide: { lat: -31.9788, lon: -64.5584 },
  ...overrides,
})

/** Forma real de la respuesta de Georef AR (/localidades). */
const REAL_PAYLOAD = {
  cantidad: 3,
  inicio: 0,
  total: 3,
  parametros: {
    campos: ['provincia.nombre', 'departamento.nombre', 'id', 'nombre', 'centroide.lat', 'centroide.lon'],
    max: 8,
    nombre: 'villa general',
    orden: 'nombre',
  },
  localidades: [
    {
      centroide: { lat: -31.97881, lon: -64.55844 },
      departamento: { nombre: 'Calamuchita' },
      id: '14028010000',
      nombre: 'Villa General Belgrano',
      provincia: { nombre: 'Córdoba' },
    },
    {
      centroide: { lat: -26.8519448937972, lon: -65.71069016081 },
      departamento: { nombre: 'Tafí del Valle' },
      id: '90098040',
      nombre: 'Tafí del Valle',
      provincia: { nombre: 'Tucumán' },
    },
    {
      centroide: { lat: -34.6, lon: -58.4 },
      departamento: null,
      id: '2',
      nombre: 'Sin Departamento',
      provincia: { nombre: 'Buenos Aires' },
    },
  ],
}

// ── buildGeorefUrl / query ───────────────────────────────────────────────────

test('buildGeorefUrl: apunta al endpoint de localidades con los campos pedidos', () => {
  const url = new URL(buildGeorefUrl('Tafi del Valle', 8))
  assert.equal(`${url.origin}${url.pathname}`, 'https://apis.datos.gob.ar/georef/api/localidades')
  assert.equal(url.searchParams.get('nombre'), 'Tafi del Valle')
  assert.equal(url.searchParams.get('max'), '8')
  assert.equal(url.searchParams.get('campos'), 'nombre,provincia.nombre,departamento.nombre,centroide')
  assert.equal(url.searchParams.get('orden'), 'nombre')
})

test('buildGeorefUrl: codifica espacios, tildes, & y # (sin partir la query)', () => {
  const raw = buildGeorefUrl('Tafí & Valle #1', 8)
  assert.ok(!raw.includes(' '), 'sin espacios crudos')
  assert.ok(!raw.includes('#'), 'sin fragmento crudo')
  assert.ok(raw.includes('%C3%AD'), 'la í va en UTF-8 percent-encoded')
  assert.ok(raw.includes('%26'), 'el & va codificado')
  assert.ok(raw.includes('%23'), 'el # va codificado')
  const url = new URL(raw)
  assert.equal(url.hash, '')
  assert.equal(url.searchParams.get('nombre'), 'Tafí & Valle #1')
  assert.equal([...url.searchParams.keys()].length, 4)
})

test('buildGeorefUrl: una entrada larguísima se trunca al máximo', () => {
  const url = new URL(buildGeorefUrl('a'.repeat(5000), 8))
  assert.equal(url.searchParams.get('nombre')?.length, GEOREF_MAX_QUERY_LENGTH)
})

test('buildGeorefUrl: recorta y colapsa espacios', () => {
  const url = new URL(buildGeorefUrl('  villa    general  ', 8))
  assert.equal(url.searchParams.get('nombre'), 'villa general')
})

test('buildGeorefUrl: max se limita a [1, GEOREF_MAX_RESULTS] y es entero', () => {
  const maxOf = (n: number) => new URL(buildGeorefUrl('villa', n)).searchParams.get('max')
  assert.equal(maxOf(0), '1')
  assert.equal(maxOf(-5), '1')
  assert.equal(maxOf(10_000), String(GEOREF_MAX_RESULTS))
  assert.equal(maxOf(7.9), '7')
  assert.equal(maxOf(Number.NaN), String(GEOREF_DEFAULT_MAX))
  assert.equal(maxOf(Number.POSITIVE_INFINITY), String(GEOREF_DEFAULT_MAX))
})

test('normalizeGeorefQuery: minúsculas, sin tildes, espacios colapsados, truncada', () => {
  assert.equal(normalizeGeorefQuery('  TAFÍ   del Valle '), 'tafi del valle')
  assert.equal(normalizeGeorefQuery('ñandú').length, 5)
  assert.equal(normalizeGeorefQuery('x'.repeat(1000)).length, GEOREF_MAX_QUERY_LENGTH)
})

test('isSearchableQuery: desde 3 caracteres y con al menos una letra o dígito', () => {
  assert.equal(isSearchableQuery('vil'), true)
  assert.equal(isSearchableQuery(' vil '), true)
  assert.equal(isSearchableQuery('vi'), false)
  assert.equal(isSearchableQuery('   '), false)
  assert.equal(isSearchableQuery('...'), false)
  assert.equal(isSearchableQuery('-- !!'), false)
  assert.equal(isSearchableQuery('  v  '), false)
  assert.equal(isSearchableQuery('ñan'), true)
  assert.equal(isSearchableQuery('a1'), false)
  assert.equal(isSearchableQuery('9 de'), true)
})

// ── Límites de coordenadas ───────────────────────────────────────────────────

test('isWithinBounds: mismos límites que LatParam/LonParam del backend (inclusivos)', () => {
  assert.equal(isWithinBounds(-34.6, -58.4), true)
  assert.equal(isWithinBounds(-55, -74), true)
  assert.equal(isWithinBounds(-21, -53), true)
  assert.equal(isWithinBounds(-55.01, -60), false)
  assert.equal(isWithinBounds(-20.99, -60), false)
  assert.equal(isWithinBounds(-30, -74.01), false)
  assert.equal(isWithinBounds(-30, -52.99), false)
  assert.equal(isWithinBounds(Number.NaN, -60), false)
  assert.equal(isWithinBounds(-30, Number.POSITIVE_INFINITY), false)
})

// ── parseGeorefResponse ──────────────────────────────────────────────────────

test('parseGeorefResponse: payload real (Villa General Belgrano, Tafí del Valle, sin departamento)', () => {
  const places = parseGeorefResponse(REAL_PAYLOAD)
  assert.equal(places.length, 3)
  assert.deepEqual(places[0], {
    name: 'Villa General Belgrano',
    province: 'Córdoba',
    department: 'Calamuchita',
    lat: -31.9788,
    lon: -64.5584,
  })
  assert.equal(places[1].name, 'Tafí del Valle')
  assert.equal(places[1].province, 'Tucumán')
  assert.equal(places[1].department, 'Tafí del Valle')
  assert.equal(places[2].department, null)
})

test('parseGeorefResponse: redondea lat/lon a GEOREF_COORD_DECIMALS (4) decimales', () => {
  const [p] = parseGeorefResponse({
    localidades: [row({ centroide: { lat: -31.9764928137116, lon: -64.5584431257481 } })],
  })
  assert.equal(GEOREF_COORD_DECIMALS, 4)
  assert.equal(p.lat, -31.9765)
  assert.equal(p.lon, -64.5584)
})

test('parseGeorefResponse: la validación de límites usa el valor ya redondeado', () => {
  const at = (lat: number, lon: number) => parseGeorefResponse({ localidades: [row({ centroide: { lat, lon } })] })
  // -55.00004 redondea a -55 (válido para el backend); -55.00006 redondea a -55.0001 (fuera).
  assert.equal(at(-55.00004, -60)[0]?.lat, -55)
  assert.equal(at(-55.00006, -60).length, 0)
  assert.equal(at(-21.00004, -60)[0]?.lat, -21)
  assert.equal(at(-21 + 0.00006, -60).length, 0)
  assert.equal(at(-30, -74.00004)[0]?.lon, -74)
  assert.equal(at(-30, -52.99996)[0]?.lon, -53)
  assert.equal(at(-30, -53 + 0.00006).length, 0)
})

test('parseGeorefResponse + dedupePlaces: el redondeo no rompe la deduplicación por cercanía', () => {
  const places = parseGeorefResponse({
    localidades: [
      row({ nombre: 'Sarmiento', departamento: { nombre: 'A' }, centroide: { lat: -45.59001234567, lon: -69.07001234567 } }),
      row({ nombre: 'Sarmiento', departamento: { nombre: 'B' }, centroide: { lat: -45.59499999999, lon: -69.07400000001 } }),
      row({ nombre: 'Sarmiento', departamento: { nombre: 'C' }, centroide: { lat: -45.7, lon: -69.2 } }),
    ],
  })
  assert.equal(dedupePlaces(places).length, 2)
})

test('parseGeorefResponse: los resultados son inmutables y no comparten referencias con la entrada', () => {
  const places = parseGeorefResponse(REAL_PAYLOAD)
  assert.ok(Object.isFrozen(places))
  assert.ok(Object.isFrozen(places[0]))
  assert.throws(() => {
    ;(places[0] as { name: string }).name = 'x'
  }, TypeError)
})

test('parseGeorefResponse: payloads que no son la forma esperada devuelven [] sin lanzar', () => {
  const garbage: unknown[] = [
    null,
    undefined,
    'texto',
    42,
    true,
    [],
    {},
    { localidades: null },
    { localidades: 'x' },
    { localidades: {} },
    { localidades: [] },
    { error: 'bad request' },
  ]
  for (const payload of garbage) {
    assert.deepEqual(parseGeorefResponse(payload), [], `payload: ${JSON.stringify(payload)}`)
  }
})

test('parseGeorefResponse: descarta filas malformadas y conserva las válidas', () => {
  const bad: unknown[] = [
    null,
    'x',
    7,
    [],
    row({ nombre: undefined }),
    row({ nombre: 123 }),
    row({ nombre: '   ' }),
    row({ provincia: undefined }),
    row({ provincia: null }),
    row({ provincia: { nombre: 5 } }),
    row({ provincia: { nombre: '' } }),
    row({ centroide: undefined }),
    row({ centroide: null }),
    row({ centroide: {} }),
    row({ centroide: { lat: -31.9 } }),
    row({ centroide: { lat: '-31.9', lon: '-64.5' } }),
    row({ centroide: { lat: Number.NaN, lon: -64.5 } }),
    row({ centroide: { lat: -31.9, lon: Number.POSITIVE_INFINITY } }),
    row({ centroide: { lat: Number.NEGATIVE_INFINITY, lon: -64.5 } }),
    row({ centroide: { lat: null, lon: null } }),
    row({ centroide: { lat: 0, lon: 0 } }),
    row({ centroide: { lat: -31.9, lon: -100 } }),
    row({ centroide: { lat: -60, lon: -64.5 } }),
    row({ centroide: { lat: 40.4, lon: -3.7 } }),
  ]
  const good = row({ nombre: 'Válida' })
  const places = parseGeorefResponse({ localidades: [...bad, good] })
  assert.equal(places.length, 1)
  assert.equal(places[0].name, 'Válida')
})

test('parseGeorefResponse: departamento inválido se vuelve null, la fila se conserva', () => {
  for (const departamento of [undefined, null, 'Capital', 7, {}, { nombre: 3 }, { nombre: '  ' }, []]) {
    const places = parseGeorefResponse({ localidades: [row({ departamento })] })
    assert.equal(places.length, 1)
    assert.equal(places[0].department, null)
  }
})

test('parseGeorefResponse: campos extra se ignoran (no se filtran al resultado)', () => {
  const places = parseGeorefResponse({
    localidades: [row({ __proto__: { polluted: 1 }, extra: { a: 1 }, id: { x: 1 } })],
  })
  assert.equal(places.length, 1)
  assert.deepEqual(Object.keys(places[0]).sort(), ['department', 'lat', 'lon', 'name', 'province'])
})

test('parseGeorefResponse: arreglos enormes se limitan a GEOREF_MAX_ROWS', () => {
  const localidades = Array.from({ length: GEOREF_MAX_ROWS * 10 }, (_, i) => row({ nombre: `Lugar ${i}` }))
  const places = parseGeorefResponse({ localidades })
  assert.equal(places.length, GEOREF_MAX_ROWS)
  assert.equal(places[0].name, 'Lugar 0')
})

test('parseGeorefResponse: textos larguísimos se recortan a GEOREF_MAX_TEXT_LENGTH', () => {
  const long = 'z'.repeat(GEOREF_MAX_TEXT_LENGTH * 5)
  const [p] = parseGeorefResponse({
    localidades: [row({ nombre: long, provincia: { nombre: long }, departamento: { nombre: long } })],
  })
  assert.equal(p.name.length, GEOREF_MAX_TEXT_LENGTH)
  assert.equal(p.province.length, GEOREF_MAX_TEXT_LENGTH)
  assert.equal(p.department?.length, GEOREF_MAX_TEXT_LENGTH)
})

test('parseGeorefResponse: recorta espacios de los textos', () => {
  const [p] = parseGeorefResponse({ localidades: [row({ nombre: '  Tafí Viejo  ' })] })
  assert.equal(p.name, 'Tafí Viejo')
})

// ── dedupePlaces ─────────────────────────────────────────────────────────────

test('dedupePlaces: las dos "Córdoba" idénticas de Capital quedan en una', () => {
  const dup = [
    place('Córdoba', 'Córdoba', 'Capital', -31.4135, -64.181),
    place('Córdoba', 'Córdoba', 'Capital', -31.4135, -64.181),
  ]
  const out = dedupePlaces(dup)
  assert.equal(out.length, 1)
  assert.equal(out[0], dup[0])
})

test('dedupePlaces: mismo nombre+provincia+departamento es duplicado aunque cambien las coordenadas', () => {
  const out = dedupePlaces([
    place('Villa Ana', 'Santa Fe', 'Vera', -29.5, -59.6),
    place('villa ana', 'santa fe', 'vera', -28.9, -60.1),
  ])
  assert.equal(out.length, 1)
})

test('dedupePlaces: mismo nombre+provincia con coordenadas a menos de ~0,01° es duplicado', () => {
  const out = dedupePlaces([
    place('Sarmiento', 'Chubut', 'Sarmiento', -45.59, -69.07),
    place('Sarmiento', 'Chubut', null, -45.595, -69.074),
  ])
  assert.equal(out.length, 1)
})

test('dedupePlaces: homónimos en distinto departamento y lejos se conservan', () => {
  const homonyms = [
    place('San Martín', 'Mendoza', 'San Martín', -33.08, -68.47),
    place('San Martín', 'Mendoza', 'Capital', -32.9, -68.8),
    place('San Martín', 'Buenos Aires', 'General San Martín', -34.57, -58.54),
    place('San Martín', 'Salta', 'General San Martín', -23.2, -63.8),
  ]
  assert.equal(dedupePlaces(homonyms).length, 4)
})

test('dedupePlaces: no muta la entrada, conserva el orden y la primera aparición', () => {
  const input = Object.freeze([
    place('B', 'P', 'd1', -30, -60),
    place('A', 'P', 'd1', -31, -61),
    place('B', 'P', 'd1', -30, -60),
  ])
  const out = dedupePlaces(input)
  assert.deepEqual(
    out.map((p) => p.name),
    ['B', 'A'],
  )
  assert.equal(input.length, 3)
})

// ── rankPlaces ───────────────────────────────────────────────────────────────

test('rankPlaces: exacto > prefijo > prefijo de palabra > contiene > resto', () => {
  const input = [
    place('Atafisal', 'X', null),
    place('Villa Tafí', 'X', null),
    place('Tafí Viejo', 'X', null),
    place('Otro Lugar', 'X', null),
    place('Tafí', 'X', null),
  ]
  const names = rankPlaces(input, 'tafi').map((p) => p.name)
  assert.deepEqual(names, ['Tafí', 'Tafí Viejo', 'Villa Tafí', 'Atafisal', 'Otro Lugar'])
})

test('rankPlaces: ignora tildes y mayúsculas en consulta y nombre', () => {
  const input = [place('Tucumán Sur', 'X', null), place('TUCUMAN', 'X', null)]
  assert.deepEqual(
    rankPlaces(input, 'TUCUMÁN').map((p) => p.name),
    ['TUCUMAN', 'Tucumán Sur'],
  )
})

test('rankPlaces: es estable entre empates y no muta la entrada', () => {
  const input = Object.freeze([
    place('Tafí del Valle', 'Tucumán', 'Tafí del Valle'),
    place('Tafí Viejo', 'Tucumán', 'Tafí Viejo'),
    place('Tafí Nuevo', 'Tucumán', 'Otro'),
  ])
  const out = rankPlaces(input, 'tafi')
  assert.deepEqual(
    out.map((p) => p.name),
    ['Tafí del Valle', 'Tafí Viejo', 'Tafí Nuevo'],
  )
  assert.equal(input[0].name, 'Tafí del Valle')
})

test('rankPlaces: "tafi del valle" pone primero al exacto y "villa gral" mantiene a los que no calzan', () => {
  const input = [
    place('Tafí del Valle Norte', 'T', null),
    place('Tafí del Valle', 'T', 'Tafí del Valle'),
  ]
  assert.equal(rankPlaces(input, 'tafi del valle')[0].name, 'Tafí del Valle')
  const gral = [place('Villa General Belgrano', 'C', 'Calamuchita')]
  assert.equal(rankPlaces(gral, 'villa gral').length, 1)
})

test('rankPlaces: con consulta vacía devuelve el mismo orden', () => {
  const input = [place('B', 'P', null), place('A', 'P', null)]
  assert.deepEqual(
    rankPlaces(input, '  ').map((p) => p.name),
    ['B', 'A'],
  )
})

// ── placeKey / placeDetail / placeLabel ──────────────────────────────────────

test('placeKey: distingue homónimos por departamento y coordenadas', () => {
  const a = place('San Martín', 'Mendoza', 'San Martín', -33.08, -68.47)
  const b = place('San Martín', 'Mendoza', 'Capital', -33.08, -68.47)
  const c = place('San Martín', 'Mendoza', 'San Martín', -32.5, -68.47)
  const keys = new Set([placeKey(a), placeKey(b), placeKey(c)])
  assert.equal(keys.size, 3)
  assert.equal(placeKey(a), placeKey({ ...a }))
})

test('placeKey: una City local (sin departamento) también tiene clave', () => {
  const c = city('Rosario', 'Santa Fe', -32.9587, -60.6931)
  assert.equal(typeof placeKey(c), 'string')
  assert.notEqual(placeKey(c), placeKey({ ...c, department: 'Rosario' }))
})

test('placeLabel / placeDetail: "Localidad · Departamento, Provincia"', () => {
  const p = place('Villa General Belgrano', 'Córdoba', 'Calamuchita')
  assert.equal(placeLabel(p), 'Villa General Belgrano · Calamuchita, Córdoba')
  assert.equal(placeDetail(p), 'Calamuchita, Córdoba')
})

test('placeLabel: omite el departamento si es null, vacío o igual al nombre', () => {
  assert.equal(placeLabel(place('Tafí', 'Tucumán', null)), 'Tafí · Tucumán')
  assert.equal(placeLabel(place('Tafí', 'Tucumán', '')), 'Tafí · Tucumán')
  assert.equal(placeLabel(place('Rosario', 'Santa Fe', 'Rosario')), 'Rosario · Santa Fe')
  assert.equal(placeLabel(place('Rosario', 'Santa Fe', 'ROSARIO')), 'Rosario · Santa Fe')
  assert.equal(placeDetail(place('Rosario', 'Santa Fe', 'Rosário')), 'Santa Fe')
})

test('placeLabel: acepta una City local', () => {
  assert.equal(placeLabel(city('Salta', 'Salta')), 'Salta · Salta')
  assert.equal(placeDetail(city('Salta', 'Salta')), 'Salta')
  assert.equal(placeDetail({ ...city('Mendoza', 'Mendoza'), department: 'Capital' }), 'Capital, Mendoza')
})

// ── mergeResults ─────────────────────────────────────────────────────────────

test('mergeResults: primero las locales, después las remotas, con forma City', () => {
  const local = [city('Córdoba', 'Córdoba', -31.4135, -64.181)]
  const remote = [place('Villa General Belgrano', 'Córdoba', 'Calamuchita', -31.9788, -64.5584)]
  const out = mergeResults(local, remote, 8)
  assert.equal(out.length, 2)
  assert.equal(out[0], local[0])
  assert.deepEqual(out[1], {
    name: 'Villa General Belgrano',
    province: 'Córdoba',
    department: 'Calamuchita',
    lat: -31.9788,
    lon: -64.5584,
  })
})

test('mergeResults: una remota sin departamento no agrega la clave department', () => {
  const [c] = mergeResults([], [place('Tafí', 'Tucumán', null, -26.8, -65.7)], 8)
  assert.equal('department' in c, false)
})

test('mergeResults: descarta remotas que duplican una local (mismo nombre + provincia, sin tildes ni mayúsculas)', () => {
  const local = [city('Córdoba', 'Córdoba', -31.4135, -64.181), city('Tucumán', 'Tucumán')]
  const remote = [
    place('CORDOBA', 'cordoba', 'Capital', -31.4, -64.18),
    place('Córdoba', 'Córdoba', 'Capital', -31.4, -64.18),
    place('Córdoba', 'Entre Ríos', 'X', -32, -58),
    place('Tucuman', 'Tucumán', 'Capital', -26.8, -65.2),
  ]
  const out = mergeResults(local, remote, 8)
  assert.deepEqual(
    out.map((c) => `${c.name}|${c.province}`),
    ['Córdoba|Córdoba', 'Tucumán|Tucumán', 'Córdoba|Entre Ríos'],
  )
})

test('mergeResults: descarta una remota con el mismo nombre y coordenadas casi iguales a una local aunque cambie la provincia', () => {
  const local = [city('Buenos Aires', 'CABA', -34.6037, -58.3816)]
  const remote = [place('Buenos Aires', 'Ciudad Autónoma de Buenos Aires', null, -34.61, -58.39)]
  assert.equal(mergeResults(local, remote, 8).length, 1)
})

test('mergeResults: respeta el límite total', () => {
  const local = Array.from({ length: 3 }, (_, i) => city(`L${i}`, 'P'))
  const remote = Array.from({ length: 20 }, (_, i) => place(`R${i}`, 'P', `d${i}`, -30 - i * 0.1, -60))
  const out = mergeResults(local, remote, 8)
  assert.equal(out.length, 8)
  assert.deepEqual(
    out.slice(0, 3).map((c) => c.name),
    ['L0', 'L1', 'L2'],
  )
  assert.equal(out[3].name, 'R0')
})

test('mergeResults: si las locales ya llenan el límite, no entra ninguna remota', () => {
  const local = Array.from({ length: 10 }, (_, i) => city(`L${i}`, 'P'))
  const out = mergeResults(local, [place('R', 'P', null)], 8)
  assert.equal(out.length, 8)
  assert.ok(out.every((c) => c.name.startsWith('L')))
})

test('mergeResults: límite no positivo o inválido devuelve []; sin remotas devuelve las locales', () => {
  const local = [city('A', 'P')]
  assert.deepEqual(mergeResults(local, [place('B', 'P', null)], 0), [])
  assert.deepEqual(mergeResults(local, [place('B', 'P', null)], Number.NaN), [])
  assert.deepEqual(mergeResults(local, [], 8), local)
  assert.deepEqual(mergeResults([], [], 8), [])
})

test('mergeResults: no muta las entradas', () => {
  const local = Object.freeze([city('A', 'P')])
  const remote = Object.freeze([place('B', 'P', 'd')])
  const out = mergeResults(local, remote, 8)
  assert.equal(local.length, 1)
  assert.equal(remote.length, 1)
  assert.notEqual(out, local)
})

// ── processGeorefResponse ────────────────────────────────────────────────────

test('processGeorefResponse: parsea, deduplica y ordena por relevancia', () => {
  const payload = {
    localidades: [
      row({ nombre: 'Villa Tafí', provincia: { nombre: 'Tucumán' }, departamento: { nombre: 'A' }, centroide: { lat: -26.8, lon: -65.7 } }),
      row({ nombre: 'Tafí Viejo', provincia: { nombre: 'Tucumán' }, departamento: { nombre: 'Tafí Viejo' }, centroide: { lat: -26.73, lon: -65.26 } }),
      row({ nombre: 'Tafí Viejo', provincia: { nombre: 'Tucumán' }, departamento: { nombre: 'Tafí Viejo' }, centroide: { lat: -26.73, lon: -65.26 } }),
      row({ nombre: 'Tafí', provincia: { nombre: 'Tucumán' }, departamento: null, centroide: { lat: -26.9, lon: -65.5 } }),
      row({ nombre: 'Rota', centroide: { lat: 'x', lon: 1 } }),
    ],
  }
  const out = processGeorefResponse(payload, 'tafi')
  assert.deepEqual(
    out.map((p) => p.name),
    ['Tafí', 'Tafí Viejo', 'Villa Tafí'],
  )
})

test('processGeorefResponse: un payload basura devuelve []', () => {
  assert.deepEqual(processGeorefResponse({ nope: 1 }, 'tafi'), [])
  assert.deepEqual(processGeorefResponse(null, 'tafi'), [])
})

// ── searchHint ───────────────────────────────────────────────────────────────

const HINT_BASE: SearchHintInput = {
  dismissed: false,
  isSearching: false,
  remoteFailed: false,
  queryLength: 12,
  resultCount: 0,
}
const hint = (overrides: Partial<SearchHintInput>) => searchHint({ ...HINT_BASE, ...overrides })

test('searchHint: búsqueda exitosa sin resultados dice "not_found"', () => {
  assert.equal(hint({}), 'not_found')
})

test('searchHint: si el servicio falló y no hay resultados, no afirma que no existe', () => {
  assert.equal(hint({ remoteFailed: true }), 'unavailable')
})

test('searchHint: con resultados locales y el servicio caído no muestra ningún texto', () => {
  assert.equal(hint({ remoteFailed: true, resultCount: 2 }), 'none')
  assert.equal(hint({ resultCount: 2 }), 'none')
})

test('searchHint: mientras busca, "searching" (aunque haya un fallo previo o ningún resultado)', () => {
  assert.equal(hint({ isSearching: true }), 'searching')
  assert.equal(hint({ isSearching: true, remoteFailed: true }), 'searching')
  assert.equal(hint({ isSearching: true, resultCount: 3 }), 'searching')
})

test('searchHint: descartado por el usuario o consulta corta no muestra texto', () => {
  assert.equal(hint({ dismissed: true, isSearching: true }), 'none')
  assert.equal(hint({ dismissed: true, remoteFailed: true }), 'none')
  assert.equal(hint({ queryLength: 2 }), 'none')
  assert.equal(hint({ queryLength: 2, remoteFailed: true }), 'none')
  assert.equal(hint({ queryLength: GEOREF_MIN_QUERY_LENGTH }), 'not_found')
})
