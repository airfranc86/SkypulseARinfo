import { Link } from 'react-router-dom'

const SUGGESTIONS = [
  { to: '/prevision', label: 'Previsión del clima' },
  { to: '/terremotos', label: 'Terremotos' },
  { to: '/nubes', label: 'Catálogo del cielo' },
]

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center text-center py-20 gap-4">
      <p
        className="text-6xl font-bold"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-primary)' }}
      >
        404
      </p>
      <h1
        className="text-xl"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
      >
        Esta página no existe
      </h1>
      <p className="text-sm max-w-sm" style={{ color: 'var(--color-muted-foreground)' }}>
        Puede que el enlace esté roto o que la URL tenga un error. Volvé al inicio o probá alguna de estas herramientas.
      </p>

      <Link
        to="/"
        className="mt-2 text-sm font-medium rounded-full px-4 py-2 transition-opacity hover:opacity-80"
        style={{
          background: 'var(--color-primary)',
          color: 'var(--color-background)',
        }}
      >
        Volver al inicio
      </Link>

      <div className="flex flex-wrap justify-center gap-2 mt-4">
        {SUGGESTIONS.map(s => (
          <Link
            key={s.to}
            to={s.to}
            className="text-xs rounded-full px-3 py-1.5 transition-opacity hover:opacity-80"
            style={{
              border: '1px solid var(--color-border)',
              color: 'var(--color-muted-foreground)',
            }}
          >
            {s.label}
          </Link>
        ))}
      </div>
    </div>
  )
}
