import { COPY, mensajeDeDisponibilidad, notaInstalarIos } from '@/lib/alertas/copy'
import type { Disponibilidad } from '@/lib/alertas/plataforma'

interface PasosInstalarIosProps {
  disponibilidad: Extract<Disponibilidad, { tipo: 'instalar-ios' }>
}

/** iPhone sin instalar: los pasos para agregar SkyPulse a la pantalla de inicio, que es lo que habilita los avisos. */
export function PasosInstalarIos({ disponibilidad }: PasosInstalarIosProps) {
  return (
    <section className="space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4">
      <h2 className="text-base font-semibold text-[var(--color-foreground)]">{COPY.tituloInstalarIos}</h2>
      <p className="text-sm leading-relaxed text-[var(--color-muted-foreground)]">
        {mensajeDeDisponibilidad(disponibilidad)}
      </p>
      <ol className="list-decimal space-y-2 pl-6 text-sm leading-relaxed text-[var(--color-foreground)]">
        {disponibilidad.pasos.map((paso) => (
          <li key={paso}>{paso}</li>
        ))}
      </ol>
      <p className="text-sm leading-relaxed text-[var(--color-muted-foreground)]">
        {notaInstalarIos(disponibilidad.versionMinima)}
      </p>
    </section>
  )
}
