import { Droplets } from 'lucide-react'
import { cn } from '@/lib/utils'

interface RainPillProps {
  /** Tipo de precipitación del ícono del día ("Lluvia", "Nieve"…). */
  kind: string
  /** Probabilidad diaria, en porcentaje. */
  pct: number
  /** Franja con lluvia prevista ("14–17 h"). Va debajo de la pastilla, o al lado con `inline`. */
  window?: string
  /** La franja a la derecha de la pastilla, para las filas de la lista de 7 días. */
  inline?: boolean
}

/** Precipitación de un día, siempre en celeste: lluvia se lee igual en todas las vistas. */
export function RainPill({ kind, pct, window, inline = false }: RainPillProps) {
  return (
    <span className={cn('inline-flex', inline ? 'items-center gap-1.5' : 'flex-col items-center gap-0.5 text-center')}>
      <span
        className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
        style={{
          background: 'rgba(90,170,216,0.12)',
          border: '1px solid rgba(90,170,216,0.3)',
          color: 'var(--color-info)',
        }}
      >
        <Droplets size={12} strokeWidth={2} aria-hidden="true" />
        {kind} {Math.round(pct)}%
      </span>
      {window && (
        <span className="text-[11px]" style={{ color: 'var(--color-info)' }}>
          {window}
        </span>
      )}
    </span>
  )
}
