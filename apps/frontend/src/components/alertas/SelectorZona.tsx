import { useId } from 'react'
import { COPY, lineaCiudad } from '@/lib/alertas/copy'
import { ZONAS_ALERTAS } from '@/lib/alertas/zonaSugerida'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

const COLLATOR = new Intl.Collator('es')
/** Las ciudades por orden alfabético: en una lista de 50 es lo más fácil de recorrer. */
const ZONAS_ORDENADAS = [...ZONAS_ALERTAS].sort((a, b) => COLLATOR.compare(a.nombre, b.nombre))

interface SelectorZonaProps {
  /** Slug de la ciudad elegida; null si todavía no hay una. */
  valor: string | null
  onCambio: (slug: string | null) => void
  /** Nombre de la ciudad más cercana a la ubicación, si hay; solo se usa para la línea de ayuda. */
  nombreSugerida: string | null
}

/** La ciudad de los avisos: un `<select>` nativo con su etiqueta visible y la ciudad sugerida como ayuda. */
export function SelectorZona({ valor, onCambio, nombreSugerida }: SelectorZonaProps) {
  const idSelect = useId()
  const idAyuda = useId()

  return (
    <div className="space-y-1.5">
      <label htmlFor={idSelect} className="block text-sm font-semibold text-[var(--color-foreground)]">
        {COPY.etiquetaCiudad}
      </label>
      <select
        id={idSelect}
        value={valor ?? ''}
        onChange={(event) => onCambio(event.target.value === '' ? null : event.target.value)}
        aria-describedby={idAyuda}
        className={`min-h-11 w-full rounded-lg border border-[var(--color-border-strong)] bg-[var(--color-card)] px-3 text-sm text-[var(--color-foreground)] ${FOCUS_RING}`}
      >
        <option value="">{COPY.opcionCiudad}</option>
        {ZONAS_ORDENADAS.map((zona) => (
          <option key={zona.slug} value={zona.slug}>
            {`${zona.nombre} (${zona.provincia})`}
          </option>
        ))}
      </select>
      <p id={idAyuda} className="text-sm text-[var(--color-muted-foreground)]">
        {lineaCiudad(nombreSugerida)}
      </p>
    </div>
  )
}
