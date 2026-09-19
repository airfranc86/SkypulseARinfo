import { AlertTriangle, CircleAlert, Info, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import { LEVEL_COLOR, alertLevel, alertSummary, sortAlertas, vigenciaText, type AlertLevel } from '@/lib/smnAlertas'
import type { SmnAlerta } from '@/lib/api'

interface SmnAlertasBlockProps {
  alertas: SmnAlerta[]
  /** El SMN no respondió: la ausencia de avisos no significa que no haya. */
  unavailable?: boolean
  /** Hora de referencia (ms) para la vigencia de cada aviso. */
  nowMs?: number
  /** Los avisos todavía no llegaron: se reserva una línea en vez de dejar que empujen el resto al llegar. */
  pending?: boolean
}

/**
 * El peso visual escala con la gravedad (principio 3): rojo y naranja llevan borde completo, fondo
 * más cargado, ícono propio y título de 16 px (el rojo suma el enlace a la fuente); amarillo es una línea de 14 px.
 * El nivel también se dice con la palabra y con la forma del ícono, no solo con el color.
 */
const STYLE: Record<AlertLevel, { Icon: LucideIcon; tint: string; border: string; strong: boolean }> = {
  rojo:     { Icon: OctagonAlert,  tint: '24', border: '2px solid',   strong: true },
  naranja:  { Icon: TriangleAlert, tint: '1f', border: '1.5px solid', strong: true },
  amarillo: { Icon: CircleAlert,   tint: '14', border: '1px solid',   strong: false },
  verde:    { Icon: Info,          tint: '14', border: '1px solid',   strong: false },
  otro:     { Icon: Info,          tint: '14', border: '1px solid',   strong: false },
}

const SMN_URL = 'https://www.smn.gob.ar/'

/** Avisos oficiales del SMN, mostrados tal cual vienen de la fuente — sin interpretación propia. */
export function SmnAlertasBlock({ alertas, unavailable = false, nowMs = Number.NaN, pending = false }: SmnAlertasBlockProps) {
  if (pending && !unavailable && alertas.length === 0) {
    return (
      <p
        role="status"
        className="mb-4 rounded-xl px-4 py-3 text-xs"
        style={{ border: '1px solid var(--color-border)', color: 'var(--color-muted-foreground)' }}
      >
        Consultando avisos del SMN…
      </p>
    )
  }

  if (unavailable) {
    return (
      <p
        className="mb-4 rounded-xl px-4 py-3 text-xs leading-relaxed flex items-start gap-2"
        style={{
          border: '1px solid var(--color-border)',
          background: 'var(--color-secondary)',
          color: 'var(--color-muted-foreground)',
        }}
      >
        <AlertTriangle size={14} strokeWidth={2} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>
          No pudimos consultar los avisos del SMN, así que no sabemos si hay alguno vigente. Consultalos en{' '}
          <a
            href={SMN_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
            style={{ color: 'var(--color-foreground)' }}
          >
            smn.gob.ar
          </a>
          .
        </span>
      </p>
    )
  }

  if (alertas.length === 0) return null

  const summary = alertSummary(alertas, nowMs)

  return (
    <section aria-labelledby="smn-alertas-title" className="mb-4 space-y-2">
      {/* Un solo anuncio para todos los avisos críticos (una oración por aviso): cuando llegan después
          del pronóstico, nada más en pantalla avisa que apareció algo grave. */}
      {summary && <p role="alert" className="sr-only">{summary}</p>}
      <h2
        id="smn-alertas-title"
        className="text-xs uppercase tracking-wide font-medium"
        style={{ color: 'var(--color-muted-foreground)' }}
      >
        Avisos oficiales — SMN
      </h2>
      <ul className="space-y-2">
        {sortAlertas(alertas).map((alerta, i) => {
          const level = alertLevel(alerta.nivel)
          const color = LEVEL_COLOR[level]
          const { Icon, tint, border, strong } = STYLE[level]
          const vigencia = vigenciaText(alerta, nowMs)
          return (
            <li
              key={i}
              className="rounded-xl px-4 py-3 space-y-1.5"
              style={{ background: `${color}${tint}`, border: `${border} ${strong ? color : `${color}66`}` }}
            >
              <div className="flex items-center gap-2 flex-wrap">
                {/* Relleno sólido con texto oscuro: 6,4:1 en rojo, 8,4:1 en naranja, 11,3:1 en amarillo */}
                <span
                  className="inline-flex items-center gap-1 text-xs font-bold uppercase px-2 py-0.5 rounded-full"
                  style={{ background: color, color: '#160a0a' }}
                >
                  <Icon size={14} strokeWidth={2.25} aria-hidden="true" />
                  {alerta.nivel}
                </span>
                <span
                  className={strong ? 'text-base font-semibold' : 'text-sm font-medium'}
                  style={{ color: 'var(--color-foreground)' }}
                >
                  {alerta.tipo}
                </span>
                {vigencia && (
                  <span className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                    · {vigencia}
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
                {alerta.descripcion}
              </p>
              {level === 'rojo' && (
                <a
                  href={SMN_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center min-h-[44px] text-sm font-medium underline"
                  style={{ color: 'var(--color-foreground)' }}
                >
                  Ver el aviso completo en smn.gob.ar
                </a>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
