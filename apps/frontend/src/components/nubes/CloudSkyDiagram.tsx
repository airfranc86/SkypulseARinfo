import { useId, type CSSProperties } from 'react'
import { CLOUDS, type CloudId, type CloudItem } from '@/data/clouds'
import {
  GROUND_LINE,
  SKY_FLOORS,
  diagramLabel,
  gridLineForKm,
  keepUnitsTogether,
  skyLayout,
  type GridRows,
  type SkyPlacement,
} from '@/lib/cloudSky'
import { CloudGlyph } from './CloudGlyph'
import { CumulonimbusTower } from './CumulonimbusTower'
import './cloudSky.css'

/*
 * "Atmósfera en capas": one static altitude column (0, 2, 6, 12 and 15 km) with one button per
 * cloud; a tap jumps to the cloud's catalog card. Placement comes from `skyLayout` (pure,
 * tested); this component only maps it onto the CSS grid in cloudSky.css.
 */

const LAYOUT = skyLayout()
const CLOUD_BY_ID = new Map<CloudId, CloudItem>(CLOUDS.map(c => [c.id, c]))
const FLOOR_AREA = ['alta', 'media', 'baja'] as const
const FLOOR_LIST_LABELS: Record<(typeof FLOOR_AREA)[number], string> = {
  alta: 'Nubes altas · 6–12 km',
  media: 'Nubes medias · 2–6 km',
  baja: 'Nubes bajas · 0–2 km',
}

const byArea = (area: SkyPlacement['area']) => LAYOUT.placements.filter(p => p.area === area)
const COLUMNS = byArea('column').toSorted((a, b) => a.lane! - b.lane!)
const GROUND = byArea('ground')
const TOWER = byArea('tower').find(p => p.anchor === null)
const TOWER_ACCESSORIES = byArea('tower').filter(p => p.anchor !== null)

const rows = ({ start, end }: GridRows) => `${start} / ${end}`
/** Rows of a part of the tower, counted inside the tower's subgrid. */
const towerRows = (part: GridRows, tower: GridRows) => `${part.start - tower.start + 1} / ${part.end - tower.start + 1}`
const floorRows = (baseKm: number, topKm: number) => `${gridLineForKm(topKm)} / ${gridLineForKm(baseKm)}`
const groundColumns = (lanes: number[]) => `main-start / ${lanes.length ? `lane-${Math.max(...lanes)}-end` : 'main-end'}`

interface CloudSkyDiagramProps {
  /** Takes the user to the full catalog card of a cloud. */
  onOpenCard: (id: CloudId) => void
}

export function CloudSkyDiagram({ onOpenCard }: CloudSkyDiagramProps) {
  const headingId = useId()

  function chip(placement: SkyPlacement, variant: string, style?: CSSProperties) {
    const cloud = CLOUD_BY_ID.get(placement.cloudId)!
    return <SkyChip key={cloud.id} cloud={cloud} variant={variant} onSelect={onOpenCard} style={style} />
  }

  return (
    <section className="sky" aria-labelledby={headingId}>
      <h2 id={headingId} className="sky__title">¿A qué altura está cada nube?</h2>
      <p className="sky__lead">Tocá una nube para ir a su ficha.</p>

      <div className="sky__layout">
        <div className="sky__figure">
          <div className="sky__plot">
            {/* Floor bands and axis (decoration: the groups below carry the floor names) */}
            {SKY_FLOORS.map(floor => (
              <div
                key={floor.id}
                className={`sky-band sky-band--${floor.id}`}
                style={{ gridRow: floorRows(floor.baseKm, floor.topKm) }}
                aria-hidden="true"
              />
            ))}
            <div className="sky-band sky-band--ground" style={{ gridRow: rows(LAYOUT.ground) }} aria-hidden="true" />
            {SKY_FLOORS.map(floor => (
              <p key={floor.id} className="sky-axis" style={{ gridRow: `${gridLineForKm(floor.topKm)} / span 1` }} aria-hidden="true">
                <b>{floor.axisLabel}</b>
                {floor.name && <span>{floor.name}</span>}
              </p>
            ))}
            <p className="sky-axis sky-axis--ground" style={{ gridRow: `${GROUND_LINE} / span 1` }} aria-hidden="true">
              <b>0 m</b>
              <span>Suelo</span>
            </p>
            <p className="sky-caption" style={{ gridRow: rows(LAYOUT.floorCells.cima) }} aria-hidden="true">
              Yunque del Cb →
            </p>

            {/* Clouds that live inside one floor */}
            {FLOOR_AREA.map(floorId => {
              const floor = SKY_FLOORS.find(f => f.id === floorId)!
              const inFloor = LAYOUT.placements.filter(p => p.area === 'floor' && p.floor === floorId)
              if (inFloor.length === 0) return null
              return (
                <div
                  key={floorId}
                  role="group"
                  aria-label={floor.groupLabel}
                  className="sky-floor"
                  style={{ gridRow: rows(LAYOUT.floorCells[floorId]) }}
                >
                  <p className="sky-list-label" aria-hidden="true">{FLOOR_LIST_LABELS[floorId]}</p>
                  {inFloor.map(p => chip(p, 'layer'))}
                </div>
              )
            })}

            {/* Vertical strips that cross from the low floor into the middle one */}
            <p className="sky-list-label sky-list-label--solo" aria-hidden="true">Cruzan del piso bajo al medio</p>
            {COLUMNS.map(p => chip(p, 'column', { gridRow: rows(p.rows), gridColumn: `lane-${p.lane}` }))}

            {/* Cumulonimbus: anvil over the free lanes, mammatus hanging under its overhang */}
            {TOWER && (
              <CumulonimbusTower
                rows={TOWER.rows}
                anvilBottomLine={LAYOUT.anvil.end}
                wideBottomLine={LAYOUT.wideBody.end}
                baseLine={LAYOUT.cbBase.start}
              >
                {TOWER_ACCESSORIES.map(p =>
                  chip(p, 'accessory', { gridRow: towerRows(p.rows, TOWER.rows), gridColumn: p.lane ?? 1 }),
                )}
                {/* Centred on the tower lane, over the trunk (column 3 of the tower subgrid). */}
                {chip(TOWER, 'tower', { gridRow: towerRows(LAYOUT.cbBody, TOWER.rows), gridColumn: -2 })}
              </CumulonimbusTower>
            )}

            {/* Fog: resting on the ground line, never below it */}
            {GROUND.map(p => chip(p, 'ground', { gridRow: rows(p.rows), gridColumn: groundColumns(p.lanes) }))}
          </div>
        </div>

        <div className="sky__tools">
          <p className="sky__legend">Franjas por piso, no a escala.</p>
        </div>
      </div>
    </section>
  )
}

interface SkyChipProps {
  cloud: CloudItem
  variant: string
  onSelect: (id: CloudId) => void
  style?: CSSProperties
}

function SkyChip({ cloud, variant, onSelect, style }: SkyChipProps) {
  const { name, note } = diagramLabel(cloud)
  return (
    <button
      type="button"
      className={`sky-chip sky-chip--${variant}`}
      onClick={() => onSelect(cloud.id)}
      style={{ ...style, '--sky-accent': cloud.sky.accent } as CSSProperties}
    >
      <CloudGlyph cloudId={cloud.id} className="sky-glyph" />
      <span className="sky-chip__text">
        <span className="sky-chip__name">{name}</span>
        {note && (
          <>
            <span className="sr-only">, </span>
            <span className="sky-chip__note">{keepUnitsTogether(note)}</span>
          </>
        )}
      </span>
      {cloud.dangerLevel >= 5 && (
        <>
          <span className="sky-chip__alert" aria-hidden="true">!</span>
          <span className="sr-only">, peligro máximo</span>
        </>
      )}
    </button>
  )
}
