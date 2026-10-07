import { Link } from 'react-router-dom'
import { COPY, RUTA_PRIVACIDAD } from '@/lib/alertas/copy'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

interface ConsentimientoAvisosProps {
  marcado: boolean
  onCambio: (marcado: boolean) => void
}

/**
 * La casilla obligatoria para activar los avisos, con el enlace a la política de privacidad. Sin tildarla
 * "Activar avisos" queda deshabilitado (lo decide `puedeActivar`). El enlace va fuera de la etiqueta para que
 * tocarlo no tilde la casilla.
 */
export function ConsentimientoAvisos({ marcado, onCambio }: ConsentimientoAvisosProps) {
  return (
    <div className="space-y-1">
      <label className="flex min-h-11 cursor-pointer items-start gap-3 py-2 text-sm leading-relaxed text-[var(--color-foreground)]">
        <input
          type="checkbox"
          checked={marcado}
          onChange={(event) => onCambio(event.target.checked)}
          className={`mt-0.5 size-6 shrink-0 cursor-pointer accent-[color:var(--color-primary)] ${FOCUS_RING}`}
        />
        <span>{COPY.consentimiento}</span>
      </label>
      <Link
        to={RUTA_PRIVACIDAD}
        className={`inline-flex min-h-11 items-center rounded-md px-1 text-sm underline underline-offset-4 hover:opacity-80 ${FOCUS_RING}`}
        style={{ color: 'var(--color-primary)' }}
      >
        {COPY.enlacePrivacidad}
      </Link>
    </div>
  )
}
