import { SMN_URL } from '@/lib/smnAlertas'

/**
 * Pie de la previsión: un enlace discreto a la fuente oficial, no un aviso. Se muestra siempre (con avisos,
 * sin avisos o con el SMN caído). Sin ícono ni estilo de alerta, sin `role="alert"` ni región viva, y solo se
 * monta cuando ya hay pronóstico o error final (no reserva espacio). El texto es chico pero el área táctil
 * llega a 44 px de alto.
 */
export function SmnFallbackLink() {
  return (
    <div className="mt-4 text-center">
      <a
        href={SMN_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center min-h-[44px] px-3 text-[11px] underline hover:opacity-80"
        style={{ color: 'var(--color-muted-foreground)' }}
      >
        Consulta oficial: smn.gob.ar
      </a>
    </div>
  )
}
