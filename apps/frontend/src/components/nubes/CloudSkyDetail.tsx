import type { Ref } from 'react'
import type { CloudId, CloudItem } from '@/data/clouds'
import { keepUnitsTogether, skyFicha } from '@/lib/cloudSky'
import { DangerScale } from '@/components/ui/DangerScale'
import { StatusBadge } from './StatusBadge'

interface CloudSkyDetailProps {
  id: string
  cloud: CloudItem | null
  panelRef?: Ref<HTMLElement>
  onOpenCard?: (id: CloudId) => void
}

/** "Qué indica" card of the cloud chosen in the diagram; every text comes from the catalog (`skyFicha`). */
export function CloudSkyDetail({ id, cloud, panelRef, onOpenCard }: CloudSkyDetailProps) {
  return (
    <section ref={panelRef} id={id} className="sky-detail" aria-label="Qué indica la nube elegida" aria-live="polite">
      {cloud ? (
        <Ficha cloud={cloud} onOpenCard={onOpenCard} />
      ) : (
        <p className="sky-detail__empty">Elegí una nube del diagrama: acá vas a ver qué indica y cómo reconocerla.</p>
      )}
    </section>
  )
}

function Ficha({ cloud, onOpenCard }: { cloud: CloudItem; onOpenCard?: (id: CloudId) => void }) {
  const f = skyFicha(cloud)
  return (
    <>
      <p className="sky-detail__eyebrow">{f.familyTitle}</p>
      <h3 className="sky-detail__name">{f.name}</h3>
      <p className="sky-detail__latin">{f.latin}</p>

      <div className="sky-detail__level">
        <div className="sky-detail__scale">
          <DangerScale level={f.dangerLevel} />
        </div>
        <span>Nivel {f.dangerLevel} de 5</span>
      </div>

      <dl className="sky-detail__facts">
        <div>
          <dt>Altura</dt>
          <dd>{keepUnitsTogether(f.rangeLabel)}</dd>
        </div>
        <div>
          <dt>Qué indica</dt>
          <dd>
            <p className="sky-detail__says">{f.indicates}</p>
            {f.indicates !== f.badgeLabel && (
              <p className="sky-detail__badge">
                <StatusBadge variant={f.badge} label={f.badgeLabel} />
              </p>
            )}
          </dd>
        </div>
        <div>
          <dt>Cómo reconocerla</dt>
          <dd>{f.recognize}</dd>
        </div>
        <div>
          <dt>Rasgo</dt>
          <dd>{f.composition}</dd>
        </div>
      </dl>

      {onOpenCard && (
        <button type="button" className="sky-detail__more" onClick={() => onOpenCard(cloud.id)}>
          Ver la ficha completa
          <span aria-hidden="true">↓</span>
        </button>
      )}
    </>
  )
}
