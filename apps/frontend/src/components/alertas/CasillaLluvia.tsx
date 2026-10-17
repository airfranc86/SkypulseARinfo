import { Link } from 'react-router-dom'
import { COPY, RUTA_PRIVACIDAD, mensajeDeLluvia } from '@/lib/alertas/copy'
import type { EstadoLluvia } from '@/lib/alertas/lluvia'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

interface CasillaLluviaProps {
  marcada: boolean
  estado: EstadoLluvia
  onCambio: (marcada: boolean) => void
  /** El enlace a la política de privacidad: solo cuando no hay otro consentimiento a la vista que ya lo traiga. */
  conEnlacePrivacidad: boolean
}

/**
 * La casilla del aviso de lluvia persistente (opt-in): desmarcada de entrada, con su propio consentimiento, y visible
 * también con los avisos activos (ahí, al tocarla, se reenvía el alta con la preferencia). Es independiente de la
 * casilla del consentimiento general: quien no la tilda sigue recibiendo solo los avisos de tormenta. No pide ni toca el
 * permiso del navegador. El mensaje de estado va siempre montado, para que el lector de pantalla anuncie el resultado.
 */
export function CasillaLluvia({ marcada, estado, onCambio, conEnlacePrivacidad }: CasillaLluviaProps) {
  return (
    <div className="space-y-1">
      <label className="flex min-h-11 cursor-pointer items-start gap-3 py-2 text-sm leading-relaxed text-[var(--color-foreground)]">
        <input
          type="checkbox"
          checked={marcada}
          onChange={(event) => onCambio(event.target.checked)}
          className={`mt-0.5 size-6 shrink-0 cursor-pointer accent-[color:var(--color-primary)] ${FOCUS_RING}`}
        />
        <span>{COPY.consentimientoLluvia}</span>
      </label>
      {conEnlacePrivacidad && (
        <Link
          to={RUTA_PRIVACIDAD}
          className={`inline-flex min-h-11 items-center rounded-md px-1 text-sm underline underline-offset-4 hover:opacity-80 ${FOCUS_RING}`}
          style={{ color: 'var(--color-primary)' }}
        >
          {COPY.enlacePrivacidad}
        </Link>
      )}
      <p role="status" aria-live="polite" className="text-sm text-[var(--color-muted-foreground)]">
        {mensajeDeLluvia(estado)}
      </p>
    </div>
  )
}
