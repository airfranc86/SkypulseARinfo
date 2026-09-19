import { TriangleAlert } from 'lucide-react'

interface ErrorMessageProps {
  message: string
  onRetry?: () => void
}

/**
 * Shared error display — replaces the copy-pasted ErrorMessage in every page.
 * En ámbar, no en rojo: un fallo de red no es un peligro, y el rojo se reserva para los avisos de
 * gravedad real (principio 3 de PRODUCT.md). El texto va en el color de lectura, no en el de acento.
 */
export function ErrorMessage({ message, onRetry }: ErrorMessageProps) {
  return (
    <div
      className="rounded-xl p-4 text-sm flex items-center justify-between gap-3 flex-wrap"
      role="alert"
      style={{
        border: '1px solid rgba(240,160,48,0.4)',
        background: 'rgba(240,160,48,0.08)',
        color: 'var(--color-foreground)',
      }}
    >
      <span className="flex items-start gap-2">
        <TriangleAlert size={18} strokeWidth={2} className="mt-0.5 shrink-0" style={{ color: 'var(--color-watch)' }} aria-hidden="true" />
        <span>{message}</span>
      </span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-medium rounded-full px-4 min-h-[44px] shrink-0 transition-opacity hover:opacity-80"
          style={{ background: 'rgba(240,160,48,0.16)', color: '#f5c542', border: '1px solid rgba(240,160,48,0.5)' }}
        >
          Reintentar
        </button>
      )}
    </div>
  )
}
