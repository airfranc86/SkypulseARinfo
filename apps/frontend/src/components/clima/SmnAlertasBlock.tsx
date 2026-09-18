import { AlertTriangle } from 'lucide-react'
import type { SmnAlerta } from '@/lib/api'

interface SmnAlertasBlockProps {
  alertas: SmnAlerta[]
  /** El SMN no respondió: la ausencia de avisos no significa que no haya. */
  unavailable?: boolean
}

const NIVEL_COLOR: Record<string, string> = {
  rojo: '#ff3333',
  naranja: '#e05545',
  amarillo: '#f0a030',
  verde: '#3ecf7a',
}

function nivelColor(nivel: string): string {
  return NIVEL_COLOR[nivel.toLowerCase()] ?? '#90aabb'
}

/** Avisos oficiales del SMN, mostrados tal cual vienen de la fuente — sin interpretación propia. */
export function SmnAlertasBlock({ alertas, unavailable = false }: SmnAlertasBlockProps) {
  if (unavailable) {
    return (
      <p
        className="rounded-xl px-4 py-3 text-xs leading-relaxed flex items-start gap-2"
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
            href="https://www.smn.gob.ar/"
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

  return (
    <section aria-labelledby="smn-alertas-title" className="space-y-2">
      <h2
        id="smn-alertas-title"
        className="text-xs uppercase tracking-wide font-medium"
        style={{ color: 'var(--color-muted-foreground)' }}
      >
        Avisos oficiales — SMN
      </h2>
      <ul className="space-y-2">
        {alertas.map((alerta, i) => {
          const color = nivelColor(alerta.nivel)
          return (
            <li
              key={i}
              className="rounded-xl px-4 py-3 space-y-1"
              style={{ background: `${color}14`, border: `1px solid ${color}44` }}
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span
                  className="text-[11px] font-semibold uppercase px-2 py-0.5 rounded-full"
                  style={{ background: `${color}26`, color }}
                >
                  {alerta.nivel}
                </span>
                <span className="text-xs font-medium" style={{ color: 'var(--color-foreground)' }}>
                  {alerta.tipo}
                </span>
              </div>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
                {alerta.descripcion}
              </p>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
