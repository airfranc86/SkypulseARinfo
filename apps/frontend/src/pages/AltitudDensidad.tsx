import { Gauge } from 'lucide-react'
import { PageHeader } from '@/components/ui/PageHeader'
import { DensityAltitudeWidget } from '@/components/aeronautica/DensityAltitudeWidget'

const ACCENT = '#8fc4a8'

export function AltitudDensidad() {
  return (
    <div>
      <PageHeader
        icon={<Gauge size={32} style={{ color: ACCENT }} />}
        title="Altitud de densidad"
        subtitle="Qué le hace el aire de hoy a tu velamen y a la aeronave de salto"
        accentColor={ACCENT}
      />
      <DensityAltitudeWidget />
    </div>
  )
}
