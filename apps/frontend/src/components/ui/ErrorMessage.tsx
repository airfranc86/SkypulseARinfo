interface ErrorMessageProps {
  message: string
  onRetry?: () => void
}

/** Shared error display — replaces the copy-pasted ErrorMessage in every page. */
export function ErrorMessage({ message, onRetry }: ErrorMessageProps) {
  return (
    <div
      className="rounded-xl p-4 text-sm flex items-center justify-between gap-3 flex-wrap"
      role="alert"
      style={{
        border: '1px solid rgba(224,85,69,0.35)',
        background: 'rgba(224,85,69,0.08)',
        color: 'var(--color-crit-soft)',
      }}
    >
      <span>{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-medium rounded-full px-4 min-h-[44px] shrink-0 transition-opacity hover:opacity-80"
          style={{ background: 'rgba(224,85,69,0.14)', color: '#e05545', border: '1px solid rgba(224,85,69,0.4)' }}
        >
          Reintentar
        </button>
      )}
    </div>
  )
}
