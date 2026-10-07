import { test } from 'node:test'
import assert from 'node:assert/strict'
import { AR_CITIES } from '../src/lib/cities-ar.ts'
import {
  ZONAS_ALERTAS,
  distanciaKm,
  slugDeCiudad,
  zonaMasCercana,
  zonaPorSlug,
} from '../src/lib/alertas/zonaSugerida.ts'

// El `slug` es la clave que viaja al backend (`zona` en POST /api/alertas/suscripcion). Tiene que
// ser idéntico al `_slug` de apps/backend/app/services/alertas/zonas.py: si difiere, el backend
// responde 422 para esa ciudad. Los casos fijos de abajo se confirmaron contra ese `_slug`.

const PATRON_SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/

// ── slug ─────────────────────────────────────────────────────────────────────

test('slugDeCiudad: minúsculas, sin tildes, con guiones (casos confirmados contra el backend)', () => {
  const esperados: Array<[string, string]> = [
    ['Buenos Aires', 'buenos-aires'],
    ['Córdoba', 'cordoba'],
    ['Tucumán', 'tucuman'],
    ['Neuquén', 'neuquen'],
    ['Bahía Blanca', 'bahia-blanca'],
    ['Paraná', 'parana'],
    ['Río Gallegos', 'rio-gallegos'],
    ['Junín', 'junin'],
    ['Morón', 'moron'],
    ['Lanús', 'lanus'],
    ['San Salvador de Jujuy', 'san-salvador-de-jujuy'],
    ['Santiago del Estero', 'santiago-del-estero'],
    ['Malargüe', 'malargue'],
  ]
  for (const [nombre, slug] of esperados) {
    assert.equal(slugDeCiudad(nombre), slug, nombre)
  }
})

test('slugDeCiudad: la ñ y la ü pierden la marca, no la letra', () => {
  assert.equal(slugDeCiudad('Ñandú'), 'nandu')
  assert.equal(slugDeCiudad('Güemes'), 'guemes')
  assert.equal(slugDeCiudad('Malargüe'), 'malargue')
})

test('slugDeCiudad: separadores raros se colapsan y los bordes se recortan', () => {
  assert.equal(slugDeCiudad('  Zárate!! '), 'zarate')
  assert.equal(slugDeCiudad('a--b'), 'a-b')
  assert.equal(slugDeCiudad('x_y'), 'x-y')
  assert.equal(slugDeCiudad(''), '')
})

test('slugDeCiudad: un carácter que no es ASCII ni se descompone se descarta, como el backend', () => {
  // `encode("ascii", "ignore")` del backend los tira antes de separar por guiones.
  assert.equal(slugDeCiudad('Straße'), 'strae')
  assert.equal(slugDeCiudad('日本'), '')
})

// ── Las 50 zonas ─────────────────────────────────────────────────────────────

test('ZONAS_ALERTAS: una zona por ciudad de AR_CITIES, en el mismo orden', () => {
  assert.equal(AR_CITIES.length, 50)
  assert.equal(ZONAS_ALERTAS.length, AR_CITIES.length)
  ZONAS_ALERTAS.forEach((zona, i) => {
    assert.equal(zona.nombre, AR_CITIES[i].name)
    assert.equal(zona.provincia, AR_CITIES[i].province)
    assert.equal(zona.slug, slugDeCiudad(AR_CITIES[i].name))
  })
})

test('ZONAS_ALERTAS: los 50 slugs son únicos y bien formados', () => {
  const slugs = ZONAS_ALERTAS.map((z) => z.slug)
  assert.equal(new Set(slugs).size, slugs.length)
  for (const slug of slugs) {
    assert.match(slug, PATRON_SLUG, slug)
  }
})

test('zonaPorSlug: devuelve la zona de un slug conocido y null para el resto', () => {
  assert.deepEqual(zonaPorSlug('cordoba'), { slug: 'cordoba', nombre: 'Córdoba', provincia: 'Córdoba' })
  assert.equal(zonaPorSlug('malargue')?.nombre, 'Malargüe')
  assert.equal(zonaPorSlug('atlantida'), null)
  assert.equal(zonaPorSlug(''), null)
  assert.equal(zonaPorSlug('Cordoba'), null)
})

test('zonaPorSlug: las claves del prototipo no son slugs', () => {
  assert.equal(zonaPorSlug('constructor'), null)
  assert.equal(zonaPorSlug('__proto__'), null)
  assert.equal(zonaPorSlug('toString'), null)
  assert.equal(zonaPorSlug(undefined as unknown as string), null)
})

// ── Distancia ────────────────────────────────────────────────────────────────

test('distanciaKm: Buenos Aires a Córdoba ronda 646 km (haversine, radio 6371 km)', () => {
  const km = distanciaKm({ lat: -34.6037, lon: -58.3816 }, { lat: -31.4135, lon: -64.181 })
  assert.ok(Math.abs(km - 646.55) < 0.5, `distancia ${km}`)
})

test('distanciaKm: un grado de latitud son unos 111,2 km, el mismo punto es 0 y es simétrica', () => {
  assert.ok(Math.abs(distanciaKm({ lat: 0, lon: 0 }, { lat: 1, lon: 0 }) - 111.19) < 0.05)
  const a = { lat: -34.6037, lon: -58.3816 }
  const b = { lat: -54.8, lon: -68.3 }
  assert.equal(distanciaKm(a, a), 0)
  assert.equal(distanciaKm(a, b), distanciaKm(b, a))
})

// ── Zona sugerida ────────────────────────────────────────────────────────────

test('zonaMasCercana: un punto en Córdoba sugiere Córdoba con la distancia en km', () => {
  const zona = zonaMasCercana({ lat: -31.42, lon: -64.19, source: 'gps' })
  assert.ok(zona)
  assert.equal(zona.slug, 'cordoba')
  assert.equal(zona.nombre, 'Córdoba')
  assert.equal(zona.provincia, 'Córdoba')
  assert.ok(zona.distanciaKm < 2, `distancia ${zona.distanciaKm}`)
})

test('zonaMasCercana: elige la ciudad más cercana aunque no sea la de la provincia (Malargüe)', () => {
  const zona = zonaMasCercana({ lat: -35.5, lon: -69.6, source: 'gps' })
  assert.equal(zona?.slug, 'malargue')
})

test('zonaMasCercana: acepta ciudad elegida, GPS y una entrada vieja sin source', () => {
  assert.equal(zonaMasCercana({ lat: -32.9, lon: -68.85, source: 'city' })?.slug, 'mendoza')
  assert.equal(zonaMasCercana({ lat: -32.9, lon: -68.85, source: 'gps' })?.slug, 'mendoza')
  assert.equal(zonaMasCercana({ lat: -32.9, lon: -68.85 })?.slug, 'mendoza')
})

test('zonaMasCercana: con la ubicación por defecto (source fallback) no sugiere nada', () => {
  // Buenos Aires por defecto no es la ubicación de la persona: sugerirla sería adivinar.
  assert.equal(zonaMasCercana({ lat: -34.6037, lon: -58.3816, source: 'fallback' }), null)
  assert.equal(zonaMasCercana({ lat: -31.42, lon: -64.19, source: 'fallback' }), null)
})

test('zonaMasCercana: coordenadas que no son números finitos o están fuera de rango no sugieren nada', () => {
  const malas: Array<{ lat: unknown; lon: unknown }> = [
    { lat: Number.NaN, lon: -64 },
    { lat: -31, lon: Number.POSITIVE_INFINITY },
    { lat: Number.NEGATIVE_INFINITY, lon: -64 },
    { lat: 91, lon: -64 },
    { lat: -91, lon: -64 },
    { lat: -31, lon: 181 },
    { lat: -31, lon: -181 },
    { lat: '-31.4', lon: -64.2 },
    { lat: null, lon: -64 },
    { lat: undefined, lon: undefined },
  ]
  for (const mala of malas) {
    const ubicacion = { ...mala, source: 'gps' } as unknown as Parameters<typeof zonaMasCercana>[0]
    assert.equal(zonaMasCercana(ubicacion), null, JSON.stringify(mala))
  }
})

test('zonaMasCercana: los extremos válidos de lat/lon no se rechazan', () => {
  assert.ok(zonaMasCercana({ lat: -90, lon: 180, source: 'gps' }))
  assert.ok(zonaMasCercana({ lat: 90, lon: -180, source: 'gps' }))
})

test('zonaMasCercana: sin ciudades no sugiere nada', () => {
  assert.equal(zonaMasCercana({ lat: -31.42, lon: -64.19, source: 'gps' }, []), null)
})

test('zonaMasCercana: con un empate gana la primera de la lista', () => {
  const ciudades = [
    { name: 'Primera', province: 'A', lat: -30, lon: -60 },
    { name: 'Segunda', province: 'B', lat: -30, lon: -60 },
  ]
  const zona = zonaMasCercana({ lat: -30, lon: -60, source: 'city' }, ciudades)
  assert.equal(zona?.slug, 'primera')
  assert.equal(zona?.distanciaKm, 0)
})

test('zonaMasCercana: no modifica la lista de ciudades que recibe', () => {
  const ciudades = Object.freeze([
    Object.freeze({ name: 'Lejos', province: 'A', lat: -50, lon: -70 }),
    Object.freeze({ name: 'Cerca', province: 'B', lat: -30, lon: -60 }),
  ])
  const zona = zonaMasCercana({ lat: -30.1, lon: -60.1, source: 'city' }, ciudades)
  assert.equal(zona?.slug, 'cerca')
  assert.equal(ciudades.length, 2)
})
