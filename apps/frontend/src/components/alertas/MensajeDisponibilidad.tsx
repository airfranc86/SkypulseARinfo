import { TriangleAlert } from 'lucide-react'
import { mensajeDeDisponibilidad } from '@/lib/alertas/copy'
import type { Disponibilidad } from '@/lib/alertas/plataforma'

interface MensajeDisponibilidadProps {
  disponibilidad: Exclude<Disponibilidad, { tipo: 'activar' | 'instalar-ios' }>
}

/**
 * Cuando no se puede activar desde acá: el navegador interno de Instagram o Facebook (hay que abrir la página
 * en otro navegador) o un navegador sin soporte. El ícono acompaña al texto, que dice todo por sí solo.
 */
export function MensajeDisponibilidad({ disponibilidad }: MensajeDisponibilidadProps) {
  return (
    <section
      className="flex items-start gap-3 rounded-xl p-4 text-sm leading-relaxed"
      style={{
        border: '1px solid rgba(240,160,48,0.4)',
        background: 'rgba(240,160,48,0.08)',
        color: 'var(--color-foreground)',
      }}
    >
      <TriangleAlert
        size={18}
        strokeWidth={2}
        className="mt-0.5 shrink-0"
        style={{ color: 'var(--color-watch)' }}
        aria-hidden="true"
      />
      <p>{mensajeDeDisponibilidad(disponibilidad)}</p>
    </section>
  )
}
