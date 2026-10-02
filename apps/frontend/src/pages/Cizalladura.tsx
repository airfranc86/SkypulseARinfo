import { WindArrowDown } from 'lucide-react'
import { PageHeader } from '@/components/ui/PageHeader'
import type { LocationState } from '@/hooks/useLocation'
import { WindShearWidget } from '@/components/aeronautica/WindShearWidget'

const ACCENT = '#c4b08f'

interface CizalladuraProps {
  location?: LocationState | null
}

export function Cizalladura({ location }: CizalladuraProps = {}) {
  return (
    <div>
      <PageHeader
        icon={<WindArrowDown size={32} style={{ color: ACCENT }} />}
        title="Cizalladura / LLWS"
        subtitle="Qué tan brusco cambia el viento entre el suelo y 1.000 ft, antes de aterrizar"
        accentColor={ACCENT}
      />
      <WindShearWidget location={location} />
    </div>
  )
}
