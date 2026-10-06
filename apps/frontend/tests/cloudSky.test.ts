import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CLOUDS, CLOUD_FAMILY_SECTIONS, QUICK_ID_GUIDE, type CloudId, type CloudItem } from '../src/data/clouds.ts'
import {
  FLOOR_BOUNDARIES_KM,
  GROUND_LINE,
  SKY_DRIFT_MAX_S,
  SKY_DRIFT_MIN_S,
  SKY_DRIFT_PX,
  SKY_FLOORS,
  SKY_LANE_COUNT,
  cumulonimbusShape,
  diagramLabel,
  driftTiming,
  floorOf,
  floorsCrossed,
  gridLineForKm,
  keepUnitsTogether,
  recognizeHint,
  revealScrollDelta,
  shouldAnimateSky,
  skyFicha,
  skyLayout,
  whatItIndicates,
  type SkyPlacement,
} from '../src/lib/cloudSky.ts'

const SOFT_HYPHEN = String.fromCharCode(0xad)
const FOG_TEXT = 'visibilidad menor a 1 km'
const CU_RANGE = 'base 600–2.000 m · cima hasta ~3 km'
const NS_RANGE = '0–3 km'

function cloud(id: CloudId): CloudItem {
  const found = CLOUDS.find(c => c.id === id)
  assert.ok(found, `no existe la nube ${id} en el catálogo`)
  return found
}

function placement(id: CloudId): SkyPlacement {
  const found = skyLayout().placements.find(p => p.cloudId === id)
  assert.ok(found, `la nube ${id} no aparece en el diagrama`)
  return found
}

/** Every string reachable from a value, so a forbidden phrase cannot hide in a nested field. */
function allStrings(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (Array.isArray(value)) return value.flatMap(allStrings)
  if (value !== null && typeof value === 'object') return Object.values(value).flatMap(allStrings)
  return []
}

// ── Scale ────────────────────────────────────────────────────────────────────

test('la escala de pisos es 0, 2, 6, 12 y 15 km', () => {
  assert.deepEqual([...FLOOR_BOUNDARIES_KM], [0, 2, 6, 12, 15])
})

test('los pisos van de arriba hacia abajo y se tocan sin huecos', () => {
  assert.deepEqual(
    SKY_FLOORS.map(f => [f.id, f.baseKm, f.topKm]),
    [['cima', 12, 15], ['alta', 6, 12], ['media', 2, 6], ['baja', 0, 2]],
  )
})

test('gridLineForKm: cada límite de piso cae en su línea y la altura crece hacia arriba', () => {
  assert.equal(gridLineForKm(15), 1)
  assert.equal(gridLineForKm(12), 5)
  assert.equal(gridLineForKm(6), 9)
  assert.equal(gridLineForKm(2), 13)
  assert.equal(gridLineForKm(0), 17)
  assert.equal(GROUND_LINE, gridLineForKm(0))
  assert.ok(gridLineForKm(3) < gridLineForKm(2), '3 km queda por encima de 2 km')
  assert.ok(gridLineForKm(0.6) > gridLineForKm(2), '600 m queda por debajo de 2 km')
  assert.ok(gridLineForKm(0.6) < GROUND_LINE, '600 m queda por encima del suelo')
})

test('gridLineForKm: fuera de la escala se recorta al suelo o a 15 km', () => {
  assert.equal(gridLineForKm(-1), GROUND_LINE)
  assert.equal(gridLineForKm(20), 1)
})

test('floorOf y floorsCrossed ubican alturas en su piso', () => {
  assert.equal(floorOf(0), 'baja')
  assert.equal(floorOf(1.9), 'baja')
  assert.equal(floorOf(2), 'media')
  assert.equal(floorOf(8), 'alta')
  assert.equal(floorOf(15), 'cima')
  assert.deepEqual(floorsCrossed(0, 3), ['baja', 'media'])
  assert.deepEqual(floorsCrossed(6, 12), ['alta'])
  assert.deepEqual(floorsCrossed(0, 15), ['baja', 'media', 'alta', 'cima'])
})

// ── Every cloud is in the diagram ───────────────────────────────────────────

test('todas las nubes del catálogo aparecen una sola vez en el diagrama', () => {
  const ids = skyLayout().placements.map(p => p.cloudId)
  assert.equal(ids.length, CLOUDS.length)
  assert.deepEqual([...ids].sort(), CLOUDS.map(c => c.id).sort())
})

test('cada nube tiene su pista en la guía rápida, una sola vez', () => {
  const guideIds = QUICK_ID_GUIDE.flatMap(section => section.answers.map(a => a.cloudId))
  assert.deepEqual([...guideIds].sort(), CLOUDS.map(c => c.id).sort())
  for (const c of CLOUDS) assert.ok(recognizeHint(c.id).length > 0, `sin pista para ${c.id}`)
})

test('las nubes de un solo piso quedan dentro de su piso', () => {
  const layers: Array<[CloudId, string]> = [
    ['cirros', 'alta'], ['cirrostratos', 'alta'], ['cirrocumulos', 'alta'],
    ['altocumulos', 'media'], ['altostratos', 'media'], ['lenticular', 'media'],
    ['estrato', 'baja'], ['estratocumulos', 'baja'],
  ]
  for (const [id, floor] of layers) {
    const p = placement(id)
    assert.equal(p.area, 'floor', id)
    assert.equal(p.floor, floor, id)
    assert.deepEqual(p.rows, skyLayout().floorCells[p.floor!], id)
  }
})

test('las etiquetas del diagrama son el nombre del catálogo (con cortes de palabra opcionales)', () => {
  for (const c of CLOUDS) {
    const name = diagramLabel(c).name.replaceAll(SOFT_HYPHEN, '')
    assert.ok(c.name.endsWith(name), `${c.id}: "${name}" no sale de "${c.name}"`)
  }
})

test('solo la lenticular (2–8 km) avisa en el diagrama que se sale de su piso', () => {
  assert.equal(diagramLabel(cloud('lenticular')).note, '2–8 km')
  for (const id of ['cirros', 'cirrostratos', 'cirrocumulos', 'altocumulos', 'altostratos', 'estrato', 'estratocumulos'] as const) {
    assert.equal(diagramLabel(cloud(id)).note, null, id)
  }
})

// ── Fog ──────────────────────────────────────────────────────────────────────

test('la niebla está apoyada en el suelo y nunca queda por debajo', () => {
  const fog = placement('niebla')
  const { floorCells, ground } = skyLayout()
  assert.equal(fog.area, 'ground')
  assert.equal(fog.rows.end, GROUND_LINE, 'la niebla termina justo en la línea del suelo')
  assert.ok(fog.rows.start < GROUND_LINE, 'la niebla ocupa la franja de arriba del suelo')
  assert.ok(fog.rows.start > gridLineForKm(2), 'y es una franja de pocos cientos de metros')
  assert.equal(ground.start, GROUND_LINE, 'la tira del suelo empieza donde termina la niebla')
  assert.ok(floorCells.baja.end <= fog.rows.start, 'las nubes bajas no se pisan con la niebla')
  const band = cloud('niebla').sky.band
  assert.ok('baseKm' in band)
  assert.equal(band.baseKm, 0)
  assert.ok(band.topKm > 0 && band.topKm <= 0.5)
})

test('la niebla no se superpone con ninguna nube vertical', () => {
  const fog = placement('niebla')
  const columns = skyLayout().placements.filter(p => p.area === 'column')
  for (const col of columns) {
    const sharesColumn = fog.lanes.includes(col.lane!)
    if (sharesColumn) assert.ok(col.rows.end <= fog.rows.start, `${col.cloudId} se pisa con la niebla`)
  }
})

test('la niebla dice "visibilidad menor a 1 km" en la guía, el diagrama y la ficha', () => {
  const fog = cloud('niebla')
  assert.equal(diagramLabel(fog).note, FOG_TEXT)
  assert.ok(recognizeHint('niebla').includes(FOG_TEXT))
  assert.ok(skyFicha(fog).recognize.includes(FOG_TEXT))
  assert.ok(fog.composition.toLowerCase().includes(FOG_TEXT))
  const guideHint = QUICK_ID_GUIDE.flatMap(s => s.answers).find(a => a.cloudId === 'niebla')!.hint
  assert.ok(guideHint.includes(FOG_TEXT))
})

test('la curiosidad de la niebla distingue FG (<1 km) de BR (1–5 km)', () => {
  assert.equal(
    cloud('niebla').curiosity,
    'FG en METAR = niebla (<1 km). BR = neblina o bruma (1–5 km). Misma física, distintas implicancias operativas.',
  )
})

test('ningún texto del catálogo ni de la guía dice "visibilidad nula"', () => {
  const texts = [...allStrings(CLOUDS), ...allStrings(QUICK_ID_GUIDE), ...CLOUDS.flatMap(c => allStrings(skyFicha(c)))]
  for (const text of texts) assert.doesNotMatch(text, /visibilidad nula/i)
})

// ── Cumulonimbus and mammatus ───────────────────────────────────────────────

test('la torre del cumulonimbo va del suelo hasta el piso de 15 km', () => {
  const cb = placement('cumulonimbo')
  assert.equal(cb.area, 'tower')
  assert.equal(cb.rows.start, gridLineForKm(15))
  assert.equal(cb.rows.end, GROUND_LINE)
  assert.deepEqual(cb.crosses, ['baja', 'media', 'alta', 'cima'])
  assert.equal(diagramLabel(cloud('cumulonimbo')).note, 'hasta 15 km')
})

test('el mammatus cuelga justo debajo del yunque del cumulonimbo', () => {
  const mammatus = placement('mammatus')
  const { anvil } = skyLayout()
  assert.deepEqual(mammatus.anchor, { cloudId: 'cumulonimbo', part: 'anvil' })
  assert.equal(mammatus.area, 'tower')
  assert.equal(anvil.start, gridLineForKm(15), 'el yunque es la cima de la torre')
  assert.equal(anvil.end, gridLineForKm(12))
  assert.equal(mammatus.rows.start, anvil.end, 'arranca donde termina el yunque')
  assert.ok(mammatus.rows.end < skyLayout().cbBody.start, 'y no tapa el botón del cumulonimbo')
})

test('el yunque se abre hacia el costado sobre las pistas libres y el mammatus cuelga bajo ese alero', () => {
  const layout = skyLayout()
  const mammatus = placement('mammatus')
  assert.deepEqual(layout.anvilLanes, [1, 2], 'el yunque cubre las dos pistas además de la torre')
  assert.equal(mammatus.lane, 1, 'el mammatus cuelga bajo el alero, lejos del cuerpo de la torre')
  assert.deepEqual(mammatus.lanes, [1])
  assert.ok(layout.anvilLanes.includes(mammatus.lane!))
})

test('la torre se ensancha arriba solo donde las franjas verticales no llegan', () => {
  const layout = skyLayout()
  const columnsTop = Math.min(...layout.placements.filter(p => p.area === 'column').map(p => p.rows.start))
  assert.deepEqual(layout.wideBody, { start: layout.anvil.end, end: columnsTop })
  assert.equal(layout.wideBody.end, gridLineForKm(3))
  assert.deepEqual(layout.wideBodyLanes, [2], 'arriba ocupa también la pista vecina a la torre')
  assert.ok(placement('mammatus').rows.end <= columnsTop, 'el mammatus no se pisa con el Cu')
  assert.ok(layout.cbBody.start >= layout.wideBody.start && layout.cbBody.end <= layout.wideBody.end, 'el botón del Cb va en la parte ancha')
})

test('la base del Cb queda a ~500 m y la cortina de lluvia llega al suelo', () => {
  const { cbBase } = skyLayout()
  assert.deepEqual(cbBase, { start: gridLineForKm(0.5), end: GROUND_LINE })
})

// ── Cumulonimbus silhouette ─────────────────────────────────────────────────

// Phone-like box: lane 1 at 0, lane 2 at 72, tower at 132, 204 px wide, ground at 590 px.
const cbBox = { width: 229, lane2X: 64, towerX: 116, anvilBottomY: 34, wideBottomY: 330, baseY: 520, groundY: 550 }
// Wide (640–1280 px) box.
const cbWideBox = { width: 418, lane2X: 104, towerX: 192, anvilBottomY: 40, wideBottomY: 300, baseY: 470, groundY: 500 }
const span = (s: { x0: number; x1: number }) => s.x1 - s.x0

test('cumulonimbusShape: el yunque toca el tope de 15 km y se abre más que la torre', () => {
  const shape = cumulonimbusShape(cbBox)
  assert.ok(shape.anvil.topY <= 3, `tope en ${shape.anvil.topY}`)
  assert.equal(shape.anvil.bottomY, cbBox.anvilBottomY)
  assert.ok(shape.anvil.x1 - shape.anvil.x0 >= 0.9 * cbBox.width, 'el yunque ocupa casi todo el ancho')
  assert.ok(shape.anvil.x0 < shape.bodyTop.x0, 'se abre hacia el costado, más allá del cuerpo')
})

test('cumulonimbusShape: base ancha y chata, más ancha que la cintura del tronco', () => {
  for (const box of [cbBox, cbWideBox]) {
    const shape = cumulonimbusShape(box)
    const towerW = box.width - box.towerX
    assert.ok(span(shape.base) >= 0.8 * towerW, `base ${span(shape.base)} de ${towerW}`)
    assert.ok(span(shape.base) > span(shape.waist), 'la base es más ancha que la cintura')
    assert.ok(shape.waist.y > box.wideBottomY && shape.waist.y < box.baseY, 'la cintura está entre la base y los 3 km')
  }
})

test('cumulonimbusShape: el tronco se ensancha hacia arriba más allá de la base y el yunque lo supera de los dos lados', () => {
  for (const box of [cbBox, cbWideBox]) {
    const shape = cumulonimbusShape(box)
    assert.ok(span(shape.bodyTop) > span(shape.base), 'arriba el tronco es más ancho que la base')
    assert.ok(span(shape.bodyTop) >= 1.3 * span(shape.waist), 'y bastante más ancho que la cintura')
    assert.ok(shape.bodyTop.x0 - shape.anvil.x0 >= 0.15 * box.width, 'el yunque sale bien hacia el costado izquierdo')
    assert.ok(shape.anvil.x1 - shape.bodyTop.x1 >= 6, 'y también asoma a la derecha')
  }
})

test('cumulonimbusShape: borde de coliflor con lóbulos grandes y desparejos, yunque fibroso en las puntas', () => {
  const shape = cumulonimbusShape(cbBox)
  assert.ok(shape.lobes.left >= 4 && shape.lobes.right >= 4, `lóbulos ${JSON.stringify(shape.lobes)}`)
  const biggest = Math.max(...shape.lobeChords)
  const smallest = Math.min(...shape.lobeChords)
  assert.ok(biggest / smallest >= 1.8, `lóbulos casi iguales: ${smallest}–${biggest}`)
  assert.ok(biggest >= 0.2 * (cbBox.width - cbBox.towerX), 'hay lóbulos grandes, no solo festón')
  assert.ok(shape.fibers >= 4, 'hebras en las dos puntas del yunque')
})

test('cumulonimbusShape: nada se sale de la caja ni tapa las franjas, el mammatus ni el suelo', () => {
  for (const box of [cbBox, cbWideBox]) {
    const shape = cumulonimbusShape(box)
    for (const p of shape.extremes) {
      assert.ok(p.x >= 0 && p.x <= box.width, `x fuera: ${p.x}`)
      assert.ok(p.y >= 0 && p.y <= box.groundY, `y fuera: ${p.y}`)
      if (p.y > box.wideBottomY + 0.5) assert.ok(p.x >= box.towerX, `debajo de 3 km pisa las franjas en x=${p.x}`)
      if (p.y > box.anvilBottomY + 0.5) assert.ok(p.x >= box.lane2X, `bajo el alero tapa al mammatus en x=${p.x}`)
    }
  }
})

test('cumulonimbusShape: base chata y oscura, cortina de lluvia hasta el suelo', () => {
  const shape = cumulonimbusShape(cbBox)
  assert.equal(shape.base.y, cbBox.baseY)
  assert.ok(shape.base.x0 >= cbBox.towerX && shape.base.x1 <= cbBox.width)
  assert.ok(shape.rain.length >= 3)
  for (const line of shape.rain) {
    assert.ok(line.y1 >= cbBox.baseY && line.y2 <= cbBox.groundY)
    assert.ok(line.x2 >= cbBox.towerX && line.x1 <= cbBox.width)
  }
  assert.ok(Math.max(...shape.rain.map(l => l.y2)) >= cbBox.groundY - 2, 'la lluvia llega al suelo')
})

test('cumulonimbusShape: caminos SVG válidos en una caja angosta y en una ancha', () => {
  for (const box of [cbBox, cbWideBox]) {
    const shape = cumulonimbusShape(box)
    for (const d of [shape.outline, shape.baseBand, shape.texture]) {
      assert.match(d, /^M/)
      assert.doesNotMatch(d, /NaN|undefined|Infinity/)
    }
  }
})

// ── Content fixes ───────────────────────────────────────────────────────────

test('la tarjeta del mammatus dice "Bajo el yunque del Cb"', () => {
  assert.equal(cloud('mammatus').height, 'Bajo el yunque del Cb')
})

test('el consejo del mammatus dice "debajo de otra nube"', () => {
  assert.match(cloud('mammatus').observeTip, /debajo de otra nube/)
  assert.doesNotMatch(cloud('mammatus').observeTip, /otro nube/)
})

test('el subtítulo de nubes bajas no fija un tope de 2.000 m y nombra al nimboestrato', () => {
  const subtitle = CLOUD_FAMILY_SECTIONS.baja.subtitle
  assert.doesNotMatch(subtitle, /Por debajo de los 2\.000 m/)
  assert.match(subtitle, /Nimboestrato/)
  assert.match(subtitle, /3 km/)
})

test('la lenticular sigue en el piso medio con la nota 2–8 km', () => {
  assert.equal(placement('lenticular').floor, 'media')
  assert.equal(diagramLabel(cloud('lenticular')).note, '2–8 km')
})

test('la ficha del mammatus explica aire descendente y turbulento bajo el yunque, señal de convección fuerte', () => {
  const text = whatItIndicates(cloud('mammatus'))
  assert.match(text, /descendente/i)
  assert.match(text, /turbulento/i)
  assert.match(text, /yunque/i)
  assert.match(text, /convección fuerte/i)
  assert.equal(skyFicha(cloud('mammatus')).indicates, text)
  assert.equal(skyFicha(cloud('mammatus')).badgeLabel, cloud('mammatus').badgeLabel)
})

test('las demás nubes indican lo mismo que su aviso del catálogo', () => {
  for (const c of CLOUDS.filter(c => c.id !== 'mammatus')) {
    assert.equal(whatItIndicates(c), c.badgeLabel, c.id)
  }
})

// ── Cumulus and nimbostratus: same text in diagram and card ─────────────────

test('cúmulo: "base 600–2.000 m · cima hasta ~3 km" igual en el diagrama y en la ficha', () => {
  const cu = cloud('cumulo')
  assert.equal(diagramLabel(cu).note, CU_RANGE)
  assert.equal(skyFicha(cu).rangeLabel, CU_RANGE)
  assert.equal(cu.height, CU_RANGE, 'la ficha completa del catálogo usa el mismo texto')
})

test('cúmulo: su franja va de 600 m a ~3 km, del piso bajo al medio, sin tocar el suelo', () => {
  const p = placement('cumulo')
  assert.equal(p.area, 'column')
  assert.equal(p.rows.start, gridLineForKm(3))
  assert.equal(p.rows.end, gridLineForKm(0.6))
  assert.deepEqual(p.crosses, ['baja', 'media'])
})

test('nimboestrato: "0–3 km" igual en el diagrama y en la ficha', () => {
  const ns = cloud('nimboestrato')
  assert.equal(diagramLabel(ns).note, NS_RANGE)
  assert.equal(skyFicha(ns).rangeLabel, NS_RANGE)
  assert.ok(ns.heightTag.includes(NS_RANGE), 'la etiqueta de la ficha completa también dice 0–3 km')
})

test('nimboestrato: una franja que cruza del piso bajo al medio y llega al suelo', () => {
  const p = placement('nimboestrato')
  assert.equal(p.area, 'column')
  assert.equal(p.rows.start, gridLineForKm(3))
  assert.equal(p.rows.end, GROUND_LINE)
  assert.deepEqual(p.crosses, ['baja', 'media'])
})

test('las franjas verticales caben en las pistas del diagrama, una por pista', () => {
  const columns = skyLayout().placements.filter(p => p.area === 'column')
  const lanes = columns.map(p => p.lane)
  assert.equal(new Set(lanes).size, lanes.length)
  for (const lane of lanes) assert.ok(lane !== null && lane >= 1 && lane <= SKY_LANE_COUNT)
})

// ── Card ("qué indica") ─────────────────────────────────────────────────────

test('skyFicha reutiliza los datos del catálogo sin inventar', () => {
  for (const c of CLOUDS) {
    const f = skyFicha(c)
    assert.equal(f.name, c.name)
    assert.equal(f.latin, c.latin)
    assert.equal(f.composition, c.composition)
    assert.equal(f.dangerLevel, c.dangerLevel)
    assert.equal(f.badgeLabel, c.badgeLabel)
    assert.equal(f.rangeLabel, c.sky.rangeLabel)
    assert.ok(f.familyTitle.length > 0)
    assert.doesNotMatch(f.recognize, /^→|NaN|undefined|null/)
  }
})

test('keepUnitsTogether: un número nunca se separa de su unidad, y nada más cambia', () => {
  const nbsp = String.fromCharCode(0xa0)
  assert.equal(keepUnitsTogether(CU_RANGE), `base 600–2.000${nbsp}m · cima hasta ~3${nbsp}km`)
  assert.equal(keepUnitsTogether(FOG_TEXT), `visibilidad menor a 1${nbsp}km`)
  assert.equal(keepUnitsTogether(NS_RANGE), `0–3${nbsp}km`)
  assert.equal(keepUnitsTogether('bajo el yunque del Cb'), 'bajo el yunque del Cb')
  assert.equal(keepUnitsTogether(CU_RANGE).replaceAll(nbsp, ' '), CU_RANGE)
})

// ── Scrolling under the sticky header ───────────────────────────────────────

// Header ends at 220 px, window 812 px high, 12 px of breathing room: visible area 232..800.
const view = { viewTop: 232, viewBottom: 800 }

test('revealScrollDelta: algo que ya se ve entero no mueve la página', () => {
  assert.equal(revealScrollDelta({ ...view, top: 300, bottom: 700, align: 'nearest' }), 0)
})

test('revealScrollDelta: algo que queda abajo sube lo justo para verse entero', () => {
  assert.equal(revealScrollDelta({ ...view, top: 700, bottom: 1000, align: 'nearest' }), 200)
})

test('revealScrollDelta: algo más alto que el área visible muestra su comienzo, nunca queda tapado por el encabezado', () => {
  assert.equal(revealScrollDelta({ ...view, top: 700, bottom: 1500, align: 'nearest' }), 468)
  assert.equal(revealScrollDelta({ ...view, top: 100, bottom: 300, align: 'nearest' }), -132)
})

test('revealScrollDelta: con align start el comienzo queda justo bajo el encabezado', () => {
  assert.equal(revealScrollDelta({ ...view, top: 80, bottom: 400, align: 'start' }), -152)
  assert.equal(revealScrollDelta({ ...view, top: 1200, bottom: 1600, align: 'start' }), 968)
})

// ── Motion ──────────────────────────────────────────────────────────────────

test('shouldAnimateSky: quieto con movimiento reducido o en pausa, animado si no', () => {
  assert.equal(shouldAnimateSky({ reducedMotion: false, paused: false }), true)
  assert.equal(shouldAnimateSky({ reducedMotion: true, paused: false }), false)
  assert.equal(shouldAnimateSky({ reducedMotion: false, paused: true }), false)
  assert.equal(shouldAnimateSky({ reducedMotion: true, paused: true }), false)
})

test('driftTiming: ±4 px, ciclos de 14 a 22 s, sin arrancar todos juntos', () => {
  assert.equal(SKY_DRIFT_PX, 4)
  assert.equal(SKY_DRIFT_MIN_S, 14)
  assert.equal(SKY_DRIFT_MAX_S, 22)
  const timings = CLOUDS.map((_, i) => driftTiming(i))
  for (const t of timings) {
    assert.ok(t.durationS >= 14 && t.durationS <= 22, `duración ${t.durationS}`)
    assert.ok(t.delayS <= 0, 'el desfase es negativo: arranca a mitad de ciclo, sin espera')
  }
  assert.ok(new Set(timings.map(t => t.durationS)).size > 3, 'no todas las nubes van al mismo ritmo')
})
