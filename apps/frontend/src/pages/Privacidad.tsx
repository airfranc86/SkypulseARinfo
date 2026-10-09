import { leerContactoPrivacidad, SECCIONES_PRIVACIDAD, type ContactoPrivacidad } from '@/lib/privacidad'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

/** El contacto sale del entorno de build (`VITE_PRIVACY_CONTACT_EMAIL`, en Vercel): en el repo no hay ninguna dirección. */
const CONTACTO = leerContactoPrivacidad(import.meta.env)

/**
 * El botón abre el correo que la persona tenga configurado; la dirección queda a la vista para copiarla.
 * Sin dirección configurada no hay botón ni dirección: solo el aviso, sin inventar ninguna.
 */
function Contacto({ contacto }: { contacto: ContactoPrivacidad | null }) {
  if (contacto === null) {
    return (
      <p className="pt-1 text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
        Por ahora no hay un correo de contacto publicado en esta página.
      </p>
    )
  }
  return (
    <div className="space-y-2 pt-1">
      <a
        href={contacto.mailto}
        className={`inline-flex min-h-11 w-full items-center justify-center rounded-lg bg-[var(--color-primary)] px-5 py-2 text-center text-sm font-medium text-[var(--color-primary-foreground)] transition-colors hover:opacity-90 motion-reduce:transition-none sm:w-auto ${FOCUS_RING}`}
      >
        Escribirnos por email
      </a>
      <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
        Si el botón no abre tu correo, escribinos a{' '}
        <span className="select-all font-medium" style={{ color: 'var(--color-foreground)' }}>
          {contacto.email}
        </span>
        .
      </p>
    </div>
  )
}

export function Privacidad() {
  return (
    <div className="max-w-2xl mx-auto py-8 space-y-6">
      <h1
        className="text-2xl"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
      >
        Política de privacidad
      </h1>
      <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
        SkyPulse es una herramienta de consulta meteorológica y sísmica sin registro de usuarios. Esta página explica, en criollo, qué datos tocamos y para qué.
      </p>

      {SECCIONES_PRIVACIDAD.map(s => (
        <section key={s.titulo} className="space-y-1.5">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
            {s.titulo}
          </h2>
          {s.parrafos.map(p => (
            <p key={p} className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
              {p}
            </p>
          ))}
          {s.contacto === true && <Contacto contacto={CONTACTO} />}
        </section>
      ))}
    </div>
  )
}
