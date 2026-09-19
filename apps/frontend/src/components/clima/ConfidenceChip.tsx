import type { DailyEntry } from '@/lib/api'

interface ConfidenceChipProps {
  label: DailyEntry['confidence_label']
}

/**
 * Aviso de que GFS y ECMWF no coinciden del todo ese día. "ALTA" no se anuncia: con un solo
 * modelo el backend la fija en 100 %, así que solo el aviso lleva información.
 */
export function ConfidenceChip({ label }: ConfidenceChipProps) {
  if (label === 'ALTA') return null
  return (
    <span
      className="text-[11px] px-2 py-0.5 rounded-full text-center"
      style={{
        border: '1px solid var(--color-border)',
        color: label === 'BAJA' ? 'var(--color-watch)' : 'var(--color-muted-foreground)',
      }}
    >
      Confianza {label === 'BAJA' ? 'baja' : 'media'}
    </span>
  )
}
