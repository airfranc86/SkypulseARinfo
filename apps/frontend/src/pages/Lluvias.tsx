import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'
import { RainText } from '@/components/animated/RainText'

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

type BadgeVariant = 'no' | 'maybe' | 'yes' | 'heavy' | 'crit'
type IntensityLevel = 0 | 1 | 2 | 3 | 4

interface CloudRow {
  name: string
  badge: BadgeVariant
  badgeLabel: string
  intensity: IntensityLevel
  duration: string
  when: string
}

const CLOUDS: CloudRow[] = [
  { name: 'Cirros',         badge: 'no',    badgeLabel: 'No',             intensity: 0, duration: '—',                     when: 'Todo el año, especialmente antes de frentes' },
  { name: 'Cirrostratos',   badge: 'yes',   badgeLabel: 'En 12–24 h',     intensity: 1, duration: 'Prolongada',            when: 'Preceden frentes cálidos' },
  { name: 'Cirrocúmulos',   badge: 'no',    badgeLabel: 'No directa',     intensity: 0, duration: '—',                     when: 'Efímeros, señal de inestabilidad' },
  { name: 'Altocúmulos',    badge: 'maybe', badgeLabel: 'Posible',        intensity: 1, duration: 'Breve',                 when: 'Mañanas cálidas con Ac castellanus' },
  { name: 'Altostratos',    badge: 'yes',   badgeLabel: 'Sí',             intensity: 2, duration: 'Prolongada',            when: 'Siguen a los cirrostratos en frentes' },
  { name: 'Estrato',        badge: 'yes',   badgeLabel: 'Sí',             intensity: 1, duration: 'Larga, persistente',    when: 'Días fríos y húmedos, zonas costeras' },
  { name: 'Estratocúmulos', badge: 'maybe', badgeLabel: 'Llovizna posible', intensity: 1, duration: 'Breve',              when: 'Muy comunes, raramente llueven fuerte' },
  { name: 'Nimboestrato',   badge: 'heavy', badgeLabel: 'Sí — continua',  intensity: 3, duration: 'Muchas horas o días',  when: 'Frentes activos, invierno y otoño' },
  { name: 'Cúmulo',         badge: 'maybe', badgeLabel: 'Solo si crecen', intensity: 2, duration: 'Breve (chubasco)',      when: 'Tardes cálidas de verano' },
  { name: 'Cumulonimbo',    badge: 'crit',  badgeLabel: 'Sí — severa',    intensity: 4, duration: 'Corta pero intensa',   when: 'Verano, tarde-noche, zonas tropicales' },
  { name: 'Mammatus',       badge: 'crit',  badgeLabel: 'Tormenta activa', intensity: 4, duration: 'Variable, muy intensa', when: 'Bajo el yunque de un Cb severo' },
  { name: 'Niebla',         badge: 'yes',   badgeLabel: 'Llovizna fina',  intensity: 1, duration: 'Hasta que sube el sol', when: 'Madrugada y amanecer en valles' },
]

const BADGE_STYLES: Record<BadgeVariant, { color: string; bg: string; border: string }> = {
  no:    { color: '#90aabb', bg: 'rgba(96,112,128,.07)',  border: 'rgba(96,112,128,.28)'  },
  maybe: { color: 'var(--color-watch)', bg: 'rgba(212,135,15,.07)',  border: 'rgba(212,135,15,.32)'  },
  yes:   { color: 'var(--color-info)', bg: 'rgba(43,143,212,.07)',  border: 'rgba(43,143,212,.32)'  },
  heavy: { color: 'var(--color-warn)', bg: 'rgba(192,57,43,.07)',   border: 'rgba(192,57,43,.32)'   },
  crit:  { color: 'var(--color-crit-soft)', bg: 'rgba(255,0,0,.07)',     border: 'rgba(255,0,0,.32)'     },
}

const INTENSITY_COLORS: Record<IntensityLevel, string> = {
  0: 'transparent',
  1: '#5aaad8',
  2: '#f0a030',
  3: '#e05545',
  4: '#ff3333',
}

const INTENSITY_SCALE = [
  { label: 'Sin lluvia', color: '#2d3748' },
  { label: 'Llovizna',   color: '#5aaad8' },
  { label: 'Moderada',   color: '#f0a030' },
  { label: 'Intensa',    color: '#e05545' },
  { label: 'Severa',     color: '#ff3333' },
] as const

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function IntensityScaleBar() {
  return (
    <div
      className="rounded-xl p-4"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <p className="text-[.55rem] uppercase tracking-widest mb-3" style={{ color: 'var(--color-muted-foreground)' }}>
        Escala de intensidad
      </p>
      <div className="flex gap-[3px] h-[10px]">
        {INTENSITY_SCALE.map((item) => (
          <div key={item.label} className="flex-1 rounded-full" style={{ background: item.color }} />
        ))}
      </div>
      <div className="flex mt-2.5">
        {INTENSITY_SCALE.map((item) => (
          <div key={item.label} className="flex-1 text-center">
            <span className="text-[.48rem] leading-tight block" style={{ color: 'var(--color-muted-foreground)' }}>
              {item.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Badge({ variant, label }: { variant: BadgeVariant; label: string }) {
  const s = BADGE_STYLES[variant]
  return (
    <span
      className="inline-flex items-center text-[.68rem] font-medium px-2 py-0.5 rounded"
      style={{ color: s.color, background: s.bg, border: `1px solid ${s.border}` }}
    >
      {label}
    </span>
  )
}

function IntensityDots({ level }: { level: IntensityLevel }) {
  const activeColor = INTENSITY_COLORS[level]
  return (
    <div className="flex items-center gap-1">
      {([0, 1, 2, 3] as const).map(i => (
        <span
          key={i}
          className="inline-block w-2 h-2 rounded-full"
          style={{
            background: i < level ? activeColor : 'var(--color-border)',
          }}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Lluvias() {
  return (
    <div className="relative">
      <Dither opacity={0.03} />

      <FadeContent>
        {/* Header */}
        <div className="mb-10 text-center">
          <p
            className="text-[.62rem] font-medium tracking-[.28em] uppercase mb-4"
            style={{ color: 'var(--color-primary)' }}
          >
            Lluvias según el cielo
          </p>
          <h1 className="sr-only">Qué lluvia esperar según las nubes</h1>
          <div aria-hidden="true" className="mb-4 flex justify-center">
            <RainText text="Qué lluvia esperar según las nubes" fontSize="2.25rem" />
          </div>
          <p className="text-sm max-w-lg mx-auto leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            Cada tipo de nube produce un tipo de lluvia distinto — o ninguna.
            Aprendé a leer el cielo antes de que llueva.
          </p>
        </div>

        {/* Critical cloud callout */}
        <div
          className="rounded-xl px-5 py-4 flex items-start gap-4 mb-6"
          style={{ background: 'rgba(255,51,51,0.06)', border: '1.5px solid rgba(255,51,51,0.28)' }}
        >
          <div className="relative flex-shrink-0 mt-1">
            <span className="absolute inset-0 rounded-full animate-ping opacity-50" style={{ background: 'var(--color-crit)' }} />
            <span className="relative block w-3 h-3 rounded-full" style={{ background: 'var(--color-crit)' }} />
          </div>
          <div>
            <p className="text-sm font-bold leading-tight" style={{ color: 'var(--color-crit)' }}>
              Cumulonimbo y Mammatus — peligro severo
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--color-muted-foreground)' }}>
              Son las únicas nubes que producen tormenta severa, granizo y rayos. Si las ves crecer en torres, buscá refugio antes de que lleguen.
            </p>
          </div>
        </div>

        {/* Escala de referencia */}
        <IntensityScaleBar />

        {/* Table */}
        <div className="overflow-x-auto rounded-xl border mt-6" style={{ borderColor: 'var(--color-border)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: 'var(--color-card)' }}>
                {['Tipo de nube', '¿Llueve?', 'Intensidad', 'Duración típica', 'Cuándo aparece'].map(h => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-[.65rem] font-medium uppercase tracking-wide"
                    style={{ color: 'var(--color-muted-foreground)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CLOUDS.map((row) => (
                <tr
                  key={row.name}
                  className="border-t transition-colors hover:bg-white/[.02]"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: row.badge === 'crit' ? 'rgba(255,51,51,0.04)' : undefined,
                  }}
                >
                  <td className="px-4 py-3 font-medium" style={{ color: 'var(--color-foreground)' }}>
                    {row.name}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={row.badge} label={row.badgeLabel} />
                  </td>
                  <td className="px-4 py-3">
                    <IntensityDots level={row.intensity} />
                  </td>
                  <td
                    className="px-4 py-3 hidden sm:table-cell text-xs"
                    style={{ color: row.duration === '—' ? 'var(--color-muted-foreground)' : 'var(--color-foreground)' }}
                  >
                    {row.duration}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: 'var(--color-muted-foreground)' }}>
                    {row.when}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Educational cards */}
        <div className="mt-12">
          <h2
            className="text-xl font-semibold italic mb-6"
            style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
          >
            Cómo leer el cielo antes de que llueva
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              {
                accent: '#c8a84b',
                title: 'La secuencia clásica de un frente',
                body: <>El ciclo más predecible: primero aparecen <strong style={{ color: 'var(--color-foreground)' }}>Cirros</strong> — aviso de 24–48 h. Luego el cielo se cubre con <strong style={{ color: 'var(--color-foreground)' }}>Cirrostratos</strong> y su halo. Bajan a <strong style={{ color: 'var(--color-foreground)' }}>Altostratos</strong> y el sol desaparece. Finalmente llega el <strong style={{ color: 'var(--color-foreground)' }}>Nimboestrato</strong> — lluvia continua que dura horas.</>,
              },
              {
                accent: '#e05545',
                title: 'La tormenta convectiva',
                body: <>El ciclo más violento y más rápido: <strong style={{ color: 'var(--color-foreground)' }}>Cúmulos</strong> crecen en torres durante la tarde. Si el ambiente es inestable, se convierten en <strong style={{ color: 'var(--color-foreground)' }}>Cumulonimbos</strong> en minutos. La lluvia es breve pero extrema — granizo, ráfagas y rayos. Sin aviso previo de horas.</>,
              },
              {
                accent: '#5aaad8',
                title: 'El día gris sin drama',
                body: <>El escenario más cotidiano: <strong style={{ color: 'var(--color-foreground)' }}>Estratocúmulos</strong> o <strong style={{ color: 'var(--color-foreground)' }}>Estratos</strong> cubren el cielo sin traer lluvia seria. A lo sumo una llovizna fina. El día es gris, la luz plana y el ambiente húmedo — pero sin riesgo real. El paraguas es opcional.</>,
              },
              {
                accent: '#90aabb',
                title: 'Lo que las nubes no dicen',
                body: <>Las nubes muestran lo que pasa ahora, no necesariamente lo que viene en horas. Un cielo con <strong style={{ color: 'var(--color-foreground)' }}>Cirros</strong> puede seguir despejado un día entero. Un <strong style={{ color: 'var(--color-foreground)' }}>Nimboestrato</strong> puede terminar antes de lo esperado. Usar las nubes como pista, no como pronóstico exacto.</>,
              },
            ].map(({ accent, title, body }) => (
              <div
                key={title}
                className="rounded-xl p-5"
                style={{
                  background: `${accent}0a`,
                  border: `1px solid ${accent}30`,
                }}
              >
                <p className="text-[.63rem] font-medium tracking-widest uppercase mb-2" style={{ color: accent }}>
                  {title}
                </p>
                <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
                  {body}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Quick rule */}
        <div
          className="mt-8 rounded-xl p-6"
          style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
        >
          <p className="text-[.63rem] font-medium tracking-widest uppercase mb-4" style={{ color: 'var(--color-primary)' }}>
            Regla práctica rápida
          </p>
          <div className="grid grid-cols-3 gap-4 text-center">
            {[
              { emoji: '🌤', title: 'Nubes finas y altas',   desc: 'Cirros, cirrostratos — sin lluvia hoy, monitorear mañana' },
              { emoji: '🌧', title: 'Capas grises y bajas',  desc: 'Estrato, nimboestrato — llevá paraguas, va a durar' },
              { emoji: '⛈', title: 'Torres que crecen',     desc: 'Cúmulos en expansión — buscá refugio antes de las 3 hs' },
            ].map(({ emoji, title, desc }) => (
              <div key={title}>
                <div className="text-2xl mb-2">{emoji}</div>
                <div className="text-xs font-medium mb-1" style={{ color: 'var(--color-foreground)' }}>{title}</div>
                <div className="text-[.72rem]" style={{ color: 'var(--color-muted-foreground)' }}>{desc}</div>
              </div>
            ))}
          </div>
        </div>

      </FadeContent>
    </div>
  )
}
