/**
 * Logic of the Nubes altitude diagram ("Atmósfera en capas"), kept pure so it can be tested
 * without a browser: the floors and their scale, where each cloud of the catalog goes and the
 * texts the diagram shows.
 *
 * The diagram is a CSS grid drawn "por piso, no a escala": every floor gets the same number of
 * sub-rows whatever its height in km. Grid lines are numbered from the top of the scale
 * (15 km, line 1) down to the ground line.
 */
import { CLOUDS, type CloudBand, type CloudId, type CloudItem } from '../data/clouds.ts'

// ---------------------------------------------------------------------------
// Floors and scale
// ---------------------------------------------------------------------------

/** Floor boundaries, from the ground up. */
export const FLOOR_BOUNDARIES_KM = [0, 2, 6, 12, 15] as const

/** Sub-rows per floor: enough to place 600 m, 3 km or a ground layer inside a floor. */
export const SUBROWS_PER_FLOOR = 4

export type FloorId = 'baja' | 'media' | 'alta' | 'cima'

export interface SkyFloor {
  id: FloorId
  baseKm: number
  topKm: number
  /** Label of the floor's top line on the axis. */
  axisLabel: string
  /** Short floor name under the axis label (none for the top floor, only the Cb reaches it). */
  name: string | null
  /** Accessible name of the group of clouds drawn in the floor. */
  groupLabel: string
}

/** Top to bottom, the order they are drawn and read. */
export const SKY_FLOORS: readonly SkyFloor[] = [
  { id: 'cima', baseKm: 12, topKm: 15, axisLabel: '15 km', name: null, groupLabel: 'De 12 a 15 km' },
  { id: 'alta', baseKm: 6, topKm: 12, axisLabel: '12 km', name: 'Altas', groupLabel: 'Nubes altas, de 6 a 12 km' },
  { id: 'media', baseKm: 2, topKm: 6, axisLabel: '6 km', name: 'Medias', groupLabel: 'Nubes medias, de 2 a 6 km' },
  { id: 'baja', baseKm: 0, topKm: 2, axisLabel: '2 km', name: 'Bajas', groupLabel: 'Nubes bajas, por debajo de 2 km' },
]

const FLOORS_BOTTOM_UP: readonly FloorId[] = ['baja', 'media', 'alta', 'cima']
const FLOOR_COUNT = FLOORS_BOTTOM_UP.length

/** Height in floors from the ground: 0 at the ground, 1 at 2 km, 2 at 6 km, 3 at 12 km, 4 at 15 km. */
export function floorPosition(km: number): number {
  const b = FLOOR_BOUNDARIES_KM
  if (km <= b[0]) return 0
  for (let i = 0; i < FLOOR_COUNT; i++) {
    if (km <= b[i + 1]) return i + (km - b[i]) / (b[i + 1] - b[i])
  }
  return FLOOR_COUNT
}

/** Grid line (from the top, 1-based) for an altitude; out-of-scale altitudes clamp to the ends. */
export function gridLineForKm(km: number): number {
  return 1 + Math.round((FLOOR_COUNT - floorPosition(km)) * SUBROWS_PER_FLOOR)
}

/** The ground line: nothing in the sky is drawn below it. */
export const GROUND_LINE = gridLineForKm(0)

/** Floor that holds an altitude; a boundary belongs to the floor above it. */
export function floorOf(km: number): FloorId {
  return FLOORS_BOTTOM_UP[Math.min(Math.floor(floorPosition(km)), FLOOR_COUNT - 1)]
}

/** Floors a band crosses, bottom up. A top that sits on a boundary does not enter the next floor. */
export function floorsCrossed(baseKm: number, topKm: number): FloorId[] {
  const first = Math.min(Math.floor(floorPosition(baseKm)), FLOOR_COUNT - 1)
  const last = Math.max(first, Math.ceil(floorPosition(topKm)) - 1)
  return FLOORS_BOTTOM_UP.slice(first, last + 1)
}

// ---------------------------------------------------------------------------
// Placement
// ---------------------------------------------------------------------------

/** Lanes for vertical strips between the floor area and the Cb tower (matches the CSS grid). */
export const SKY_LANE_COUNT = 2

/** Sub-rows the anvil accessory (mammatus) takes under the anvil. */
const ACCESSORY_SUBROWS = 3

export interface GridRows {
  start: number
  end: number
}

/**
 * - `floor`: inside the floor area, with the other clouds of its floor.
 * - `column`: a vertical strip in its own lane.
 * - `tower`: inside the Cb tower (the tower itself, or something hanging from it).
 * - `ground`: resting on the ground line.
 */
export type SkyArea = 'floor' | 'column' | 'tower' | 'ground'

export interface SkyPlacement {
  cloudId: CloudId
  area: SkyArea
  /** Floor whose cell holds the cloud (`floor` area only). */
  floor: FloorId | null
  /** Lane of a vertical strip (`column` area only), 1 = next to the floor area. */
  lane: number | null
  /** Lanes the drawing covers besides the floor area (a column's own lane, or lanes the ground layer runs under). */
  lanes: number[]
  rows: GridRows
  crosses: FloorId[]
  anchor: { cloudId: CloudId; part: 'anvil' } | null
}

export interface SkyLayout {
  placements: SkyPlacement[]
  /** Cell of each floor in the floor area (the low floor stops where the ground layer starts). */
  floorCells: Record<FloorId, GridRows>
  /**
   * Cb drawing parts, in the diagram's grid lines (the tower is a subgrid of the diagram that
   * also covers the strip lanes, so the anvil and the upper tower can spread over them).
   */
  anvil: GridRows
  /** Lanes the anvil opens over, besides the tower lane (all of them: nothing else reaches 12 km). */
  anvilLanes: number[]
  /** Rows where the tower is wide: from the anvil down to where the vertical strips begin. */
  wideBody: GridRows
  /** Lanes the wide part of the tower also covers (the lane next to the tower; the mammatus keeps the far one). */
  wideBodyLanes: number[]
  /** Rows of the Cb button, inside the wide part. */
  cbBody: GridRows
  /** From the flat base (~500 m) to the ground: the rain curtain. */
  cbBase: GridRows
  /** Ground strip under the ground line. */
  ground: GridRows
}

function isAltitudeBand(band: CloudBand): band is { baseKm: number; topKm: number } {
  return 'baseKm' in band
}

function bandRows(baseKm: number, topKm: number): GridRows {
  const end = gridLineForKm(baseKm)
  return { start: Math.min(gridLineForKm(topKm), end - 1), end }
}

/** Where every cloud of the catalog is drawn. */
export function skyLayout(clouds: readonly CloudItem[] = CLOUDS): SkyLayout {
  const towerRows = { start: gridLineForKm(15), end: GROUND_LINE }
  const anvil = { start: towerRows.start, end: gridLineForKm(12) }
  const accessoryRows = { start: anvil.end, end: anvil.end + ACCESSORY_SUBROWS }
  const cbBase = { start: gridLineForKm(0.5), end: GROUND_LINE }

  const altitude = (c: CloudItem) => (isAltitudeBand(c.sky.band) ? c.sky.band : null)

  const groundStart = Math.min(
    GROUND_LINE,
    ...clouds.filter(c => c.sky.shape === 'ground').map(c => bandRows(0, altitude(c)?.topKm ?? 0).start),
  )

  // Strips that stay clear of the ground layer go first (next to the floor area), so the
  // ground layer can run under them; strips that reach the ground sit next to the tower.
  const columns = clouds
    .filter(c => c.sky.shape === 'column')
    .map(c => ({ cloud: c, band: altitude(c)! }))
    .sort((a, b) => b.band.baseKm - a.band.baseKm)
  if (columns.length > SKY_LANE_COUNT) {
    throw new Error(`cloudSky: ${columns.length} franjas verticales y solo ${SKY_LANE_COUNT} pistas`)
  }
  const laneOf = new Map(columns.map((col, i) => [col.cloud.id, i + 1]))

  const groundLanes: number[] = []
  for (const [i, col] of columns.entries()) {
    if (bandRows(col.band.baseKm, col.band.topKm).end > groundStart) break
    groundLanes.push(i + 1)
  }

  const floorCells: Record<FloorId, GridRows> = {
    cima: { start: gridLineForKm(15), end: gridLineForKm(12) },
    alta: { start: gridLineForKm(12), end: gridLineForKm(6) },
    media: { start: gridLineForKm(6), end: gridLineForKm(2) },
    baja: { start: gridLineForKm(2), end: groundStart },
  }

  // The anvil opens over every lane (no strip reaches 12 km). The tower is wide down to where
  // the first strip starts; there it narrows to its own lane. The mammatus hangs under the
  // anvil's overhang in the far lane, the wide tower takes the lane next to it.
  const lanes = Array.from({ length: SKY_LANE_COUNT }, (_, i) => i + 1)
  const columnsTop = Math.min(GROUND_LINE, ...columns.map(col => bandRows(col.band.baseKm, col.band.topKm).start))
  const wideBody = { start: anvil.end, end: columnsTop }
  const overhangLane = lanes[0]
  const wideBodyLanes = lanes.slice(1)
  const cbBody = { start: gridLineForKm(6), end: columnsTop }

  const placements = clouds.map((c): SkyPlacement => {
    const base = { cloudId: c.id, floor: null, lane: null, lanes: [], anchor: null }
    const { band } = c.sky
    if (!isAltitudeBand(band)) {
      return {
        ...base,
        area: 'tower',
        lane: overhangLane,
        lanes: [overhangLane],
        rows: accessoryRows,
        crosses: [],
        anchor: { cloudId: band.hangsUnderAnvilOf, part: 'anvil' },
      }
    }
    const crosses = floorsCrossed(band.baseKm, band.topKm)
    switch (c.sky.shape) {
      case 'column': {
        const lane = laneOf.get(c.id)!
        return { ...base, area: 'column', lane, lanes: [lane], rows: bandRows(band.baseKm, band.topKm), crosses }
      }
      case 'tower':
        return { ...base, area: 'tower', rows: towerRows, crosses }
      case 'ground':
        return { ...base, area: 'ground', lanes: groundLanes, rows: { start: groundStart, end: GROUND_LINE }, crosses }
      default: {
        const floor = floorOf(band.baseKm)
        return { ...base, area: 'floor', floor, rows: floorCells[floor], crosses }
      }
    }
  })

  return {
    placements,
    floorCells,
    anvil,
    anvilLanes: lanes,
    wideBody,
    wideBodyLanes,
    cbBody,
    cbBase,
    ground: { start: GROUND_LINE, end: GROUND_LINE + 1 },
  }
}

// ---------------------------------------------------------------------------
// Texts of the diagram
// ---------------------------------------------------------------------------

export interface DiagramLabel {
  /** May contain soft hyphens for narrow lanes. */
  name: string
  note: string | null
}

/** Name and line under it in the diagram; crossing clouds show their range. */
export function diagramLabel(cloud: CloudItem): DiagramLabel {
  const { sky } = cloud
  const name = sky.label ?? cloud.name
  if (sky.note) return { name, note: sky.note }
  if (sky.shape === 'layer' && isAltitudeBand(sky.band)) {
    const oneFloor = floorsCrossed(sky.band.baseKm, sky.band.topKm).length === 1
    return { name, note: oneFloor ? null : sky.rangeLabel }
  }
  return { name, note: sky.rangeLabel }
}

const NBSP = String.fromCharCode(0xa0)

/**
 * Rendering form of a height text: a non-breaking space between a number and its unit
 * ("2.000 m", "~3 km") so a narrow lane never leaves the unit alone on a line.
 */
export function keepUnitsTogether(text: string): string {
  return text.replace(/(\d) (k?m)\b/g, `$1${NBSP}$2`)
}

// ---------------------------------------------------------------------------
// Scrolling under the app's sticky header
// ---------------------------------------------------------------------------

export interface RevealInput {
  /** Element edges, relative to the window. */
  top: number
  bottom: number
  /** Visible area: below the sticky header, above the window's bottom edge. */
  viewTop: number
  viewBottom: number
  /** `start`: put the element's top right under the header. `nearest`: scroll only if it is not fully visible. */
  align: 'start' | 'nearest'
}

/** How far to scroll (px, positive = down) so an element shows without hiding under the header. */
export function revealScrollDelta({ top, bottom, viewTop, viewBottom, align }: RevealInput): number {
  if (align === 'start' || top < viewTop) return top - viewTop
  if (bottom > viewBottom) return Math.min(bottom - viewBottom, top - viewTop)
  return 0
}

// ---------------------------------------------------------------------------
// Cumulonimbus silhouette
// ---------------------------------------------------------------------------

/**
 * The Cb drawing box, measured in px on the page (the drawing is made at real size, so the
 * cauliflower lobes stay round at any width). x = 0 is the far edge of the strip lanes,
 * y = 0 the 15 km line.
 */
export interface CbBox {
  width: number
  /** Where the lane next to the tower starts (the mammatus hangs left of it). */
  lane2X: number
  /** Where the tower lane starts (below `wideBottomY` the drawing stays right of it). */
  towerX: number
  /** 12 km line: underside of the anvil. */
  anvilBottomY: number
  /** Where the vertical strips start (~3 km): the tower narrows to its lane. */
  wideBottomY: number
  /** Flat dark base (~500 m). */
  baseY: number
  /** Ground line. */
  groundY: number
}

export interface Pt {
  x: number
  y: number
}

export interface CbShape {
  /** Anvil + cauliflower tower + flat base, one closed path. */
  outline: string
  /** Dark band along the base. */
  baseBand: string
  /** Inner bulges that read as cauliflower. */
  texture: string
  rain: Array<{ x1: number; y1: number; x2: number; y2: number }>
  anvil: { x0: number; x1: number; topY: number; bottomY: number }
  /** Widest extent of the trunk above 3 km. */
  bodyTop: { x0: number; x1: number }
  /** Narrowest point of the trunk, between the base and 3 km. */
  waist: { x0: number; x1: number; y: number }
  base: { x0: number; x1: number; y: number }
  lobes: { left: number; right: number }
  /** Chord of every lobe, to check they are uneven. */
  lobeChords: number[]
  /** Fibre strokes at the anvil tips. */
  fibers: number
  /** Every point the drawing can reach (vertices, curve controls, lobe tops), for bounds checks. */
  extremes: Pt[]
}

/** Stroke half-width margin. */
const CB_PAD = 1.5
/** Relative lobe sizes along an edge: strongly uneven, like real cauliflower billows. */
const LOBE_PATTERN = [1, 0.62, 1.38, 0.8, 1.2, 0.7]
/** Arc radius relative to its chord: the lobe sticks out ~0.29 chord. */
const LOBE_RADIUS = 0.58
/**
 * Upper bound of a lobe's bulge relative to the nominal chord of its edge (pattern spread and
 * rounding make a segment up to ~1.45 chords long), used to keep the drawing inside its box.
 */
const LOBE_BULGE = 0.42

const r1 = (v: number) => Math.round(v * 10) / 10
const fmt = (p: Pt) => `${r1(p.x)} ${r1(p.y)}`
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)

function lobeSagitta(chord: number): number {
  const radius = LOBE_RADIUS * chord
  return radius - Math.sqrt(radius * radius - (chord * chord) / 4)
}

interface LobedEdge {
  d: string
  count: number
  chords: number[]
  tops: Pt[]
  ends: Pt[]
}

/**
 * Lobed edge from `a` to `b` as SVG arcs bulging outward (the path runs clockwise, so outward
 * is the left-hand normal (dy, -dx)). Returns the arcs, their chords and the lobe tops.
 */
function lobedEdge(a: Pt, b: Pt, chord: number, phase = 0): LobedEdge {
  const length = Math.hypot(b.x - a.x, b.y - a.y)
  const count = Math.max(2, Math.ceil(length / chord))
  const weights = Array.from({ length: count }, (_, i) => LOBE_PATTERN[(i + phase) % LOBE_PATTERN.length])
  const total = weights.reduce((sum, w) => sum + w, 0)
  const ux = (b.x - a.x) / length
  const uy = (b.y - a.y) / length
  let d = ''
  let travelled = 0
  const chords: number[] = []
  const tops: Pt[] = []
  const ends: Pt[] = []
  for (const w of weights) {
    const seg = (length * w) / total
    const start = { x: a.x + ux * travelled, y: a.y + uy * travelled }
    travelled += seg
    const end = { x: a.x + ux * travelled, y: a.y + uy * travelled }
    const s = lobeSagitta(seg)
    chords.push(r1(seg))
    tops.push({ x: (start.x + end.x) / 2 + uy * s, y: (start.y + end.y) / 2 - ux * s })
    ends.push(end)
    d += ` A ${r1(LOBE_RADIUS * seg)} ${r1(LOBE_RADIUS * seg)} 0 0 1 ${fmt(end)}`
  }
  return { d, count, chords, tops, ends }
}

/** Lobed path through several points, each stretch with its own lobe size and phase. */
function lobedPath(points: Pt[], stretches: Array<{ chord: number; phase: number }>): LobedEdge {
  const edges = stretches.map((s, i) => lobedEdge(points[i], points[i + 1], s.chord, s.phase))
  return {
    d: edges.map(e => e.d).join(''),
    count: edges.reduce((n, e) => n + e.count, 0),
    chords: edges.flatMap(e => e.chords),
    tops: edges.flatMap(e => e.tops),
    ends: edges.flatMap(e => e.ends),
  }
}

/** Bulge (arc) inside the body, for texture. */
function innerBulge(from: Pt, to: Pt): string {
  const chord = Math.hypot(to.x - from.x, to.y - from.y)
  return `M ${fmt(from)} A ${r1(LOBE_RADIUS * chord)} ${r1(LOBE_RADIUS * chord)} 0 0 1 ${fmt(to)}`
}

/** x of a polyline (ordered by y, top to bottom) at height y. */
function xAt(poly: Pt[], y: number): number {
  for (let i = 0; i < poly.length - 1; i++) {
    const [p, q] = [poly[i], poly[i + 1]]
    if (y >= p.y && y <= q.y) return p.x + ((q.x - p.x) * (y - p.y)) / (q.y - p.y || 1)
  }
  return y < poly[0].y ? poly[0].x : poly[poly.length - 1].x
}

/**
 * Silhouette of a textbook cumulonimbus: a wide flat dark base, a waist, a trunk that billows
 * out above 3 km with big uneven cauliflower lobes, and a large smooth anvil with fibrous tips
 * spreading to both sides at the 15 km line; a faint rain curtain hangs under the base.
 * Pure: the component only measures the box.
 */
export function cumulonimbusShape(box: CbBox): CbShape {
  const { width: W, lane2X, towerX, groundY } = box
  const anvilBottomY = Math.max(box.anvilBottomY, 8)
  const wideBottomY = Math.max(box.wideBottomY, anvilBottomY + 16)
  const baseY = Math.min(Math.max(box.baseY, wideBottomY + 16), groundY)

  const towerW = Math.max(W - towerX, 24)
  const chordUp = clamp(towerW * 0.34, 14, 60)
  const chordLow = clamp(towerW * 0.16, 8, 30)
  const sUp = LOBE_BULGE * chordUp
  const sLow = LOBE_BULGE * chordLow
  const rightOverhang = Math.max(6, towerW * 0.05)

  const topY = 2
  const h = anvilBottomY - topY
  const anvilLeft = CB_PAD
  const anvilRight = W - CB_PAD
  const upperH = wideBottomY - anvilBottomY
  const lowerH = baseY - wideBottomY
  // The trunk keeps widening almost up to the anvil, with only a slight neck under it.
  const billowY = anvilBottomY + 0.22 * upperH
  const waistY = wideBottomY + 0.45 * lowerH

  // Right side, top to bottom: neck under the anvil, billow, 3 km, waist, base corner.
  const right: Pt[] = [
    { x: anvilRight - sUp - rightOverhang - towerW * 0.05, y: anvilBottomY },
    { x: anvilRight - sUp - rightOverhang, y: billowY },
    { x: anvilRight - sUp - rightOverhang - towerW * 0.03, y: wideBottomY },
    { x: anvilRight - sLow - towerW * 0.13, y: waistY },
    { x: anvilRight - sLow, y: baseY },
  ]
  // Left side, bottom to top: base corner, waist, 3 km, billow over the next lane, neck.
  const leftBillowX = lane2X + CB_PAD + sUp
  const left: Pt[] = [
    { x: towerX + CB_PAD + sLow, y: baseY },
    { x: towerX + CB_PAD + sLow + towerW * 0.13, y: waistY },
    { x: towerX + CB_PAD + sLow + towerW * 0.04, y: wideBottomY },
    { x: leftBillowX, y: billowY },
    { x: leftBillowX + 0.18 * (towerX - leftBillowX), y: anvilBottomY },
  ]

  const rightEdge = lobedPath(right, [
    { chord: chordUp, phase: 1 },
    { chord: chordUp, phase: 3 },
    { chord: chordLow, phase: 2 },
    { chord: chordLow, phase: 4 },
  ])
  const leftEdge = lobedPath(left, [
    { chord: chordLow, phase: 0 },
    { chord: chordLow, phase: 3 },
    { chord: chordUp, phase: 2 },
    { chord: chordUp, phase: 5 },
  ])

  // Anvil, like a flattened mushroom cap: flat top at the 15 km line, thin tips opening to the
  // sides, concave underside sweeping from the neck to each tip; over the mammatus the
  // underside stays at the 12 km line so the pouches hang right from it.
  const neckR = right[0]
  const anvilPts: Pt[] = [
    { x: anvilLeft, y: topY + 0.2 * h },
    { x: anvilLeft + 0.03 * W, y: topY },
    { x: anvilLeft + 0.14 * W, y: topY },
    { x: anvilRight - 0.14 * W, y: topY },
    { x: anvilRight - 0.03 * W, y: topY },
    { x: anvilRight, y: topY + 0.2 * h },
    { x: neckR.x + 0.25 * (W - neckR.x), y: anvilBottomY - 0.05 * h },
    { x: anvilLeft + 0.4 * lane2X, y: anvilBottomY },
    { x: anvilLeft + 0.06 * W, y: anvilBottomY - 0.08 * h },
  ]
  const [tipL, ctlTL, topL, topR, ctlTR, tipR, ctlR, underL, ctlTip] = anvilPts

  const outline = [
    `M ${fmt(tipL)}`,
    `Q ${fmt(ctlTL)} ${fmt(topL)}`,
    `L ${fmt(topR)}`,
    `Q ${fmt(ctlTR)} ${fmt(tipR)}`,
    `Q ${fmt(ctlR)} ${fmt(neckR)}`,
    rightEdge.d,
    `L ${fmt(left[0])}`,
    leftEdge.d,
    `L ${fmt(underL)}`,
    `Q ${fmt(ctlTip)} ${fmt(tipL)}`,
    'Z',
  ].join(' ')

  const base = { x0: left[0].x, x1: right[right.length - 1].x, y: baseY }
  const bandH = Math.min(16, lowerH * 0.14)
  const baseBand = [
    `M ${fmt({ x: base.x0, y: baseY - bandH })}`,
    `Q ${fmt({ x: (base.x0 + base.x1) / 2, y: baseY - bandH * 1.7 })} ${fmt({ x: base.x1, y: baseY - bandH })}`,
    `L ${fmt({ x: base.x1, y: baseY })}`,
    `L ${fmt({ x: base.x0, y: baseY })}`,
    'Z',
  ].join(' ')

  // Texture: inner billows, plus fibres streaming out of both anvil tips.
  const leftPoly = [...left].reverse()
  const upperBulges = [0.2, 0.45, 0.7].map(f => {
    const y = anvilBottomY + upperH * f
    const x0 = xAt(leftPoly, y) + chordLow * 0.7
    const x1 = xAt(right, y) - chordLow * 0.7
    const mid = (x0 + x1) / 2
    return `${innerBulge({ x: x0, y }, { x: mid, y: y - 2 })} ${innerBulge({ x: mid + 2, y: y - 2 }, { x: x1, y })}`
  })
  const lowerBulges = [0.3, 0.68].map(f => {
    const y = wideBottomY + lowerH * f
    return innerBulge({ x: xAt(leftPoly, y) + chordLow * 0.6, y }, { x: xAt(right, y) - chordLow * 0.6, y: y - 1 })
  })
  const bulges = [...upperBulges, ...lowerBulges]
  const fiberRows = [0.32, 0.5, 0.68]
  const fibers = fiberRows.flatMap(f => {
    const y = topY + h * f
    const len = 0.11 * W
    return [
      `M ${fmt({ x: anvilLeft + 2 + 0.02 * W * f, y })} Q ${fmt({ x: anvilLeft + len * 0.5, y: y - 1.5 })} ${fmt({ x: anvilLeft + len, y: y + 0.5 })}`,
      `M ${fmt({ x: anvilRight - 2 - 0.02 * W * f, y })} Q ${fmt({ x: anvilRight - len * 0.5, y: y - 1.5 })} ${fmt({ x: anvilRight - len, y: y + 0.5 })}`,
    ]
  })
  const texture = [...bulges, ...fibers].join(' ')

  const rainStep = Math.max(7, (base.x1 - base.x0) / 9)
  const rain: CbShape['rain'] = []
  for (let x = base.x0 + 5; x <= base.x1 - 3; x += rainStep) {
    rain.push({ x1: r1(x), y1: r1(baseY + 2), x2: r1(Math.max(x - 4, towerX)), y2: r1(groundY - 1) })
  }

  const above3km = (p: Pt) => p.y <= wideBottomY
  const widestLeft = Math.min(...leftEdge.tops.filter(above3km).map(p => p.x), leftBillowX)
  const widestRight = Math.max(...rightEdge.tops.filter(above3km).map(p => p.x), right[1].x)

  return {
    outline,
    baseBand,
    texture,
    rain,
    anvil: { x0: anvilLeft, x1: anvilRight, topY, bottomY: anvilBottomY },
    bodyTop: { x0: widestLeft, x1: widestRight },
    waist: { x0: left[1].x, x1: right[3].x, y: waistY },
    base,
    lobes: { left: leftEdge.count, right: rightEdge.count },
    lobeChords: [...leftEdge.chords, ...rightEdge.chords],
    fibers: fibers.length,
    extremes: [...anvilPts, ...leftEdge.tops, ...leftEdge.ends, ...rightEdge.tops, ...rightEdge.ends, ...left, ...right],
  }
}
