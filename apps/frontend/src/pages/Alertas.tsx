import { useMemo } from 'react'
import { ControlesAvisos } from '@/components/alertas/ControlesAvisos'
import { MensajeDisponibilidad } from '@/components/alertas/MensajeDisponibilidad'
import { PasosInstalarIos } from '@/components/alertas/PasosInstalarIos'
import { useAvisosPush } from '@/hooks/useAvisosPush'
import type { LocationState } from '@/hooks/useLocation'
import type { ConfigAlertas } from '@/lib/alertas/config'
import { COPY } from '@/lib/alertas/copy'
import { zonaMasCercana } from '@/lib/alertas/zonaSugerida'
import { SMN_URL } from '@/lib/smnAlertas'

interface Props {
  location: LocationState | null
  config: ConfigAlertas
}

/**
 * `/alertas` (FRA-357, T7b): activar, probar y desactivar los avisos de tormenta en el celular. La página es
 * accesible directo aunque la campana del header esté oculta. El permiso del navegador se pide solo al tocar
 * "Activar avisos", nunca al entrar.
 */
export function Alertas({ location, config }: Props) {
  // Con la ubicación por defecto (Buenos Aires de respaldo) no se sugiere nada: `zonaMasCercana` da null.
  const sugerida = useMemo(() => (location === null ? null : zonaMasCercana(location)), [location])
  const avisos = useAvisosPush(config, sugerida?.slug ?? null)
  const { disponibilidad } = avisos
  const { antes, enlace, despues } = COPY.aclaracionOficial

  return (
    <div className="max-w-2xl mx-auto py-8 space-y-6">
      <h1 className="text-2xl" style={{ fontFamily: 'var(--font-serif)', color: 'var(--color-foreground)' }}>
        {COPY.titulo}
      </h1>
      <div className="space-y-2">
        <p className="text-sm leading-relaxed text-[var(--color-muted-foreground)]">{COPY.intro}</p>
        <p className="text-sm leading-relaxed text-[var(--color-muted-foreground)]">
          {antes}{' '}
          <a
            href={SMN_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-sm underline underline-offset-4 hover:opacity-80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]"
            style={{ color: 'var(--color-primary)' }}
          >
            {enlace}
          </a>
          {despues}
        </p>
      </div>

      {disponibilidad.tipo === 'activar' && (
        <ControlesAvisos avisos={avisos} nombreSugerida={sugerida?.nombre ?? null} />
      )}
      {disponibilidad.tipo === 'instalar-ios' && <PasosInstalarIos disponibilidad={disponibilidad} />}
      {(disponibilidad.tipo === 'abrir-en-navegador' || disponibilidad.tipo === 'sin-soporte') && (
        <MensajeDisponibilidad disponibilidad={disponibilidad} />
      )}
    </div>
  )
}
