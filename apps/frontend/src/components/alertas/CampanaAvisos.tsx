import { NavLink } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { NOMBRE_CAMPANA } from '@/lib/alertas/copy'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

/**
 * La campana del header: un enlace a `/alertas` de 44 px, con su nombre accesible (el ícono es decorativo).
 * Quien la monta decide si se ve (`config.visible`, la bandera `VITE_ALERTAS_VISIBLE`): acá no se lee el entorno.
 */
export function CampanaAvisos() {
  return (
    <NavLink
      to="/alertas"
      aria-label={NOMBRE_CAMPANA}
      title={NOMBRE_CAMPANA}
      className={`inline-flex size-11 shrink-0 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] text-[var(--color-foreground)] transition-colors motion-reduce:transition-none hover:bg-[var(--color-accent)] aria-[current=page]:border-[var(--color-primary)] aria-[current=page]:text-[var(--color-primary)] ${FOCUS_RING}`}
    >
      <Bell className="size-5" aria-hidden="true" />
    </NavLink>
  )
}
