interface ErrorMessageProps {
  message: string
}

/** Shared error display — replaces the copy-pasted ErrorMessage in every page. */
export function ErrorMessage({ message }: ErrorMessageProps) {
  return (
    <div
      className="rounded-xl p-4 text-sm"
      role="alert"
      style={{
        border: '1px solid rgba(224,85,69,0.3)',
        background: 'rgba(224,85,69,0.05)',
        color: 'var(--color-destructive)',
      }}
    >
      Error: {message}
    </div>
  )
}
