import { useId } from 'react'
import { FadeContent } from '@/components/animated/FadeContent'
import { useNiebla } from '@/hooks/useWeather'
import type { NieblaResponse } from '@/lib/api'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Props {
  location: { lat: number; lon: number } | null
}

type FogCategory = 'radiation' | 'advection' | 'sea' | 'valley' | 'freezing' | 'steam'

interface FogType {
  id: FogCategory
  name: string
  subtitle: string
  when: string
  where: string
  danger: 'low' | 'medium' | 'high'
  dangerLabel: string
  description: string
  tip: string
  icon: string
}

// ---------------------------------------------------------------------------
// Catalog data
// ---------------------------------------------------------------------------

const FOG_TYPES: FogType[] = [
  {
    id: 'radiation',
    name: 'Niebla de radiación',
    subtitle: 'La más común en Argentina',
    when: 'Noches despejadas, invierno y otoño',
    where: 'Pampa húmeda, valles, zonas rurales',
    danger: 'medium',
    dangerLabel: 'Visibilidad reducida al amanecer',
    description: 'El suelo enfría el aire cercano durante la noche y condensa el vapor de agua. Se forma entre medianoche y el amanecer y desaparece con el sol. La más frecuente en las llanuras argentinas.',
    tip: 'Espera 2–3 horas después del amanecer — el sol la disipa rápidamente.',
    icon: '🌫️',
  },
  {
    id: 'advection',
    name: 'Niebla de advección',
    subtitle: 'Aire cálido sobre superficie fría',
    when: 'Todo el año, especialmente en costa atlántica',
    where: 'Costa bonaerense, Delta del Paraná',
    danger: 'high',
    dangerLabel: 'Puede durar días enteros',
    description: 'Masa de aire cálido y húmedo que se desplaza sobre una superficie más fría (agua o tierra). A diferencia de la radiación, no desaparece con el sol y puede cubrir grandes áreas por días.',
    tip: 'Si hay viento del noreste con temperatura superior a la media: esperá niebla persistente.',
    icon: '🌊',
  },
  {
    id: 'sea',
    name: 'Bruma marina',
    subtitle: 'Niebla sobre el Río de la Plata',
    when: 'Primavera y verano, vientos del E-SE',
    where: 'Buenos Aires, Montevideo, costa rioplatense',
    danger: 'medium',
    dangerLabel: 'Visibilidad 500–2000 m',
    description: 'La evaporación del agua del Río de la Plata o el océano crea una capa baja de niebla que avanza tierra adentro con el viento. Frecuente en la madrugada y mañana en la costa porteña.',
    tip: 'Visible como banco blanco sobre el río al amanecer desde la costanera.',
    icon: '⚓',
  },
  {
    id: 'valley',
    name: 'Niebla de ladera y valle',
    subtitle: 'Atrapada entre montañas',
    when: 'Noches calmas, cuencas cerradas',
    where: 'Mendoza, Salta, Jujuy, precordillera',
    danger: 'medium',
    dangerLabel: 'Persistente en zonas encajonadas',
    description: 'El aire frío y pesado escurre ladera abajo y se acumula en los valles. Los pasos de montaña y rutas de altura pueden tener niebla intensa mientras en la cumbre el cielo está despejado.',
    tip: 'En rutas de montaña: si la temperatura baja 5°C en menos de una hora, reducí velocidad.',
    icon: '⛰️',
  },
  {
    id: 'freezing',
    name: 'Niebla con escarcha',
    subtitle: 'Peligro en ruta y aeropuertos',
    when: 'Invierno, temperaturas bajo cero',
    where: 'Patagonia, puna, noches de helada',
    danger: 'high',
    dangerLabel: 'WMO código 48 — peligro grave',
    description: 'Niebla en la que las gotitas se congelan al contacto con superficies. Crea una capa de hielo invisible en el asfalto, alas de avión y tendidos eléctricos. La más peligrosa de todas.',
    tip: 'Si hay niebla + temperatura bajo 0°C: no salgas en auto. Las rutas están como espejo.',
    icon: '🧊',
  },
  {
    id: 'steam',
    name: 'Humo de mar (vapor de agua)',
    subtitle: 'Curiosidad térmica',
    when: 'Invierno muy frío con superficie de agua tibia',
    where: 'Lagos patagónicos, Litoral húmedo',
    danger: 'low',
    dangerLabel: 'Efecto visual, baja peligrosidad',
    description: 'Columnas de vapor que suben de la superficie del agua cuando el aire está mucho más frío. El agua "humea" como si estuviera hirviendo. Espectacular en los lagos patagónicos en invierno.',
    tip: 'Fenómeno efímero y localizado — la visibilidad mejora a solo metros de la orilla.',
    icon: '💨',
  },
]

const DANGER_COLORS = {
  low:    { color: '#3ecf7a', bg: 'rgba(62,207,122,.09)',  border: 'rgba(62,207,122,.25)'  },
  medium: { color: '#f0a030', bg: 'rgba(240,160,48,.09)',  border: 'rgba(240,160,48,.28)'  },
  high:   { color: '#e05545', bg: 'rgba(224,85,69,.09)',   border: 'rgba(224,85,69,.28)'   },
}

// ---------------------------------------------------------------------------
// Visibility utils
// ---------------------------------------------------------------------------

function visibilityKm(m: number | null): string {
  if (m == null) return '—'
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`
  return `${Math.round(m)} m`
}

/** 0–10 km range → 0–1 fraction capped at 1 */
function visibilityFraction(m: number | null): number {
  if (m == null) return 0
  return Math.min(m / 10_000, 1)
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FogCard({ fog }: { fog: FogType }) {
  const d = DANGER_COLORS[fog.danger]
  return (
    <article
      style={{
        background: 'var(--color-card)',
        border: '1px solid var(--color-border)',
        borderRadius: '16px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      {/* Icon + title row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <span
          style={{
            fontSize: '28px',
            lineHeight: 1,
            flexShrink: 0,
            marginTop: '2px',
          }}
          role="img"
          aria-hidden="true"
        >
          {fog.icon}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3
            style={{
              margin: 0,
              fontSize: '15px',
              fontWeight: 600,
              color: 'var(--color-foreground)',
              fontFamily: 'var(--font-serif)',
            }}
          >
            {fog.name}
          </h3>
          <p
            style={{
              margin: '2px 0 0',
              fontSize: '12px',
              color: 'var(--color-muted-foreground)',
            }}
          >
            {fog.subtitle}
          </p>
        </div>
        {/* Danger badge */}
        <span
          style={{
            flexShrink: 0,
            fontSize: '10px',
            fontWeight: 600,
            color: d.color,
            background: d.bg,
            border: `1px solid ${d.border}`,
            borderRadius: '6px',
            padding: '3px 7px',
            whiteSpace: 'nowrap',
          }}
        >
          {fog.dangerLabel}
        </span>
      </div>

      {/* Description */}
      <p
        style={{
          margin: 0,
          fontSize: '13px',
          lineHeight: 1.6,
          color: 'var(--color-muted-foreground)',
        }}
      >
        {fog.description}
      </p>

      {/* When / Where pills */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        <span
          style={{
            fontSize: '11px',
            color: 'var(--color-muted-foreground)',
            background: 'rgba(255,255,255,.04)',
            border: '1px solid var(--color-border)',
            borderRadius: '20px',
            padding: '3px 9px',
          }}
        >
          🗓️ {fog.when}
        </span>
        <span
          style={{
            fontSize: '11px',
            color: 'var(--color-muted-foreground)',
            background: 'rgba(255,255,255,.04)',
            border: '1px solid var(--color-border)',
            borderRadius: '20px',
            padding: '3px 9px',
          }}
        >
          📍 {fog.where}
        </span>
      </div>

      {/* Tip */}
      <div
        style={{
          fontSize: '12px',
          color: 'var(--color-foreground)',
          background: 'rgba(255,255,255,.03)',
          border: '1px solid var(--color-border)',
          borderRadius: '10px',
          padding: '10px 12px',
        }}
      >
        <span style={{ color: '#c8a84b', fontWeight: 600 }}>Tip:</span>{' '}
        {fog.tip}
      </div>
    </article>
  )
}

/** Horizontal visibility gauge with label */
function VisibilityMeter({
  visibilityM,
  fogLabel,
  fogColor,
}: {
  visibilityM: number | null
  fogLabel: string
  fogColor: string
}) {
  const fraction = visibilityFraction(visibilityM)
  const kmLabel  = visibilityKm(visibilityM)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {/* Value row */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
        <span
          style={{
            fontSize: '32px',
            fontWeight: 700,
            fontFamily: 'var(--font-mono, monospace)',
            color: fogColor,
            lineHeight: 1,
          }}
        >
          {kmLabel}
        </span>
        <span
          style={{
            fontSize: '13px',
            fontWeight: 600,
            color: fogColor,
            background: `${fogColor}18`,
            border: `1px solid ${fogColor}40`,
            borderRadius: '8px',
            padding: '3px 9px',
          }}
        >
          {fogLabel}
        </span>
      </div>

      {/* Bar track */}
      <div
        style={{
          position: 'relative',
          height: '8px',
          background: 'rgba(255,255,255,.07)',
          borderRadius: '99px',
          overflow: 'hidden',
        }}
        role="meter"
        aria-valuenow={visibilityM ?? 0}
        aria-valuemin={0}
        aria-valuemax={10000}
        aria-label={`Visibilidad actual: ${kmLabel}`}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '100%',
            width: `${fraction * 100}%`,
            background: fogColor,
            borderRadius: '99px',
            transition: 'width 0.8s ease',
          }}
        />
      </div>

      {/* Scale labels */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '10px',
          color: 'var(--color-muted-foreground)',
        }}
      >
        <span>0 m</span>
        <span>2 km</span>
        <span>5 km</span>
        <span>10 km</span>
      </div>
    </div>
  )
}

/** 12-hour visibility timeline bars */
function VisibilityTimeline({
  slots,
}: {
  slots: NieblaResponse['hourly']
}) {
  const gradId = useId()

  if (!slots.length) return null

  const maxM = 10_000

  return (
    <div>
      <h3
        style={{
          margin: '0 0 12px',
          fontSize: '13px',
          fontWeight: 600,
          color: 'var(--color-muted-foreground)',
          textTransform: 'uppercase',
          letterSpacing: '.05em',
        }}
      >
        Próximas 12 h
      </h3>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: '4px',
          height: '60px',
        }}
        role="img"
        aria-label="Pronóstico de visibilidad para las próximas 12 horas"
      >
        <svg width={0} height={0} style={{ position: 'absolute' }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#5aaad8" stopOpacity="1" />
              <stop offset="100%" stopColor="#5aaad8" stopOpacity="0.4" />
            </linearGradient>
          </defs>
        </svg>
        {slots.map((s) => {
          const h = Math.max((((s.visibility_m ?? 0) / maxM) * 52) + 8, 6)
          return (
            <div
              key={s.hour_label}
              style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}
            >
              <div
                title={`${s.hour_label}: ${visibilityKm(s.visibility_m)} — ${s.fog_label}`}
                style={{
                  width: '100%',
                  height: `${h}px`,
                  background: `${s.fog_color}cc`,
                  borderRadius: '4px 4px 2px 2px',
                  transition: 'height 0.5s ease',
                  cursor: 'default',
                }}
              />
              <span
                style={{
                  fontSize: '9px',
                  color: 'var(--color-muted-foreground)',
                  whiteSpace: 'nowrap',
                }}
              >
                {s.hour_label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Live visibility block — shown only when location is available */
function VisibilityBlock({ location }: { location: { lat: number; lon: number } }) {
  const { data, isLoading, error } = useNiebla(location.lat, location.lon)

  return (
    <section
      style={{
        background: 'var(--color-card)',
        border: '1px solid var(--color-border)',
        borderRadius: '20px',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{ fontSize: '20px' }} role="img" aria-hidden="true">👁️</span>
        <div>
          <h2
            style={{
              margin: 0,
              fontSize: '15px',
              fontWeight: 700,
              color: 'var(--color-foreground)',
            }}
          >
            Visibilidad actual
          </h2>
          <p
            style={{
              margin: '1px 0 0',
              fontSize: '11px',
              color: 'var(--color-muted-foreground)',
            }}
          >
            Datos Open-Meteo · actualiza cada 5 min
          </p>
        </div>
      </div>

      {isLoading && (
        <div
          style={{
            height: '80px',
            borderRadius: '10px',
            background: 'rgba(255,255,255,.04)',
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      )}

      {error && (
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--color-muted-foreground)' }}>
          No se pudo obtener la visibilidad en este momento.
        </p>
      )}

      {data && !isLoading && (
        <>
          <VisibilityMeter
            visibilityM={data.visibility_m}
            fogLabel={data.fog_label}
            fogColor={data.fog_color}
          />
          <VisibilityTimeline slots={data.hourly} />
        </>
      )}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Page skeleton
// ---------------------------------------------------------------------------

function PageSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          style={{
            height: '140px',
            borderRadius: '16px',
            background: 'rgba(255,255,255,.04)',
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Niebla({ location }: Props) {
  if (!location) return <PageSkeleton />

  return (
    <FadeContent>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>

        {/* ── Header ────────────────────────────────────────────────────── */}
        <header style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div
            style={{
              width: '48px',
              height: '48px',
              borderRadius: '14px',
              background: 'linear-gradient(135deg, rgba(144,170,187,.2) 0%, rgba(144,170,187,.05) 100%)',
              border: '1px solid rgba(144,170,187,.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '22px',
              marginBottom: '4px',
            }}
          >
            🌫️
          </div>
          <h1
            style={{
              margin: 0,
              fontSize: '26px',
              fontWeight: 700,
              fontFamily: 'var(--font-serif)',
              color: 'var(--color-foreground)',
            }}
          >
            Niebla, Bruma y Neblina
          </h1>
          <p
            style={{
              margin: 0,
              fontSize: '14px',
              color: 'var(--color-muted-foreground)',
              maxWidth: '520px',
            }}
          >
            Seis tipos de niebla que se forman en Argentina — y cómo cada una afecta la visibilidad de forma diferente.
          </p>
        </header>

        {/* ── Live visibility (only if location) ──────────────────────── */}
        <VisibilityBlock location={location} />

        {/* ── Visibility scale reference ───────────────────────────────── */}
        <section>
          <h2
            style={{
              margin: '0 0 14px',
              fontSize: '13px',
              fontWeight: 600,
              color: 'var(--color-muted-foreground)',
              textTransform: 'uppercase',
              letterSpacing: '.05em',
            }}
          >
            Escala de visibilidad
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
              gap: '8px',
            }}
          >
            {[
              { label: 'Despejada',    range: '> 10 km',     color: '#3ecf7a' },
              { label: 'Buena',        range: '5–10 km',     color: '#5aaad8' },
              { label: 'Reducida',     range: '2–5 km',      color: '#c8a84b' },
              { label: 'Bruma',        range: '1–2 km',      color: '#f0a030' },
              { label: 'Niebla',       range: '500 m–1 km',  color: '#e07030' },
              { label: 'Niebla densa', range: '< 500 m',     color: '#e05545' },
            ].map(({ label, range, color }) => (
              <div
                key={label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 12px',
                  borderRadius: '10px',
                  background: 'var(--color-card)',
                  border: '1px solid var(--color-border)',
                }}
              >
                <span
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: color,
                    flexShrink: 0,
                  }}
                />
                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-foreground)' }}>
                    {label}
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--color-muted-foreground)' }}>
                    {range}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Visual divider ───────────────────────────────────────────── */}
        <div
          aria-hidden="true"
          style={{
            height: '1px',
            background: 'linear-gradient(90deg, transparent, var(--color-border), transparent)',
          }}
        />

        {/* ── Fog catalog ─────────────────────────────────────────────── */}
        <section>
          <h2
            style={{
              margin: '0 0 16px',
              fontSize: '13px',
              fontWeight: 600,
              color: 'var(--color-muted-foreground)',
              textTransform: 'uppercase',
              letterSpacing: '.05em',
            }}
          >
            Tipos de niebla en Argentina
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '14px',
            }}
          >
            {FOG_TYPES.map(fog => (
              <FogCard key={fog.id} fog={fog} />
            ))}
          </div>
        </section>

        {/* ── Footer note ─────────────────────────────────────────────── */}
        <p
          style={{
            margin: 0,
            fontSize: '11px',
            color: 'var(--color-muted-foreground)',
            textAlign: 'center',
            paddingBottom: '8px',
          }}
        >
          Visibilidad en metros según modelo Open-Meteo best_match · Clasificación basada en estándares WMO
        </p>

      </div>
    </FadeContent>
  )
}
