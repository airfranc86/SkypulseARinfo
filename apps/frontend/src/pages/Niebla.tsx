import type { ComponentType } from 'react'
import { Eye, Wind, Waves, Mountain, Snowflake, Droplets, Sun } from 'lucide-react'
import { FadeContent } from '@/components/animated/FadeContent'
import { useNiebla } from '@/hooks/useWeather'
import type { NieblaResponse } from '@/lib/api'
import FogDayIcon from '@/assets/meteocons/fog-day.svg?react'
import { PageHeader } from '@/components/ui/PageHeader'

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
  Icon: ComponentType<{ size?: number; color?: string; strokeWidth?: number }>
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
    Icon: Sun,
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
    Icon: Wind,
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
    Icon: Waves,
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
    Icon: Mountain,
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
    Icon: Snowflake,
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
    Icon: Droplets,
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

type PillStatus = 'loading' | 'ok' | 'error'

/** Minimal source indicator — no technical jargon, just name + status color. */
function SourcePill({ status }: { status: PillStatus }) {
  const color =
    status === 'ok'    ? '#3ecf7a' :
    status === 'error' ? '#e05545' :
    'var(--color-muted-foreground)'

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        fontSize: '11px',
        fontWeight: 500,
        color,
        background: status === 'loading'
          ? 'rgba(255,255,255,.06)'
          : `${color}14`,
        border: `1px solid ${status === 'loading' ? 'var(--color-border)' : `${color}35`}`,
        borderRadius: '99px',
        padding: '2px 9px 2px 6px',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: color,
          display: 'inline-block',
          flexShrink: 0,
        }}
      />
      Open-Meteo
    </span>
  )
}

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
        <div
          style={{
            width: '40px',
            height: '40px',
            borderRadius: '10px',
            background: `${d.color}12`,
            border: `1px solid ${d.color}30`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
          }}
        >
          <fog.Icon size={20} color={d.color} strokeWidth={1.5} />
        </div>
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

/** 12-hour visibility timeline bars with a reference line at current visibility */
function VisibilityTimeline({
  slots,
  currentVisibilityM,
}: {
  slots: NieblaResponse['hourly']
  currentVisibilityM?: number | null
}) {
  if (!slots.length) return null

  const maxM       = 10_000
  const CHART_H    = 64 // px — chart area height (labels rendered outside)

  // Reference line: position from bottom, in px within the chart area
  const refFraction = (currentVisibilityM != null)
    ? Math.min(currentVisibilityM / maxM, 1)
    : null
  const refBottom = refFraction != null
    ? Math.round(refFraction * CHART_H)
    : null

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

      {/* ── Chart area: bars only, no labels ── */}
      <div
        style={{
          position: 'relative',
          height: `${CHART_H}px`,
          display: 'flex',
          alignItems: 'flex-end',
          gap: '4px',
          overflow: 'hidden',
        }}
        role="img"
        aria-label="Pronóstico de visibilidad para las próximas 12 horas"
      >
        {/* Reference line — rendered ABOVE bars via z-index */}
        {refBottom != null && (
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: `${refBottom}px`,
              height: '1px',
              zIndex: 2,
              pointerEvents: 'none',
              backgroundImage: [
                'repeating-linear-gradient(',
                '90deg,',
                'rgba(200,168,75,0.85) 0px,',
                'rgba(200,168,75,0.85) 6px,',
                'transparent 6px,',
                'transparent 10px',
                ')',
              ].join(''),
            }}
          />
        )}

        {/* Bars — z-index below the reference line */}
        {slots.map((s) => {
          const barH = Math.max(
            (((s.visibility_m ?? 0) / maxM) * (CHART_H - 8)) + 8,
            6,
          )
          return (
            <div
              key={s.hour_label}
              title={`${s.hour_label}: ${visibilityKm(s.visibility_m)} — ${s.fog_label}`}
              style={{
                flex: 1,
                height: `${barH}px`,
                background: `${s.fog_color}cc`,
                borderRadius: '4px 4px 2px 2px',
                transition: 'height 0.5s ease',
                cursor: 'default',
                position: 'relative',
                zIndex: 1,
              }}
            />
          )
        })}
      </div>

      {/* ── Hour labels — outside chart area, never clipped ── */}
      <div style={{ display: 'flex', gap: '4px', marginTop: '4px' }}>
        {slots.map((s) => (
          <span
            key={s.hour_label}
            style={{
              flex: 1,
              textAlign: 'center',
              fontSize: '9px',
              color: 'var(--color-muted-foreground)',
              whiteSpace: 'nowrap',
            }}
          >
            {s.hour_label}
          </span>
        ))}
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
        <Eye size={20} color="var(--color-muted-foreground)" strokeWidth={1.5} />
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
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
          <SourcePill
            status={error ? 'error' : isLoading ? 'loading' : 'ok'}
          />
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
          <VisibilityTimeline
            slots={data.hourly}
            currentVisibilityM={data.visibility_m}
          />
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
        <PageHeader
          icon={<FogDayIcon style={{ width: '40px', height: '40px' }} />}
          title="Niebla, Bruma y Neblina"
          subtitle="6 tipos de niebla en Argentina — visibilidad y qué esperar."
          accentColor="#90aabb"
        />

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
          Visibilidad · Estándares WMO
        </p>

      </div>
    </FadeContent>
  )
}
