import { useState, useRef, useEffect } from 'react'
import { Info } from 'lucide-react'

export type ModelKey = 'smn' | 'gfs' | 'usgs' | 'emsc' | 'windy_ecmwf' | 'openmeteo' | 'mixed' | 'segemar'
type Variant = 'pill' | 'inline' | 'header'

interface ModelMeta {
  label: string
  org: string
  color: string
  description: string
  reliability?: string
  updateFreq?: string
}

const MODELS: Record<ModelKey, ModelMeta> = {
  smn: {
    label: 'SMN',
    org: 'Argentina',
    color: '#3ecf7a',
    description: 'Observación real desde estaciones meteorológicas del SMN.',
    reliability: 'Precisión alta (dato medido, no pronóstico)',
    updateFreq: 'Cada 1h',
  },
  gfs: {
    label: 'GFS',
    org: 'NOAA',
    color: '#c8a84b',
    description: 'Modelo numérico global de NOAA, vía Windy.',
    reliability: '~85% a 3 días · ~70% a 7 días',
    updateFreq: '4 veces al día',
  },
  windy_ecmwf: {
    label: 'ECMWF',
    org: 'Windy',
    color: '#c8a84b',
    description: 'Modelo europeo de pronóstico, vía Windy.',
    reliability: '~90% a 3 días',
    updateFreq: '2 veces al día',
  },
  usgs: {
    label: 'USGS',
    org: 'EE.UU.',
    color: '#e05545',
    description: 'Red sísmica global del U.S. Geological Survey.',
    reliability: 'Tiempo real',
    updateFreq: 'Continua',
  },
  emsc: {
    label: 'EMSC',
    org: 'Europa',
    color: '#e05545',
    description: 'Centro Sismológico Europeo · incluye red NSNA/INPRES de Argentina con menor latencia.',
    reliability: 'Tiempo real · datos INPRES',
    updateFreq: 'Continua',
  },
  openmeteo: {
    label: 'Open-Meteo',
    org: 'Fallback',
    color: '#90aabb',
    description: 'Fuente de respaldo. Los datos pueden diferir de las otras fuentes.',
    reliability: 'Variable',
    updateFreq: 'Cada hora',
  },
  segemar: {
    label: 'OAVV',
    org: 'SEGEMAR',
    color: '#e05545',
    description: 'Observatorio Argentino de Vigilancia Volcánica del Servicio Geológico Minero Argentino.',
    reliability: 'Fuente oficial Argentina',
    updateFreq: 'Caché 2h',
  },
  mixed: {
    label: 'SMN + GFS',
    org: 'Mixto',
    color: '#c8a84b',
    description: 'Esta página combina observación en tiempo real (SMN) y pronóstico numérico (GFS · NOAA).',
    reliability: 'Actual: alta (SMN) · Pronóstico: ~85% a 3d',
    updateFreq: 'SMN: 1h · GFS: 4x/día',
  },
}

interface Props {
  model: ModelKey
  variant?: Variant
}

/**
 * Badge informativo que indica el modelo meteorológico de una sección.
 * Variantes:
 * - `header`: pill al lado del subtitle en PageHeader (con ícono info)
 * - `inline`: badge pequeño en esquina de card (requiere position:relative en el padre)
 */
export function ModelBadge({ model, variant = 'inline' }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const meta = MODELS[model]

  useEffect(() => {
    if (!open) return
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    document.addEventListener('keydown', onEscape)
    return () => {
      document.removeEventListener('mousedown', onClickOutside)
      document.removeEventListener('keydown', onEscape)
    }
  }, [open])

  if (variant === 'inline') {
    return (
      <div ref={ref} style={{ position: 'absolute', top: 10, right: 10, zIndex: 2 }}>
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          aria-label={`Modelo de datos: ${meta.label} · ${meta.org}. Tap para más info.`}
          aria-expanded={open}
          className="text-[10px] font-medium px-2 py-1 rounded-full flex items-center gap-1 min-h-[28px] transition-opacity hover:opacity-100"
          style={{
            background: `${meta.color}1f`,
            color: meta.color,
            border: `1px solid ${meta.color}55`,
            opacity: 0.9,
          }}
        >
          <span aria-hidden="true" style={{ fontSize: '0.5rem' }}>●</span>
          {meta.label}
        </button>
        {open && <ModelPopover meta={meta} />}
      </div>
    )
  }

  if (variant === 'header') {
    return (
      <div ref={ref} className="relative inline-block">
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          aria-label={`Modelo: ${meta.label} · ${meta.org}. Tap para más info.`}
          aria-expanded={open}
          className="text-[11px] font-medium px-2.5 py-1 rounded-full inline-flex items-center gap-1.5 min-h-[28px] transition-opacity hover:opacity-100"
          style={{
            background: `${meta.color}14`,
            color: meta.color,
            border: `1px solid ${meta.color}44`,
            opacity: 0.85,
          }}
        >
          <span aria-hidden="true" style={{ fontSize: '0.5rem' }}>●</span>
          {meta.label}
          <span style={{ color: meta.color, opacity: 0.65 }}>· {meta.org}</span>
          <Info size={10} aria-hidden="true" style={{ opacity: 0.5 }} />
        </button>
        {open && <ModelPopover meta={meta} align="left" />}
      </div>
    )
  }

  return null
}

function ModelPopover({ meta, align = 'right' }: { meta: ModelMeta; align?: 'left' | 'right' }) {
  return (
    <div
      role="dialog"
      aria-label={`Información sobre ${meta.label}`}
      className="absolute mt-2 w-64 rounded-xl p-3 text-xs shadow-xl z-50"
      style={{
        background: 'var(--color-card)',
        border: `1px solid ${meta.color}55`,
        color: 'var(--color-foreground)',
        ...(align === 'right' ? { right: 0 } : { left: 0 }),
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <span aria-hidden="true" style={{ color: meta.color, fontSize: '0.65rem' }}>●</span>
        <span className="font-semibold">{meta.label}</span>
        <span style={{ color: 'var(--color-muted-foreground)' }}>· {meta.org}</span>
      </div>

      {/* Descripción */}
      <p style={{ color: 'var(--color-muted-foreground)', lineHeight: 1.5 }}>
        {meta.description}
      </p>

      {/* Fiabilidad */}
      {meta.reliability && (
        <div
          className="mt-2 pt-2 space-y-0.5"
          style={{ borderTop: `1px solid ${meta.color}22` }}
        >
          <p>
            <span style={{ color: 'var(--color-muted-foreground)' }}>Fiabilidad: </span>
            {meta.reliability}
          </p>
          {meta.updateFreq && (
            <p>
              <span style={{ color: 'var(--color-muted-foreground)' }}>Actualiza: </span>
              {meta.updateFreq}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
