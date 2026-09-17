interface CookieConsentBannerProps {
  onAccept: () => void
  onReject: () => void
}

/** Banner de consentimiento de analítica (GTM + Vercel Analytics) — sin preselección. */
export function CookieConsentBanner({ onAccept, onReject }: CookieConsentBannerProps) {
  return (
    <div
      role="dialog"
      aria-label="Consentimiento de cookies"
      style={{
        position: 'fixed',
        bottom: 0,
        insetInline: 0,
        zIndex: 60,
        borderTop: '1px solid var(--color-border)',
        background: 'color-mix(in srgb, var(--color-background) 92%, transparent)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
      }}
    >
      <div
        className="max-w-5xl mx-auto px-4 py-3 flex flex-col sm:flex-row items-start sm:items-center gap-3"
      >
        <p className="text-xs flex-1" style={{ color: 'var(--color-muted-foreground)' }}>
          Usamos cookies de analítica (Google Tag Manager, Vercel Analytics) para entender cómo se usa SkyPulse. Podés aceptarlas o rechazarlas.
        </p>
        <div className="flex gap-2 shrink-0">
          <button
            type="button"
            onClick={onReject}
            className="text-xs font-medium rounded-full px-3 py-1.5 transition-opacity hover:opacity-80"
            style={{
              background: 'transparent',
              color: 'var(--color-foreground)',
              border: '1px solid var(--color-border)',
            }}
          >
            Rechazar
          </button>
          <button
            type="button"
            onClick={onAccept}
            className="text-xs font-medium rounded-full px-3 py-1.5 transition-opacity hover:opacity-80"
            style={{
              background: 'var(--color-primary)',
              color: 'var(--color-background)',
              border: '1px solid var(--color-primary)',
            }}
          >
            Aceptar
          </button>
        </div>
      </div>
    </div>
  )
}
