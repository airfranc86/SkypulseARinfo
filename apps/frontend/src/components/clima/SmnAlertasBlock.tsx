import type { SmnAlerta } from '@/lib/api'

interface SmnAlertasBlockProps {
  alertas: SmnAlerta[]
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
export function SmnAlertasBlock({ alertas }: SmnAlertasBlockProps) {
  if (alertas.length === 0) return null

  return (
    <div className="space-y-2">
      <p className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--color-muted-foreground)' }}>
        Avisos oficiales — SMN
      </p>
      {alertas.map((alerta, i) => {
        const color = nivelColor(alerta.nivel)
        return (
          <div
            key={i}
            role="alert"
            className="rounded-xl px-4 py-3 space-y-1"
            style={{ background: `${color}14`, border: `1px solid ${color}44` }}
          >
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full"
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
          </div>
        )
      })}
    </div>
  )
}
