import { DATA_SOURCES } from '@/data/dataSources'
import { CAFECITO_URL, OPEN_METEO_LICENCE_URL, OPEN_METEO_URL } from '@/lib/siteLinks'

const LINK_CLASS = 'inline-flex min-h-[44px] items-center underline hover:opacity-80'

/**
 * "De dónde salen los datos" (FRA-347): the main views never name a weather model, so whoever wants to
 * learn finds the whole explanation here. The text comes from `data/dataSources.ts`.
 */
export function DatosFuentes() {
  return (
    <div className="max-w-2xl mx-auto py-8 space-y-6">
      <h1
        tabIndex={-1}
        className="text-2xl focus:outline-none"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
      >
        De dónde salen los datos
      </h1>
      <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
        SkyPulse junta datos de fuentes públicas de meteorología, sismología y vigilancia volcánica. Acá explicamos, en criollo, de dónde sale cada cosa.
      </p>

      {DATA_SOURCES.map(source => (
        <section key={source.id} id={source.id} className="space-y-1.5">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
            {source.title}
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            {source.summary}
          </p>
          {source.providers.length > 0 && (
            <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
              <span style={{ color: 'var(--color-foreground)' }}>Fuentes: </span>
              {source.providers.join(' · ')}
            </p>
          )}
        </section>
      ))}

      <section id="creditos" className="space-y-1.5">
        <h2 className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
          Créditos y licencia
        </h2>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
          Datos del tiempo:{' '}
          <a href={OPEN_METEO_URL} target="_blank" rel="noopener noreferrer" className="underline hover:opacity-80">
            Open-Meteo.com
          </a>
          . Los datos de Open-Meteo se publican bajo la licencia CC BY 4.0.
        </p>
        <a href={OPEN_METEO_LICENCE_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS} style={{ color: 'var(--color-muted-foreground)' }}>
          Ver la licencia de Open-Meteo
        </a>
      </section>

      <section id="apoya" className="space-y-1.5">
        <h2 className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
          Apoyá SkyPulse
        </h2>
        <p className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
          Si SkyPulse te sirve, podés contribuir con un cafecito. Es voluntario y no desbloquea nada: todas las funciones son iguales para todos.
        </p>
        <a href={CAFECITO_URL} target="_blank" rel="noopener noreferrer" className={LINK_CLASS} style={{ color: 'var(--color-muted-foreground)' }}>
          Contribuir en Cafecito
        </a>
      </section>
    </div>
  )
}
