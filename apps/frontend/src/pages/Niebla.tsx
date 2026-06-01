import type { ComponentType } from 'react'
import { Eye, Wind, Waves, Mountain, Snowflake, Droplets, Sun } from 'lucide-react'
import { FadeContent } from '@/components/animated/FadeContent'
import { useNiebla } from '@/hooks/useWeather'
import type { NieblaResponse } from '@/lib/api'
import FogDayIcon from '@/assets/meteocons/fog-day.svg?react'
import { PageHeader } from '@/components/ui/PageHeader'
import { FogText } from '@/components/animated/FogText'

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
    subtitle: 'Partículas suspendidas + agua · solo en costas',
    when: 'Primavera y verano, vientos del E-SE',
    where: 'Buenos Aires, Montevideo, costa rioplatense',
    danger: 'medium',
    dangerLabel: 'Visibilidad 1–2 km',
    description: 'A diferencia de la neblina (solo gotas de agua), la bruma contiene sales marinas, polvo y contaminantes en suspensión. Se forma principalmente en zonas costeras y sobre el Río de la Plata. Visibilidad superior a 1 km pero el aire aparece opaco o blanquecino. La neblina pura, en cambio, es agua condensada a ras del suelo y puede formarse en cualquier región con humedad relativa superior al 70–80 %.',
    tip: 'En costa: si el horizonte marino se ve blanquecino sin nubes, es bruma. Si no podés ver a 1 km, ya es neblina.',
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
// Visibility scale — 6 levels with perceptually distinct colors
// ---------------------------------------------------------------------------

const VISIBILITY_SCALE = [
  { label: 'Niebla',    range: '< 500 m',      color: '#e03535', note: 'Solo gotas de agua'         },
  { label: 'Neblina',   range: '500 m – 1 km', color: '#c84c10', note: 'Gotas · humedad > 70 %'      },
  { label: 'Bruma',     range: '1 – 2 km',     color: '#f0a020', note: 'Costera · sales + partículas' },
  { label: 'Reducida',  range: '2 – 5 km',     color: '#a8c820', note: '' },
  { label: 'Buena',     range: '5 – 10 km',    color: '#5aaad8', note: '' },
  { label: 'Despejada', range: '> 10 km',       color: '#3ecf7a', note: '' },
] as const

/**
 * Normaliza colores heredados del backend a la paleta de 6 niveles con
 * mayor contraste perceptual. Mapeo defensivo: si el backend envía un color
 * que no está en la tabla, lo pasa tal cual.
 */
const FOG_COLOR_OVERRIDE: Record<string, string> = {
  '#e05545': '#e03535',  // Niebla  — rojo más puro
  '#e07030': '#c84c10',  // Neblina — siena quemada (antes demasiado similar al ámbar)
  '#f0a030': '#f0a020',  // Bruma   — ámbar (mínima corrección)
  '#c8a84b': '#a8c820',  // Reducida — lima/chartreuse (antes confundible con ámbar)
}

function normalizeFogColor(c: string | null | undefined): string {
  if (!c) return '#3ecf7a'
  return FOG_COLOR_OVERRIDE[c] ?? FOG_COLOR_OVERRIDE[c.toLowerCase()] ?? c
}

// ---------------------------------------------------------------------------
// Visibility utils
// ---------------------------------------------------------------------------

function visibilityKm(m: number | null): string {
  if (m == null) return '—'
  if (m >= 10_000) return '>10 km'
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

interface SourcePillProps {
  status: PillStatus
  source?: string | null
  stationName?: string | null
  distanceKm?: number | null
}

/** Source indicator showing METAR station or Open-Meteo depending on data source. */
function SourcePill({ status, source, stationName, distanceKm }: SourcePillProps) {
  const color =
    status === 'ok'    ? '#3ecf7a' :
    status === 'error' ? '#e05545' :
    'var(--color-muted-foreground)'

  const isMetar = source === 'metar'
  const label = isMetar
    ? `METAR · ${stationName ?? ''}${distanceKm != null ? ` · ${Math.round(distanceKm)} km` : ''}`
    : 'Open-Meteo'

  return (
    <span
      title={isMetar ? 'Visibilidad medida en aeropuerto más cercano (dato real)' : 'Estimación numérica Open-Meteo'}
      className="rounded-full"
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
        padding: '2px 9px 2px 6px',
        whiteSpace: 'nowrap',
      }}
    >
      <span
        aria-hidden="true"
        className="rounded-full"
        style={{
          width: '6px',
          height: '6px',
          background: color,
          display: 'inline-block',
          flexShrink: 0,
        }}
      />
      {label}
    </span>
  )
}

function FogCard({ fog }: { fog: FogType }) {
  const d = DANGER_COLORS[fog.danger]
  return (
    <article
      className="rounded-2xl"
      style={{
        background: 'var(--color-card)',
        border: '1px solid var(--color-border)',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      {/* Icon + title row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
        <div
          className="rounded-[10px]"
          style={{
            width: '40px',
            height: '40px',
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
          className="rounded-md"
          style={{
            flexShrink: 0,
            fontSize: '10px',
            fontWeight: 600,
            color: d.color,
            background: d.bg,
            border: `1px solid ${d.border}`,
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
          className="rounded-[20px]"
          style={{
            fontSize: '11px',
            color: 'var(--color-muted-foreground)',
            background: 'rgba(255,255,255,.04)',
            border: '1px solid var(--color-border)',
            padding: '3px 9px',
          }}
        >
          🗓️ {fog.when}
        </span>
        <span
          className="rounded-[20px]"
          style={{
            fontSize: '11px',
            color: 'var(--color-muted-foreground)',
            background: 'rgba(255,255,255,.04)',
            border: '1px solid var(--color-border)',
            padding: '3px 9px',
          }}
        >
          📍 {fog.where}
        </span>
      </div>

      {/* Tip */}
      <div
        className="rounded-[10px]"
        style={{
          fontSize: '12px',
          color: 'var(--color-foreground)',
          background: 'rgba(255,255,255,.03)',
          border: '1px solid var(--color-border)',
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
          className="rounded-lg"
          style={{
            fontSize: '13px',
            fontWeight: 600,
            color: fogColor,
            background: `${fogColor}18`,
            border: `1px solid ${fogColor}40`,
            padding: '3px 9px',
          }}
        >
          {fogLabel}
        </span>
      </div>

      {/* Bar track */}
      <div
        className="rounded-full"
        style={{
          position: 'relative',
          height: '8px',
          background: 'rgba(255,255,255,.07)',
          overflow: 'hidden',
        }}
        role="meter"
        aria-valuenow={visibilityM ?? 0}
        aria-valuemin={0}
        aria-valuemax={10000}
        aria-label={`Visibilidad actual: ${kmLabel}`}
      >
        <div
          className="rounded-full"
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            height: '100%',
            width: `${fraction * 100}%`,
            background: fogColor,
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

// Human-readable labels for hourly data sources
const HOURLY_SOURCE_LABEL: Record<string, string> = {
  taf:                  'TAF · Aviación',
  openmeteo_inference:  'Inferencia OM',
  openmeteo:            'Open-Meteo',
}

/** 12-hour visibility timeline bars */
function VisibilityTimeline({
  slots,
  hourlySource,
}: {
  slots: NieblaResponse['hourly']
  hourlySource?: string | null
}) {
  if (!slots.length) return null

  const maxM    = 10_000
  const CHART_H = 80 // px — chart area height (labels rendered outside)
  const BAR_MIN = 6  // minimum bar height in px (same as max(..., 6) below)
  const BAR_PAD = 8  // base offset so 0-visibility bar is still visible

  return (
    <div>
      {/* Header: title + hourly source badge */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3
          style={{
            margin: 0,
            fontSize: '13px',
            fontWeight: 600,
            color: 'var(--color-muted-foreground)',
            textTransform: 'uppercase',
            letterSpacing: '.05em',
          }}
        >
          Próximas 12 h
        </h3>
        {hourlySource && (
          <span
            title={
              hourlySource === 'taf'
                ? 'Pronóstico emitido por meteorólogos de aviación (TAF)'
                : hourlySource === 'openmeteo_inference'
                ? 'Estimado a partir de humedad, rocío y viento (Open-Meteo)'
                : 'Pronóstico numérico Open-Meteo'
            }
            className="rounded-[20px]"
            style={{
              fontSize: '10px',
              fontWeight: 500,
              color: hourlySource === 'taf' ? '#3ecf7a' : 'var(--color-muted-foreground)',
              background: hourlySource === 'taf' ? 'rgba(62,207,122,.08)' : 'rgba(255,255,255,.04)',
              border: `1px solid ${hourlySource === 'taf' ? 'rgba(62,207,122,.3)' : 'var(--color-border)'}`,
              padding: '2px 8px',
              whiteSpace: 'nowrap',
            }}
          >
            {HOURLY_SOURCE_LABEL[hourlySource] ?? hourlySource}
          </span>
        )}
      </div>

      {/* ── Chart area: bars + reference line ── */}
      <div
        style={{
          position: 'relative',
          height: `${CHART_H}px`,
          display: 'flex',
          alignItems: 'flex-end',
          gap: '3px',
        }}
        role="img"
        aria-label="Pronóstico de visibilidad para las próximas 12 horas"
      >
        {/* Bars — rendered first so reference line paints on top */}
        {slots.map((s) => {
          const barH = Math.max(
            ((s.visibility_m ?? 0) / maxM) * (CHART_H - BAR_PAD) + BAR_PAD,
            BAR_MIN,
          )
          return (
            <div
              key={s.hour_label}
              title={`${s.hour_label}: ${visibilityKm(s.visibility_m)} — ${s.fog_label}`}
              style={{
                flex: 1,
                height: `${barH}px`,
                background: `${s.fog_color}bb`,
                borderRadius: '4px 4px 2px 2px',
                transition: 'height 0.5s ease',
                cursor: 'default',
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

      {/* ── Fog level label per bar — desambigua cuando los colores son similares ── */}
      <div style={{ display: 'flex', gap: '4px', marginTop: '2px' }}>
        {slots.map((s) => (
          <span
            key={s.hour_label}
            style={{
              flex: 1,
              textAlign: 'center',
              fontSize: '7px',
              fontWeight: 600,
              color: s.fog_color,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'clip',
              letterSpacing: '-0.01em',
            }}
          >
            {s.fog_label}
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
      className="rounded-[20px]"
      style={{
        background: 'var(--color-card)',
        border: '1px solid var(--color-border)',
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
            source={data?.source}
            stationName={data?.metar_station_name}
            distanceKm={data?.metar_distance_km}
          />
        </div>
      </div>

      {isLoading && (
        <div
          className="rounded-[10px]"
          style={{
            height: '80px',
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
            fogColor={normalizeFogColor(data.fog_color)}
          />
          <VisibilityTimeline
            slots={data.hourly.map(h => ({ ...h, fog_color: normalizeFogColor(h.fog_color) }))}
            hourlySource={data.hourly_source}
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
          className="rounded-2xl"
          style={{
            height: '140px',
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
          titleNode={<FogText text="Niebla, Bruma y Neblina" fontSize="1.5rem" />}
          icon={<FogDayIcon style={{ width: '40px', height: '40px' }} />}
          title="Niebla, Bruma y Neblina"
          subtitle="6 tipos de niebla en Argentina — visibilidad y qué esperar."
          accentColor="#90aabb"
        />

        {/* ── Live visibility (only if location) ──────────────────────── */}
        <VisibilityBlock location={location} />

        {/* ── Visibility scale reference ───────────────────────────────── */}
        <section
          className="rounded-2xl"
          style={{
            background: 'var(--color-card)',
            border: '1px solid var(--color-border)',
            padding: '20px',
          }}
        >
          <h2
            style={{
              margin: '0 0 16px',
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--color-muted-foreground)',
              textTransform: 'uppercase',
              letterSpacing: '.08em',
            }}
          >
            Escala de visibilidad (peor → mejor)
          </h2>

          {/* Segmented bar — colores en contexto, el ojo distingue mejor con adyacentes */}
          <div style={{ display: 'flex', gap: '3px', marginBottom: '8px' }}>
            {VISIBILITY_SCALE.map(({ label, color }) => (
              <div
                key={label}
                title={label}
                className="rounded-full"
                style={{
                  flex: 1,
                  height: '10px',
                  background: color,
                }}
              />
            ))}
          </div>

          {/* Column labels — nombre + rango debajo de cada segmento */}
          <div style={{ display: 'flex', gap: '3px' }}>
            {VISIBILITY_SCALE.map(({ label, range, color, note }) => (
              <div
                key={label}
                style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}
              >
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 700,
                    color,
                    textAlign: 'center',
                    lineHeight: 1.2,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    maxWidth: '100%',
                  }}
                >
                  {label}
                </span>
                <span
                  style={{
                    fontSize: '8px',
                    color: 'var(--color-muted-foreground)',
                    textAlign: 'center',
                    lineHeight: 1.2,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    maxWidth: '100%',
                  }}
                >
                  {range}
                </span>
                {note && (
                  <span
                    style={{
                      fontSize: '7px',
                      color: 'var(--color-muted-foreground)',
                      textAlign: 'center',
                      lineHeight: 1.2,
                      opacity: 0.7,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      maxWidth: '100%',
                    }}
                  >
                    {note}
                  </span>
                )}
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
