import { Link } from 'react-router-dom'
import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'
import { ModelBadge } from '@/components/ui/ModelBadge'
import type { ModelKey } from '@/components/ui/ModelBadge'

const GUIDES: Array<{
  to: string
  emoji: string
  title: string
  desc: string
  color: string
}> = [
  {
    to: '/nubes',
    emoji: '☁️',
    title: 'Catálogo del cielo',
    desc: '13 tipos de nubes + 5 fenómenos aeronáuticos con escalas de peligro.',
    color: '#c8a84b',
  },
  {
    to: '/metar',
    emoji: '📡',
    title: 'METAR & TAF',
    desc: 'Consultá el reporte real de cualquier aeródromo del mundo.',
    color: '#5aaad8',
  },
  {
    to: '/lluvias',
    emoji: '🌧️',
    title: 'Lluvias según las nubes',
    desc: 'Qué lluvia esperar según el tipo de nube en el cielo.',
    color: '#5aaad8',
  },
  {
    to: '/radar',
    emoji: '🛰️',
    title: 'Radar y satélite',
    desc: 'Cómo leer colores de radar e imágenes satelitales IR.',
    color: '#7dd3fc',
  },
  {
    to: '/desastres',
    emoji: '🌋',
    title: 'Desastres naturales',
    desc: '7 fenómenos globales: datos históricos, fuentes y qué hacer.',
    color: '#e05545',
  },
]

const TOOLS: Array<{
  to: string
  emoji: string
  title: string
  desc: string
  color: string
  model: ModelKey
}> = [
  {
    to: '/prevision',
    emoji: '⛅',
    title: 'Previsión del clima',
    desc: 'El tiempo de hoy y los próximos días, en un vistazo.',
    color: '#c8a84b',
    model: 'mixed',
  },
  {
    to: '/tender-ropa',
    emoji: '🌤️',
    title: 'Tender ropa',
    desc: '¿Es buen día para colgar la ropa afuera?',
    color: '#3ecf7a',
    model: 'gfs',
  },
  {
    to: '/lavar-auto',
    emoji: '🫧',
    title: 'Lavar el auto',
    desc: 'Los mejores días de la semana para lavar sin sorpresas.',
    color: '#5aaad8',
    model: 'gfs',
  },
  {
    to: '/terremotos',
    emoji: '🌋',
    title: 'Terremotos',
    desc: 'Sismos recientes cerca tuyo.',
    color: '#e05545',
    model: 'usgs',
  },
  {
    to: '/cota-de-nieve',
    emoji: '⛷️',
    title: 'Cota de nieve',
    desc: '¿Hasta dónde llega la nieve en la cordillera?',
    color: '#90aabb',
    model: 'gfs',
  },
  {
    to: '/niebla',
    emoji: '🌫️',
    title: 'Niebla y visibilidad',
    desc: 'Visibilidad actual y pronóstico de niebla hora a hora.',
    color: '#90aabb',
    model: 'openmeteo',
  },
]

export function Landing() {
  return (
    <div className="relative py-8">
      <Dither opacity={0.04} />

      <FadeContent>
        {/* Hero */}
        <div className="mb-12 text-center">
          <h1
            className="text-4xl sm:text-5xl font-semibold tracking-tight mb-4"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Previsión{' '}
            <span style={{ color: 'var(--color-primary)' }}>Meteorológica</span>
          </h1>
          <p
            className="text-base sm:text-lg max-w-sm mx-auto"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            Datos en tiempo real a demanda.
            <br />
            <span style={{ color: 'var(--color-foreground)', fontWeight: 500 }}>
              ¿Qué información necesitás?
            </span>
          </p>
        </div>

        {/* Tool grid */}
        <p className="text-xs font-medium tracking-widest uppercase mb-3" style={{ color: 'rgba(200,168,75,0.5)' }}>
          Herramientas
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {TOOLS.map(({ to, emoji, title, desc, color, model }) => (
            <Link
              key={to}
              to={to}
              className="group flex flex-col gap-3 p-5 rounded-xl"
              style={{
                position: 'relative',
                background: 'var(--color-card)',
                border: `1px solid ${color}2e`,
                transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
              }}
              onMouseEnter={e => {
                const el = e.currentTarget as HTMLAnchorElement
                el.style.borderColor = `${color}70`
                el.style.boxShadow = `0 0 20px ${color}16`
              }}
              onMouseLeave={e => {
                const el = e.currentTarget as HTMLAnchorElement
                el.style.borderColor = `${color}2e`
                el.style.boxShadow = 'none'
              }}
            >
              {/* Badge de modelo — esquina superior derecha */}
              <ModelBadge model={model} variant="inline" />

              <div
                className="size-10 rounded-lg flex items-center justify-center"
                style={{ background: `${color}1a`, color }}
              >
                <span className="text-2xl leading-none" role="img" aria-label={title}>{emoji}</span>
              </div>
              <div>
                <h2 className="font-semibold mb-1" style={{ color: 'var(--color-foreground)' }}>
                  {title}
                </h2>
                <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                  {desc}
                </p>
              </div>
            </Link>
          ))}
        </div>

        {/* Guides section */}
        <p className="text-xs font-medium tracking-widest uppercase mt-8 mb-3" style={{ color: 'rgba(200,168,75,0.5)' }}>
          Guías meteorológicas
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {GUIDES.map(({ to, emoji, title, desc, color }) => (
            <Link
              key={to}
              to={to}
              className="group flex flex-col gap-3 p-5 rounded-xl"
              style={{
                position: 'relative',
                background: 'var(--color-card)',
                border: `1px solid ${color}2e`,
                transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
              }}
              onMouseEnter={e => {
                const el = e.currentTarget as HTMLAnchorElement
                el.style.borderColor = `${color}70`
                el.style.boxShadow = `0 0 20px ${color}16`
              }}
              onMouseLeave={e => {
                const el = e.currentTarget as HTMLAnchorElement
                el.style.borderColor = `${color}2e`
                el.style.boxShadow = 'none'
              }}
            >
              <div
                className="size-10 rounded-lg flex items-center justify-center"
                style={{ background: `${color}1a`, color }}
              >
                <span className="text-2xl leading-none" role="img" aria-label={title}>{emoji}</span>
              </div>
              <div>
                <h2 className="font-semibold mb-1" style={{ color: 'var(--color-foreground)' }}>
                  {title}
                </h2>
                <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                  {desc}
                </p>
              </div>
            </Link>
          ))}
        </div>

      </FadeContent>
    </div>
  )
}
