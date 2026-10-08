import { useState, useId } from 'react'
import { FadeContent } from '@/components/animated/FadeContent'
import { Dither } from '@/components/animated/Dither'
import { DriftText } from '@/components/animated/DriftText'
import { CloudSkyDiagram } from '@/components/nubes/CloudSkyDiagram'
import { StatusBadge } from '@/components/nubes/StatusBadge'
import { revealBelowHeader } from '@/components/nubes/revealBelowHeader'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import {
  CLOUDS,
  CLOUD_FAMILY_SECTIONS,
  type BadgeVariant,
  type CloudFamily,
  type CloudId,
  type CloudItem,
} from '@/data/clouds'
import { type DangerLevel, DangerScale } from '../components/ui/DangerScale'
import { TEXTO_CAMBIOS, creditoDe, textoCredito } from '@/lib/creditosFotos'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PillVariant = 'danger' | 'caution' | 'note'

interface AeroItem {
  id: string
  name: string
  latin: string
  height: string
  detail: string
  emoji: string
  dangerLevel: DangerLevel
  badge: BadgeVariant
  badgeLabel: string
  description: string
  pills: Array<{ variant: PillVariant; label: string }>
  curiosity: string
}

// ---------------------------------------------------------------------------
// Data — aeronautical phenomena
// ---------------------------------------------------------------------------

const AERO: AeroItem[] = [
  {
    id: 'jet-stream',
    name: 'Corriente en Chorro',
    latin: 'Jet Stream',
    height: 'FL300 – FL390 · 9–12 km',
    detail: '100 – 400+ km/h',
    emoji: '🌬️',
    dangerLevel: 2,
    badge: 'info',
    badgeLabel: 'Invisible — impacto directo en tiempo de vuelo y combustible',
    description: 'Ríos de viento de alta velocidad que fluyen en la tropopausa, completamente invisibles. Volar a favor recorta horas de vuelo; en contra, agota combustible y extiende el tiempo. En invierno polar pueden superar los 400 km/h.',
    pills: [
      { variant: 'caution', label: 'Turbulencia CAT' },
      { variant: 'caution', label: 'Desvío de ruta' },
      { variant: 'note',    label: 'Ahorro de combustible' },
      { variant: 'caution', label: 'Engelamiento posible' },
    ],
    curiosity: 'Los vuelos trasatlánticos de oeste a este son más cortos que el regreso gracias al jet stream polar. El planeta girando literalmente a tu favor.',
  },
  {
    id: 'wind-shear',
    name: 'Cizalladura del Viento',
    latin: 'Wind Shear',
    height: 'Crítico por debajo de 500 ft AGL',
    detail: 'Riesgo principal en final',
    emoji: '⚡',
    dangerLevel: 5,
    badge: 'crit',
    badgeLabel: 'Peligro severo — aproximación y despegue',
    description: 'Cambio brusco de velocidad o dirección del viento en corta distancia. A baja altitud puede hacer perder sustentación en segundos. Invisible y puede aparecer sin aviso. El microburst — su forma más peligrosa — es una corriente descendente bajo un Cb que golpea el suelo y se expande explosivamente.',
    pills: [
      { variant: 'danger',  label: 'Pérdida de sustentación' },
      { variant: 'danger',  label: 'Accidente en aproximación' },
      { variant: 'caution', label: 'Microburst bajo Cb' },
    ],
    curiosity: 'Un avión en final que atraviesa un microburst tiene muy pocos segundos para reaccionar. Los sistemas LLWAS en aeropuertos existen exactamente por esto.',
  },
  {
    id: 'icing',
    name: 'Engelamiento en Vuelo',
    latin: 'Aircraft Icing',
    height: 'Dentro de nubes · 0°C a −20°C',
    detail: 'Alas, sensores, pitot',
    emoji: '🧊',
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Degradación aerodinámica progresiva',
    description: 'Hielo que se forma sobre alas y sensores al volar dentro de nubes con agua supercooled — agua líquida por debajo de 0°C. Cambia la forma aerodinámica del ala, añade peso y puede bloquear el tubo Pitot. Se acumula en minutos sin que el piloto lo perciba.',
    pills: [
      { variant: 'danger', label: 'Pérdida de sustentación' },
      { variant: 'danger', label: 'Pérdida de indicaciones' },
      { variant: 'note',   label: 'Anti-ice obligatorio' },
    ],
    curiosity: 'Clear ice (hielo transparente): el más peligroso porque no se ve sobre el ala. Rime ice (escarcha blanca): visible, pero igualmente crítico para la aerodinámica.',
  },
  {
    id: 'cat',
    name: 'Turbulencia en Aire Claro',
    latin: 'Clear Air Turbulence · CAT',
    height: 'FL250 – FL450',
    detail: 'Cielo completamente despejado',
    emoji: '〰️',
    dangerLevel: 3,
    badge: 'warn',
    badgeLabel: 'Imposible de ver — ocurre sin nubes ni aviso visual',
    description: 'Turbulencia en cielo completamente despejado — sin nubes, sin indicación visual de ningún tipo. Aparece en los bordes del jet stream donde el viento cambia bruscamente. La única advertencia posible viene de PIREPs (reportes de pilotos) que la encontraron antes.',
    pills: [
      { variant: 'danger', label: 'Sin aviso previo' },
      { variant: 'danger', label: 'Lesiones a pasajeros' },
      { variant: 'note',   label: 'PIREPs son la clave' },
    ],
    curiosity: 'La mayoría de las lesiones graves en vuelo sin accidente son causadas por CAT con pasajeros sin cinturón. Por eso los pilotos piden mantenerlo abrochado incluso con cielo azul perfecto.',
  },
  {
    id: 'wake-turbulence',
    name: 'Estela Turbulenta',
    latin: 'Wake Turbulence',
    height: 'Crítico en despegue y aterrizaje',
    detail: 'Toda aeronave la genera',
    emoji: '🌀',
    dangerLevel: 4,
    badge: 'warn',
    badgeLabel: 'Crítico en separación — puede voltear aeronave pequeña',
    description: 'Todo avión genera dos vórtices invisibles en las puntas de sus alas mientras vuela. Se desplazan hacia abajo y a sotavento lentamente. Una aeronave más pequeña que ingrese en esa estela puede perder el control aunque el cielo esté completamente despejado.',
    pills: [
      { variant: 'danger',  label: 'Pérdida de control' },
      { variant: 'caution', label: 'Persiste hasta 3 min' },
      { variant: 'caution', label: 'Se desplaza a sotavento' },
      { variant: 'note',    label: 'Separación mínima ATC' },
    ],
    curiosity: 'Las estelas de un A380 pueden voltear un avión pequeño varios minutos después de su paso. ATC aplica separaciones mínimas específicas por categoría de peso.',
  },
]

// ---------------------------------------------------------------------------
// Style maps
// ---------------------------------------------------------------------------

const PILL_STYLES: Record<PillVariant, { color: string; bg: string; border: string }> = {
  danger:  { color: '#ff6b6b', bg: 'rgba(255,0,0,.06)',    border: 'rgba(255,0,0,.3)'    },
  caution: { color: '#f0a030', bg: 'rgba(212,135,15,.06)', border: 'rgba(212,135,15,.3)' },
  note:    { color: '#5aaad8', bg: 'rgba(43,143,212,.06)', border: 'rgba(43,143,212,.3)' },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** DOM id of a cloud's catalog card: a cloud in the altitude diagram jumps here. */
const cloudCardId = (id: CloudId) => `nube-${id}`

function CloudCardItem({ cloud }: { cloud: CloudItem }) {
  const [aeroOpen, setAeroOpen] = useState(false)
  const aeroContentId = useId()
  const credito = creditoDe(cloud.id)

  return (
    <article
      id={cloudCardId(cloud.id)}
      className="border-b py-8 sm:py-10"
      style={{
        borderColor: 'var(--color-border)',
        ...(cloud.dangerLevel >= 5
          ? { borderLeft: '3px solid var(--color-crit)', paddingLeft: '12px' }
          : cloud.dangerLevel === 4
          ? { borderLeft: '3px solid var(--color-warn)', paddingLeft: '12px' }
          : {}),
      }}
    >
      <div className="flex flex-col sm:flex-row gap-0">
        {/* Image + credit */}
        <figure className="m-0 shrink-0 w-full sm:w-[280px]">
        <div
          className="relative rounded overflow-hidden bg-[#0f2240] w-full h-[195px] sm:h-[200px]"
        >
          <img
            className="w-full h-full object-cover transition-transform duration-700 hover:scale-105"
            src={cloud.imgSrc}
            alt={cloud.imgAlt}
            title={textoCredito(credito)}
            loading="lazy"
          />
          <span
            className="absolute top-2 left-2 backdrop-blur text-[.58rem] font-medium tracking-widest uppercase text-slate-300 px-2 py-1 rounded-sm"
            style={{ background: 'rgba(6,13,26,.8)', border: '1px solid rgba(255,255,255,.1)' }}
          >
            {cloud.heightTag}
          </span>
        </div>
        <figcaption
          data-credito-foto
          className="mt-1.5 text-xs leading-snug"
          style={{ color: 'var(--color-muted-foreground)' }}
        >
          Foto: {credito.autor},{' '}
          {credito.licencia.url ? (
            <a href={credito.licencia.url} target="_blank" rel="noopener noreferrer" className="underline hover:opacity-80">
              {credito.licencia.nombre}
            </a>
          ) : (
            credito.licencia.nombre
          )}
          ,{' '}
          <a href={credito.fuente.url} target="_blank" rel="noopener noreferrer" className="underline hover:opacity-80">
            {credito.fuente.nombre}
          </a>
          {credito.redimensionada ? `, ${TEXTO_CAMBIOS}` : ''}
        </figcaption>
        </figure>

        {/* Body */}
        <div className="flex flex-col gap-3 justify-center sm:pl-8 pt-5 sm:pt-0">
          <div>
            <h3
              tabIndex={-1}
              className="text-[1.85rem] font-normal leading-tight outline-none"
              style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
            >
              {cloud.name}
            </h3>
            <div className="text-[.63rem] font-medium tracking-widest uppercase mt-1" style={{ color: 'var(--color-primary)' }}>
              {cloud.latin}
            </div>
          </div>

          <div className="flex gap-5 flex-wrap text-[.75rem]" style={{ color: 'var(--color-muted-foreground)' }}>
            <span>📍 {cloud.height}</span>
            <span>{cloud.composition.startsWith('🧊') || cloud.composition.startsWith('💧') || cloud.composition.startsWith('☀️') || cloud.composition.startsWith('⚡') ? '' : ''}
              {['La nube de tormenta', 'La nube de buen tiempo', 'La más común del planeta'].includes(cloud.composition)
                ? `☁ ${cloud.composition}`
                : cloud.composition.includes('Cristales') ? `🧊 ${cloud.composition}` : `💧 ${cloud.composition}`
              }
            </span>
          </div>

          <div>
            <DangerScale level={cloud.dangerLevel} />
            <div className="mt-1.5">
              <StatusBadge variant={cloud.badge} label={cloud.badgeLabel} />
            </div>
          </div>

          <p className="text-[.87rem] leading-[1.75]" style={{ color: 'var(--color-foreground)', opacity: 0.85 }}>
            {cloud.description}
          </p>

          <div className="flex items-center gap-1.5 text-[.63rem]" style={{ color: '#60819a' }}>
            <span>👁</span>
            <span>Mejor observarlos:</span>
            <span style={{ color: 'var(--color-muted-foreground)', marginLeft: '2px' }}>{cloud.observeTip}</span>
          </div>

          {/* Aero toggle */}
          <button
            className="self-start text-[.68rem] font-medium border rounded-sm px-3 py-1 transition-colors cursor-pointer"
            style={{
              color: '#5aaad8',
              borderColor: 'rgba(43,143,212,.35)',
              background: aeroOpen ? 'rgba(43,143,212,.08)' : 'transparent',
            }}
            onClick={() => setAeroOpen(v => !v)}
            aria-expanded={aeroOpen}
            aria-controls={aeroContentId}
          >
            ✈️ Ver significado aeronáutico {aeroOpen ? '▴' : '▾'}
          </button>

          {aeroOpen && (
            <div
              id={aeroContentId}
              className="rounded p-4 flex flex-col gap-2"
              style={{ background: '#0f2240', border: '1px solid var(--color-border)' }}
            >
              <p className="text-[.8rem] leading-[1.7]" style={{ color: 'var(--color-muted-foreground)' }}>
                {cloud.aeroText}
              </p>
              <p
                className="pl-3 text-[.77rem] italic leading-[1.65]"
                style={{
                  color: 'var(--color-muted-foreground)',
                  opacity: 0.75,
                  borderLeft: '2px solid #5a4515',
                }}
              >
                💡 {cloud.curiosity}
              </p>
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

function AeroCardItem({ item }: { item: AeroItem }) {
  return (
    <article
      className="border-b py-8 sm:py-10"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <div className="flex flex-col sm:flex-row gap-0">
        {/* Placeholder */}
        <div
          className="flex flex-col items-center justify-center rounded shrink-0 w-full sm:w-[280px] h-[160px] sm:h-[200px]"
          style={{ background: '#0f2240', border: '1px solid var(--color-border)' }}
        >
          <span className="text-5xl opacity-20">{item.emoji}</span>
          <p className="text-[.63rem] text-center mt-3 px-6 leading-5" style={{ color: 'var(--color-muted-foreground)', opacity: 0.75 }}>
            Fenómeno invisible — solo detectable por instrumentos y sus efectos
          </p>
        </div>

        {/* Body */}
        <div className="flex flex-col gap-3 justify-center sm:pl-8 pt-5 sm:pt-0">
          <div>
            <h3
              className="text-[1.85rem] font-normal leading-tight"
              style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
            >
              {item.name}
            </h3>
            <div className="text-[.63rem] font-medium tracking-widest uppercase mt-1" style={{ color: 'var(--color-primary)' }}>
              {item.latin}
            </div>
          </div>

          <div className="flex gap-5 flex-wrap text-[.75rem]" style={{ color: 'var(--color-muted-foreground)' }}>
            <span>📍 {item.height}</span>
            <span>⚠️ {item.detail}</span>
          </div>

          <div>
            <DangerScale level={item.dangerLevel} />
            <div className="mt-1.5">
              <StatusBadge variant={item.badge} label={item.badgeLabel} />
            </div>
          </div>

          <p className="text-[.87rem] leading-[1.75]" style={{ color: 'var(--color-foreground)', opacity: 0.85 }}>
            {item.description}
          </p>

          <div className="flex flex-wrap gap-1.5 mt-0.5">
            {item.pills.map(pill => {
              const s = PILL_STYLES[pill.variant]
              return (
                <span
                  key={pill.label}
                  className="text-[.63rem] font-medium px-2.5 py-0.5 rounded-full border"
                  style={{ color: s.color, background: s.bg, borderColor: s.border }}
                >
                  {pill.label}
                </span>
              )
            })}
          </div>

          <p
            className="pl-3 text-[.77rem] italic leading-[1.65]"
            style={{
              color: 'var(--color-muted-foreground)',
              opacity: 0.75,
              borderLeft: '2px solid #5a4515',
            }}
          >
            💡 {item.curiosity}
          </p>
        </div>
      </div>
    </article>
  )
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

// Cloud family headings live with the catalog (CLOUD_FAMILY_SECTIONS); this is the extra one.
const CLOUD_FAMILY_ORDER: readonly CloudFamily[] = ['alta', 'media', 'baja', 'vertical', 'especial']

const AERO_SECTION = {
  title: 'Fenómenos aeronáuticos',
  subtitle: 'Lo que no se ve a simple vista pero define la seguridad en vuelo',
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div
      className="flex items-baseline gap-4 mt-12 pb-3 border-b"
      style={{ borderColor: 'var(--color-border)' }}
    >
      <h2
        className="text-2xl italic font-normal"
        style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}
      >
        {title}
      </h2>
      <p className="text-[.74rem] hidden sm:block" style={{ color: 'var(--color-muted-foreground)', opacity: 0.75 }}>
        {subtitle}
      </p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function Nubes() {
  const reducedMotion = useReducedMotion()

  /** From the altitude diagram to the cloud's full card. */
  function openCard(id: CloudId) {
    const card = document.getElementById(cloudCardId(id))
    if (!card) return
    revealBelowHeader(card, { align: 'start', smooth: !reducedMotion })
    card.querySelector<HTMLElement>('h3')?.focus({ preventScroll: true })
  }

  return (
    <div className="relative">
      <Dither opacity={0.03} />

      <FadeContent>
        {/* Hero */}
        <div className="relative text-center px-2 pt-6 pb-10 border-b" style={{ borderColor: 'var(--color-border)' }}>
          <p
            className="inline-flex items-center gap-3 text-[.62rem] font-medium tracking-[.28em] uppercase mb-5"
            style={{ color: '#c8a84b' }}
          >
            <span className="block w-7 h-px" style={{ background: 'rgba(110,88,32,.6)' }} />
            Catálogo visual del cielo
            <span className="block w-7 h-px" style={{ background: 'rgba(110,88,32,.6)' }} />
          </p>
          <h1 className="sr-only">Lo que el cielo te está diciendo</h1>
          <div aria-hidden="true" className="flex justify-center">
            <DriftText text="Lo que el cielo te está diciendo" fontSize="3rem" />
          </div>
          <p className="mt-5 text-[.96rem] max-w-md mx-auto leading-[1.8]" style={{ color: 'var(--color-muted-foreground)' }}>
            Nubes, fenómenos y señales invisibles. Todo lo que pasa allá arriba tiene nombre — y algo que contarte sobre lo que viene.
          </p>

          <CloudSkyDiagram onOpenCard={openCard} />
        </div>

        {/* Cloud sections */}
        {CLOUD_FAMILY_ORDER.map(family => {
          const sectionClouds = CLOUDS.filter(c => c.family === family)
          if (sectionClouds.length === 0) return null
          const sec = CLOUD_FAMILY_SECTIONS[family]
          return (
            <div key={family}>
              <SectionHeader title={sec.title} subtitle={sec.subtitle} />
              {sectionClouds.map(cloud => (
                <CloudCardItem key={cloud.id} cloud={cloud} />
              ))}
            </div>
          )
        })}

        {/* Aero section */}
        <div>
          <SectionHeader title={AERO_SECTION.title} subtitle={AERO_SECTION.subtitle} />
          {AERO.map(item => (
            <AeroCardItem key={item.id} item={item} />
          ))}
        </div>

        {/* Footer note */}
        <div
          className="mt-16 pb-6 text-center text-[.67rem] leading-[2]"
          style={{ color: 'var(--color-muted-foreground)', opacity: 0.75 }}
        >
          Clasificación basada en el{' '}
          <a
            href="https://cloudatlas.wmo.int"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:opacity-100 transition-opacity"
          >
            Atlas Internacional de Nubes (OMM)
          </a>
          {' '}·{' '}
          Información aeronáutica con fines divulgativos — consultar documentación oficial OACI/ANAC para operaciones reales.
        </div>
      </FadeContent>
    </div>
  )
}
