import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { CLOUDS } from '../src/data/clouds.ts'
import { CREDITOS_FOTOS, FOTOS_COMPARTIR_IGUAL, TEXTO_CAMBIOS, creditoDe, textoCredito } from '../src/lib/creditosFotos.ts'

// B10 (item 23): the 23 photos of /nubes and /desastres are hosted by the site and each one carries
// its credit. `lib/creditosFotos.ts` is the single source of truth for authors, licences and sources.

/** Source of a file under apps/frontend, line endings normalised so regexes do not care about CRLF. */
const read = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8').replace(/\r\n/g, '\n')

const MAX_BYTES = 350 * 1024

/** Ids of the Desastres cards: the `id` of every entry of the DISASTERS list (4 spaces of indent). */
function desastresIds(): string[] {
  return [...read('src/pages/Desastres.tsx').matchAll(/^ {4}id: '([^']+)',$/gm)].map(m => m[1])
}

/** `text-xs` as a class of its own: `sm:text-xs` would only apply from a breakpoint up and leave smaller text below it. */
const TEXT_XS = /(?<![:\w-])text-xs(?![\w-])/

/** The opening tag of the first element that carries `data-credito-foto`. */
function captionTag(source: string): string {
  const tag = source.match(/<[a-z]+\b[^>]*data-credito-foto[^>]*>/s)
  assert.ok(tag, 'the page renders an element marked data-credito-foto')
  return tag[0]
}

// ---------------------------------------------------------------------------
// The credit table
// ---------------------------------------------------------------------------

test('there are 23 credits with unique ids', () => {
  assert.equal(CREDITOS_FOTOS.length, 23)
  const ids = CREDITOS_FOTOS.map(c => c.id)
  assert.equal(new Set(ids).size, ids.length)
})

test('the credit ids are exactly the 13 clouds plus the 10 Desastres cards', () => {
  const expected = [...CLOUDS.map(c => c.id as string), ...desastresIds()].sort()
  assert.equal(desastresIds().length, 10)
  assert.deepEqual(CREDITOS_FOTOS.map(c => c.id).sort(), expected)
})

test('every credit names an author, a licence and a source', () => {
  for (const c of CREDITOS_FOTOS) {
    assert.ok(c.tema.trim().length > 0, `${c.id}: tema`)
    assert.ok(c.autor.trim().length > 0, `${c.id}: autor`)
    assert.ok(c.licencia.nombre.trim().length > 0, `${c.id}: licencia`)
    assert.ok(c.fuente.nombre.trim().length > 0, `${c.id}: fuente`)
    assert.equal(typeof c.redimensionada, 'boolean', `${c.id}: redimensionada`)
  }
})

test('every link is a valid https URL', () => {
  for (const c of CREDITOS_FOTOS) {
    for (const url of [c.fuente.url, c.licencia.url].filter((u): u is string => u !== undefined)) {
      assert.equal(new URL(url).protocol, 'https:', `${c.id}: ${url}`)
    }
  }
})

test('every Creative Commons licence links to its legal text, public domain needs no link', () => {
  for (const c of CREDITOS_FOTOS) {
    if (c.licencia.nombre.startsWith('CC')) {
      assert.ok(c.licencia.url, `${c.id}: ${c.licencia.nombre} needs a licence URL`)
      assert.equal(new URL(c.licencia.url).hostname, 'creativecommons.org', c.id)
    } else {
      assert.equal(c.licencia.url, undefined, `${c.id}: ${c.licencia.nombre} has no licence URL`)
    }
  }
})

test('the licence URL matches the licence name', () => {
  const casos: Array<[string, string]> = [
    ['CC0', 'https://creativecommons.org/publicdomain/zero/1.0/'],
    ['CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/'],
    ['CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0/'],
    ['CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'],
    ['CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0/'],
    ['CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/'],
    ['CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0/'],
  ]
  for (const [nombre, url] of casos) {
    const usan = CREDITOS_FOTOS.filter(c => c.licencia.nombre === nombre)
    for (const c of usan) assert.equal(c.licencia.url, url, c.id)
  }
  const nombres = new Set(CREDITOS_FOTOS.map(c => c.licencia.nombre))
  for (const n of nombres) assert.ok(n.startsWith('Dominio público') || casos.some(([c]) => c === n), `unknown licence ${n}`)
})

test('the resized photos say so, and the credit line carries author, licence and source', () => {
  for (const c of CREDITOS_FOTOS) {
    const texto = textoCredito(c)
    assert.ok(texto.includes(c.autor), `${c.id}: author in ${texto}`)
    assert.ok(texto.includes(c.licencia.nombre), `${c.id}: licence in ${texto}`)
    assert.ok(texto.includes(c.fuente.nombre), `${c.id}: source in ${texto}`)
    assert.ok(texto.includes(c.tema), `${c.id}: topic in ${texto}`)
    assert.equal(texto.includes('redimensionada'), c.redimensionada, `${c.id}: resized flag`)
  }
})

test('credit lines use no long dash', () => {
  for (const c of CREDITOS_FOTOS) assert.doesNotMatch(textoCredito(c), /[—–]/, c.id)
})

test('three sample credit lines', () => {
  assert.equal(
    textoCredito(creditoDe('cirros')),
    'Cirros: Dimitry B. (ru_boff), CC BY 2.0, Flickr, redimensionada y recortada',
  )
  assert.equal(textoCredito(creditoDe('mammatus')), 'Mammatus: Cbaile19, CC0, Wikimedia Commons')
  assert.equal(
    textoCredito(creditoDe('tornados')),
    'Tornado F5 en Elie, Manitoba (2007): Justin Hobson (Justin1569), CC BY-SA 3.0, Wikimedia Commons, redimensionada y recortada',
  )
})

test('Commons sources point at the File: page and keep parentheses and commas readable', () => {
  const commons = CREDITOS_FOTOS.filter(c => c.fuente.nombre === 'Wikimedia Commons')
  assert.equal(commons.length, 19)
  for (const c of commons) {
    assert.match(c.fuente.url, /^https:\/\/commons\.wikimedia\.org\/wiki\/File:[^\s]+$/, c.id)
  }
  assert.equal(
    creditoDe('estrato').fuente.url,
    'https://commons.wikimedia.org/wiki/File:Stratus_nebulosus_opacus_and_Stratus_fractus_(14122021).jpg',
  )
  assert.ok(creditoDe('cumulonimbo').fuente.url.includes('na_wsch%C3%B3d_od_Krakowa'))
  assert.ok(creditoDe('cumulonimbo').fuente.url.includes('Krakowa,_2025'))
})

// The owner replaced three photos (niebla, tornados, tsunamis): their credits and alt texts follow the new files.
test('the three replaced photos carry their new credits', () => {
  const niebla = creditoDe('niebla')
  assert.equal(niebla.autor, 'Jay Huang')
  assert.deepEqual(niebla.licencia, { nombre: 'CC BY 2.0', url: 'https://creativecommons.org/licenses/by/2.0/' })
  assert.equal(niebla.fuente.url, 'https://commons.wikimedia.org/wiki/File:Beautiful_sunrise_over_Pleasanton_valley.jpg')
  assert.equal(niebla.redimensionada, true)

  const tornados = creditoDe('tornados')
  assert.equal(tornados.tema, 'Tornado F5 en Elie, Manitoba (2007)')
  assert.equal(tornados.autor, 'Justin Hobson (Justin1569)')
  assert.deepEqual(tornados.licencia, { nombre: 'CC BY-SA 3.0', url: 'https://creativecommons.org/licenses/by-sa/3.0/' })
  assert.equal(tornados.fuente.url, 'https://commons.wikimedia.org/wiki/File:F5_tornado_Elie_Manitoba_2007.jpg')
  assert.equal(tornados.redimensionada, true)
  assert.doesNotMatch(textoCredito(tornados), /NOAA|NSSL/)

  const tsunamis = creditoDe('tsunamis')
  assert.equal(tsunamis.autor, 'Sofwathulla Mohamed')
  assert.deepEqual(tsunamis.licencia, { nombre: 'Dominio público (liberada por el autor)' })
  assert.equal(
    tsunamis.fuente.url,
    'https://commons.wikimedia.org/wiki/File:2004_Indian_Ocean_earthquake_Maldives_tsunami_wave.jpg',
  )
  assert.equal(tsunamis.redimensionada, false, 'the 400x300 original was not resized')
})

test('creditoDe fails loudly for an unknown id', () => {
  assert.throws(() => creditoDe('no-existe'))
})

// ---------------------------------------------------------------------------
// The files
// ---------------------------------------------------------------------------

test('each of the 23 photos exists in public/fotos and weighs under 350 KB', () => {
  for (const c of CREDITOS_FOTOS) {
    const file = new URL(`../public/fotos/${c.id}.webp`, import.meta.url)
    assert.ok(existsSync(file), `missing public/fotos/${c.id}.webp`)
    assert.ok(statSync(file).size < MAX_BYTES, `${c.id}.webp weighs ${statSync(file).size} bytes`)
  }
})

// ---------------------------------------------------------------------------
// The pages
// ---------------------------------------------------------------------------

test('every cloud photo is a local /fotos/<id>.webp path', () => {
  assert.equal(CLOUDS.length, 13)
  for (const cloud of CLOUDS) assert.equal(cloud.imgSrc, `/fotos/${cloud.id}.webp`)
})

test('clouds.ts has no external URL left on its image lines', () => {
  const lines = read('src/data/clouds.ts').split('\n').filter(l => /^ {4}imgSrc: '/.test(l))
  assert.equal(lines.length, 13)
  for (const line of lines) assert.doesNotMatch(line, /https?:\/\//, line)
})

test('every Desastres photo is a local /fotos/<id>.webp path', () => {
  const source = read('src/pages/Desastres.tsx')
  const ids = desastresIds()
  const imgs = [...source.matchAll(/^ {4}img: '([^']+)',$/gm)].map(m => m[1])
  assert.deepEqual(imgs, ids.map(id => `/fotos/${id}.webp`))
})

test('Nubes shows a credit caption under each photo, readable and with safe links', () => {
  const source = read('src/pages/Nubes.tsx')
  assert.match(source, /from '@\/lib\/creditosFotos'/)
  assert.match(source, /creditoDe\(cloud\.id\)/)
  assert.match(source, /rel="noopener noreferrer"/)
  assert.match(captionTag(source), TEXT_XS, 'caption text is at least 12 px (text-xs)')
  assert.match(source, /loading="lazy"/)
})

test('Desastres shows each card credit, readable and with safe links', () => {
  const source = read('src/pages/Desastres.tsx')
  assert.match(source, /from '@\/lib\/creditosFotos'/)
  assert.match(source, /creditoDe\(card\.id\)/)
  assert.match(source, /rel="noopener noreferrer"/)
  assert.match(captionTag(source), TEXT_XS, 'caption text is at least 12 px (text-xs)')
  assert.match(source, /loading="lazy"/)
})

test('DatosFuentes lists the 23 photo credits under a "Fotos" heading', () => {
  const source = read('src/pages/DatosFuentes.tsx')
  assert.match(source, /from '@\/lib\/creditosFotos'/)
  assert.match(source, />\s*Fotos\s*</)
  assert.match(source, /CREDITOS_FOTOS\.map\(/)
  assert.match(source, /rel="noopener noreferrer"/)
})

/** imgAlt of a Desastres card, found by its id. */
function desastreAlt(id: string): string {
  const m = read('src/pages/Desastres.tsx').match(new RegExp(`^ {4}id: '${id}',[^]*?^ {4}imgAlt: '([^']*)',`, 'm'))
  assert.ok(m, `Desastres card ${id} has an imgAlt`)
  return m[1]
}

test('the alt text of the replaced photos describes the new pictures', () => {
  const niebla = CLOUDS.find(c => c.id === 'niebla')?.imgAlt ?? ''
  assert.match(niebla, /niebla/i)
  assert.match(niebla, /valle/i)
  assert.match(niebla, /amanecer/i)
  assert.match(niebla, /naranja/i)

  const tornado = desastreAlt('tornados')
  assert.match(tornado, /embudo/i)
  assert.match(tornado, /tormenta/i)
  assert.match(tornado, /campo/i)

  const tsunami = desastreAlt('tsunamis')
  assert.match(tsunami, /muro costero/i) // la foto muestra una ola rompiendo contra un muro de la costa
  assert.doesNotMatch(tsunami, /calle|inundando/i)
  assert.match(tsunami, /Malé/)
  assert.match(tsunami, /2004/)

  for (const alt of [niebla, tornado, tsunami]) {
    assert.doesNotMatch(alt, /persona|gente|Ao Nang|playa|ciudad|Altus|Oklahoma/i, alt)
  }
})

test('the self-hosted photos no longer ask the browser to hide the referrer', () => {
  assert.doesNotMatch(read('src/pages/Nubes.tsx'), /referrerPolicy/)
  assert.doesNotMatch(read('src/pages/Desastres.tsx'), /referrerPolicy/)
})

// ---------------------------------------------------------------------------
// Round 3: change notice, share-alike, alt texts, pinned table, WebP files
// ---------------------------------------------------------------------------

/** One row per photo, written by hand: a change to any author, licence or link must fail here. */
const TABLA: ReadonlyArray<readonly [string, string, string, string | null, string, boolean]> = [
  // id, autor, licencia, URL de la licencia, URL de la fuente, redimensionada
  ['cirros', 'Dimitry B. (ru_boff)', 'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/', 'https://www.flickr.com/photos/ru_boff/8690313402/', true],
  ['cirrostratos', 'jingoba', 'CC0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'https://pixabay.com/photos/cirrostratus-246295/', false],
  ['cirrocumulos', 'Typhoonchaser', 'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/', 'https://commons.wikimedia.org/wiki/File:Cirrocumulus_in_Hong_Kong.jpg', true],
  ['altocumulos', 'MabelAmber', 'CC0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'https://pixabay.com/photos/sky-1430070/', false],
  ['altostratos', 'W.carter', 'CC0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'https://commons.wikimedia.org/wiki/File:Altostratus_with_stratocumulus_under_2.jpg', false],
  ['estrato', 'Rollcloud', 'CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0/', 'https://commons.wikimedia.org/wiki/File:Stratus_nebulosus_opacus_and_Stratus_fractus_(14122021).jpg', true],
  ['estratocumulos', 'sarangib', 'CC0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'https://pixabay.com/photos/palm-trees-266438/', false],
  ['nimboestrato', 'Jacek Halicki', 'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/', 'https://commons.wikimedia.org/wiki/File:2014_Nimbostratus_rekadr.jpg', true],
  ['cumulo', 'Medium69 (William Crochot)', 'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0/', 'https://commons.wikimedia.org/wiki/File:Cumulus_humilis_-_39.jpg', true],
  ['cumulonimbo', 'Jakub Hałun', 'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/', 'https://commons.wikimedia.org/wiki/File:Chmura_burzowa_na_wsch%C3%B3d_od_Krakowa,_20250904_1851_4432.jpg', true],
  ['lenticular', 'NOAA Earth System Research Laboratory', 'Dominio público', null, 'https://commons.wikimedia.org/wiki/File:Lenticular_clouds_in_Boulder_CO_-_NOAA_Earth_System_Research_Laboratory.jpg', false],
  ['mammatus', 'Cbaile19', 'CC0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'https://commons.wikimedia.org/wiki/File:Mammatus_clouds,_Pittsburgh,_2022-06-16,_02.jpg', false],
  ['niebla', 'Jay Huang', 'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/', 'https://commons.wikimedia.org/wiki/File:Beautiful_sunrise_over_Pleasanton_valley.jpg', true],
  ['terremotos', 'USGS', 'CC0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'https://commons.wikimedia.org/wiki/File:2010_Haiti_Earthquake_(After).jpg', true],
  ['inundaciones', 'Flocci Nivis', 'CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/', 'https://commons.wikimedia.org/wiki/File:20240517_Flood_Saarland_07.jpg', true],
  ['tornados', 'Justin Hobson (Justin1569)', 'CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/', 'https://commons.wikimedia.org/wiki/File:F5_tornado_Elie_Manitoba_2007.jpg', true],
  ['huracanes', 'Mike Trenchard, NASA JSC (ISS007-E-14750)', 'Dominio público', null, 'https://commons.wikimedia.org/wiki/File:Hurricane_Isabel_from_ISS.jpg', false],
  ['incendios', 'John McColgan (US Forest Service), edición Fir0002', 'Dominio público', null, 'https://commons.wikimedia.org/wiki/File:Deerfire_high_res_edit.jpg', false],
  ['tsunamis', 'Sofwathulla Mohamed', 'Dominio público (liberada por el autor)', null, 'https://commons.wikimedia.org/wiki/File:2004_Indian_Ocean_earthquake_Maldives_tsunami_wave.jpg', false],
  ['micro-tsunamis', 'NOAA GLERL / L.S. Gerstner', 'CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0/', 'https://commons.wikimedia.org/wiki/File:High_waves_in_Lake_Michigan_along_the_Chicago_shoreline_(16807304806).jpg', true],
  ['ola-de-calor', 'Christopher Michel', 'CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/', 'https://commons.wikimedia.org/wiki/File:Ladakh,_India_(14687115252).jpg', true],
  ['granizo-severo', 'NOAA/NSSL', 'Dominio público', null, 'https://commons.wikimedia.org/wiki/File:Granizo.jpg', false],
  ['erupcion-volcanica', 'FEMA / Kelly Hudson (NARA vía DPLA)', 'Dominio público', null, 'https://commons.wikimedia.org/wiki/File:Close_u_of_red_hot_lava_flowing_on_a_dirt_road,_a_result_of_the_Kilauea_Volcano_eruption_and_lava_flow_in_2014._-_DPLA_-_ced6ae979602bcc6905f497b87d35e8f.JPG', false],
]

test('the 23 credits match the pinned table value by value', () => {
  assert.equal(TABLA.length, 23)
  assert.deepEqual(
    CREDITOS_FOTOS.map(c => [c.id, c.autor, c.licencia.nombre, c.licencia.url ?? null, c.fuente.url, c.redimensionada]),
    TABLA.map(row => [...row]),
  )
})

test('every photo under CC BY or CC BY-SA carries the change notice', () => {
  for (const c of CREDITOS_FOTOS) {
    if (c.licencia.nombre.startsWith('CC BY')) assert.equal(c.redimensionada, true, c.id)
  }
})

test('the change notice says the photo was resized and cropped', () => {
  assert.equal(TEXTO_CAMBIOS, 'redimensionada y recortada')
  const texto = textoCredito(creditoDe('niebla'))
  assert.ok(texto.endsWith(', redimensionada y recortada'), texto)
  assert.doesNotMatch(textoCredito(creditoDe('tsunamis')), /redimensionada|recortada/)
})

test('the pages print the change notice from the shared constant, not a hand-typed word', () => {
  for (const page of ['Nubes', 'Desastres', 'DatosFuentes']) {
    const source = read(`src/pages/${page}.tsx`)
    assert.match(source, /TEXTO_CAMBIOS/, page)
    // the data field is named `redimensionada`; the printed word itself must come from the constant
    assert.doesNotMatch(source.replaceAll('credito.redimensionada', ''), /redimensionada/, `${page} must not hard-code the notice`)
  }
})

test('the text-xs check accepts the plain class only, not a breakpoint variant', () => {
  assert.match('mt-1.5 text-xs leading-snug', TEXT_XS)
  assert.match('text-xs', TEXT_XS)
  assert.doesNotMatch('mt-1.5 sm:text-xs leading-snug', TEXT_XS)
  assert.doesNotMatch('md:text-xs', TEXT_XS)
  assert.doesNotMatch('text-xs-custom', TEXT_XS)
})

test('the photos of Nubes and Desastres show the full credit line as the image title', () => {
  for (const page of ['Nubes', 'Desastres']) {
    assert.match(read(`src/pages/${page}.tsx`), /title=\{textoCredito\(credito\)\}/, page)
  }
})

test('the "Fotos" section says the photos were converted to WebP and cropped', () => {
  assert.match(textoPagina('DatosFuentes'), /se convirtieron a WebP y se recortan para encajar en las tarjetas/)
})

test('the share-alike sentence lists exactly the CC BY-SA photos, built from the data', () => {
  const esperadas = TABLA.filter(row => row[2].startsWith('CC BY-SA')).map(row => row[0])
  assert.deepEqual(esperadas, ['cirrocumulos', 'nimboestrato', 'cumulo', 'tornados', 'micro-tsunamis'])
  assert.deepEqual(FOTOS_COMPARTIR_IGUAL.map(c => c.id), esperadas)
  const source = textoPagina('DatosFuentes')
  assert.match(source, /FOTOS_COMPARTIR_IGUAL/)
  assert.match(source, /se comparten bajo la misma licencia/)
  assert.match(source, /no cambia la del resto del sitio/)
  assert.match(source, /CC BY-SA/)
  for (const c of FOTOS_COMPARTIR_IGUAL) assert.ok(!source.includes(c.tema), `the page must not type "${c.tema}" by hand`)
})

/** A page source with every run of whitespace collapsed, so a JSX sentence can wrap over several lines. */
function textoPagina(page: string): string {
  return read(`src/pages/${page}.tsx`).replace(/\s+/g, ' ')
}

/** imgAlt of a photo by id: clouds come from the catalog, disasters from the cards of Desastres. */
function altDe(id: string): string {
  const nube = CLOUDS.find(c => c.id === id)
  return nube ? nube.imgAlt : desastreAlt(id)
}

// Each alt below was checked against the photo it describes (public/fotos/<id>.webp). `ve` is a word of what
// the picture really shows; `noVe` are words of the old alt, which described something that is not there.
const ALTS: ReadonlyArray<{ id: string; ve: RegExp; noVe: RegExp }> = [
  { id: 'altocumulos', ve: /pequeños copos/i, noVe: /castellanus|torres|convectivas/i },
  { id: 'cumulo', ve: /grises y alargadas/i, noVe: /esponjosas|base plana|blancas/i },
  { id: 'cirrostratos', ve: /velo/i, noVe: /halo|solar/i },
  { id: 'nimboestrato', ve: /grises/i, noVe: /lluvia|continua/i },
  { id: 'lenticular', ve: /lenticulares/i, noVe: /disco|perfecto|estacionario/i },
  { id: 'mammatus', ve: /naranja/i, noVe: /yunque|\bCb\b/i },
  { id: 'terremotos', ve: /satelital/i, noVe: /daños|Port-au-Prince/i },
  { id: 'incendios', ve: /ciervos/i, noVe: /California|cielo naranja/i },
  { id: 'erupcion-volcanica', ve: /colada|incandescente/i, noVe: /ceniza|ríos de lava/i },
]

for (const { id, ve, noVe } of ALTS) {
  test(`the alt of "${id}" describes the photo shown`, () => {
    const alt = altDe(id)
    assert.match(alt, ve, alt)
    assert.doesNotMatch(alt, noVe, alt)
  })
}

test('the alt of the two photos named by the reviewer reads as agreed', () => {
  assert.equal(altDe('altocumulos'), 'Altocúmulos — pequeños copos de nubes blancas dispersos en un cielo azul')
  assert.equal(altDe('cumulo'), 'Cúmulo — nubes bajas grises y alargadas bajo un cielo claro')
})

test('every file in public/fotos is a valid WebP (RIFF/WEBP header with a consistent size)', () => {
  for (const c of CREDITOS_FOTOS) {
    const bytes = readFileSync(new URL(`../public/fotos/${c.id}.webp`, import.meta.url))
    assert.equal(bytes.toString('ascii', 0, 4), 'RIFF', `${c.id}: RIFF`)
    assert.equal(bytes.toString('ascii', 8, 12), 'WEBP', `${c.id}: WEBP`)
    assert.equal(bytes.readUInt32LE(4) + 8, bytes.length, `${c.id}: RIFF size matches the file size`)
  }
})
