import { Droplets } from 'lucide-react'
import { cn } from '@/lib/utils'

interface RainPillProps {
  /** El texto ya armado ("Lluvia 40 %", "Lluvia 40–60 % · poca cantidad"): ver describeRain. */
  label: string
  /** Franja con lluvia prevista ("14–17 h"). Va debajo de la pastilla, o al lado con `inline`. */
  window?: string
  /** La franja a la derecha de la pastilla, para las filas de la lista de 7 días. */
  inline?: boolean
}

/** Precipitación de un día, siempre en celeste: lluvia se lee igual en todas las vistas. */
export function RainPill({ label, window, inline = false }: RainPillProps) {
  return (
    <span className={cn('inline-flex', inline ? 'items-center gap-1.5' : 'flex-col items-center gap-0.5 text-center')}>
      <span
        className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium leading-snug"
        style={{
          background: 'rgba(90,170,216,0.12)',
          border: '1px solid rgba(90,170,216,0.3)',
          color: 'var(--color-info)',
        }}
      >
        <Droplets size={12} strokeWidth={2} aria-hidden="true" className="shrink-0" />
        {label}
      </span>
      {window && (
        <span className="text-[11px]" style={{ color: 'var(--color-info)' }}>
          {window}
        </span>
      )}
    </span>
  )
}
