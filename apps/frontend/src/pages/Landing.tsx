import { type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '@iconify/react'
import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'

interface Item {
  to: string
  icon: string | ReactNode
  title: string
  desc: string
  color: string
}

const P = (name: string): ReactNode => (
  <img src={`/icons/icon-${name}.png`} width={28} height={28} style={{ objectFit: 'contain' }} alt="" />
)

const TOOLS: Item[] = [
  {
    to: '/prevision',
    icon: P('prevision'),
    title: 'Previsión del clima',
    desc: 'Temperatura, viento y pronóstico 7 días. Modelos GFS y ECMWF.',
    color: '#c8a84b',
  },
  {
    to: '/hacer-deporte',
    icon: 'solar:running-2-bold-duotone',
    title: 'Hacer deporte',
    desc: '¿Las condiciones acompañan? UV, humedad, viento y sensación térmica.',
    color: '#f0a030',
  },
  {
    to: '/tender-ropa',
    icon: P('tender'),
    title: 'Secado de ropa',
    desc: 'Los mejores días para tender según lluvia, viento y humedad.',
    color: '#3ecf7a',
  },
  {
    to: '/lavar-auto',
    icon: P('lavar'),
    title: 'Lavar el auto',
    desc: 'El día ideal de la semana para lavar sin que la lluvia lo arruine.',
    color: '#5aaad8',
  },
  {
    to: '/terremotos',
    icon: <img src="/icons/icon-terremotos.png" width={28} height={28} style={{ objectFit: 'contain', filter: 'brightness(0) invert(1) opacity(0.85)' }} alt="" />,
    title: 'Terremotos',
    desc: 'Sismos recientes cerca tuyo, con magnitud y distancia en tiempo real.',
    color: '#e05545',
  },
  {
    to: '/cota-de-nieve',
    icon: 'solar:snowflake-bold-duotone',
    title: 'Cota de nieve',
    desc: '¿Hasta qué altura llega la nieve en la cordillera hoy?',
    color: '#90aabb',
  },
  {
    to: '/volcanes',
    icon: 'mingcute:mountain-line',
    title: 'Volcanes',
    desc: 'Estado de alerta de los principales volcanes del país.',
    color: '#e05545',
  },
  {
    to: '/incendios',
    icon: P('incendios'),
    title: 'Incendios',
    desc: 'Riesgo de incendio forestal según temperatura, viento y humedad.',
    color: '#f0a030',
  },
  {
    to: '/niebla',
    icon: 'solar:fog-bold-duotone',
    title: 'Niebla y visibilidad',
    desc: 'Visibilidad actual y pronóstico de niebla hora a hora.',
    color: '#90aabb',
  },
  {
    to: '/metar',
    icon: P('metar'),
    title: 'METAR & TAF',
    desc: 'Reporte meteorológico real de cualquier aeródromo del mundo.',
    color: '#8b9fc4',
  },
]

const GUIDES: Item[] = [
  {
    to: '/nubes',
    icon: 'solar:cloud-bold-duotone',
    title: 'Catálogo del cielo',
    desc: '13 tipos de nubes y 5 fenómenos aeronáuticos con escalas de peligro.',
    color: '#c8a84b',
  },
  {
    to: '/lluvias',
    icon: 'solar:cloud-rain-bold-duotone',
    title: 'Lluvias según las nubes',
    desc: 'Qué lluvia esperar según el tipo de nube en el cielo.',
    color: '#5aaad8',
  },
  {
    to: '/radar',
    icon: 'solar:radar-bold-duotone',
    title: 'Radar y satélite',
    desc: 'Cómo interpretar colores de radar e imágenes satelitales IR.',
    color: '#7dd3fc',
  },
  {
    to: '/desastres',
    icon: P('desastres'),
    title: 'Desastres naturales',
    desc: '7 fenómenos globales: datos históricos, fuentes y qué hacer.',
    color: '#e05545',
  },
]

const SOURCE_PILLS = ['SMN', 'GFS', 'ECMWF', 'USGS', 'EMSC']

export function Landing() {
  return (
    <div className="relative py-8">
      <Dither opacity={0.04} />

      <FadeContent>
        {/* Hero */}
        <div className="mb-12 text-center">
          <h1
            className="text-4xl sm:text-5xl font-semibold tracking-tight mb-3"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Sky<span style={{ color: 'var(--color-primary)' }}>Pulse</span>
          </h1>

          <p
            className="text-base sm:text-lg font-medium mb-3"
            style={{ color: 'var(--color-foreground)' }}
          >
            Meteorología que se entiende y se usa.
          </p>

          <p
            className="text-sm sm:text-base max-w-md mx-auto mb-6 leading-relaxed"
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            Convierte datos del cielo en respuestas concretas para el día a día.
            Sin tecnicismos, sin ambigüedad.
          </p>

          <div className="flex gap-2 justify-center flex-wrap">
            {SOURCE_PILLS.map(s => (
              <span
                key={s}
                className="text-[10px] font-semibold px-2.5 py-1 rounded-full tracking-widest uppercase"
                style={{
                  background: 'rgba(200,168,75,0.07)',
                  border: '1px solid rgba(200,168,75,0.18)',
                  color: 'rgba(200,168,75,0.65)',
                }}
              >
                {s}
              </span>
            ))}
          </div>
        </div>

        {/* Herramientas */}
        <p className="text-xs font-medium tracking-widest uppercase mb-3" style={{ color: 'rgba(200,168,75,0.5)' }}>
          Herramientas
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {TOOLS.map((item) => <ItemCard key={item.to} {...item} />)}
        </div>

        {/* Guías */}
        <p className="text-xs font-medium tracking-widest uppercase mt-8 mb-3" style={{ color: 'rgba(200,168,75,0.5)' }}>
          Guías meteorológicas
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {GUIDES.map((item) => <ItemCard key={item.to} {...item} />)}
        </div>
      </FadeContent>
    </div>
  )
}

function ItemCard({ to, icon, title, desc, color }: Item) {
  return (
    <Link
      to={to}
      className="flex flex-col gap-3 p-5 rounded-xl"
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
        className="size-10 rounded-lg flex items-center justify-center shrink-0"
        style={{ background: `${color}1a`, color }}
      >
        {typeof icon === 'string'
          ? <Icon icon={icon} width={20} height={20} aria-hidden="true" />
          : icon}
      </div>
      <div>
        <h2 className="font-semibold mb-1" style={{ color: 'var(--color-foreground)' }}>
          {title}
        </h2>
        <p className="text-sm leading-snug" style={{ color: 'var(--color-muted-foreground)' }}>
          {desc}
        </p>
      </div>
    </Link>
  )
}
