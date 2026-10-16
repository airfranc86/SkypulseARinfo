import { ChevronLeft, ChevronRight } from 'lucide-react'
import type { HoraDelManifest } from '@/lib/isobaras/formato'
import { textoDeLaHora } from '@/lib/isobaras/horas'

interface HourSliderProps {
  horas: ReadonlyArray<HoraDelManifest>
  /** Index into `horas` of the hour being shown. */
  indice: number
  onCambio: (indice: number) => void
}

const BOTON =
  'inline-flex items-center justify-center rounded-lg disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2'

/** Slider over the forecast hours, with previous/next buttons (44 px touch targets) and the hour in Argentine time. */
export function HourSlider({ horas, indice, onCambio }: HourSliderProps) {
  const actual = horas[indice]
  const texto = actual ? textoDeLaHora(actual.valid) : '—'
  return (
    <div
      className="rounded-xl p-3 flex items-center gap-3"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <button
        type="button"
        className={BOTON}
        style={{ width: 44, height: 44, border: '1px solid var(--color-border-strong)', color: 'var(--color-foreground)' }}
        aria-label="Hora anterior"
        disabled={indice <= 0}
        onClick={() => onCambio(indice - 1)}
      >
        <ChevronLeft size={20} aria-hidden="true" />
      </button>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-center mb-1" style={{ color: 'var(--color-foreground)' }}>
          {texto}
          <span className="font-normal" style={{ color: 'var(--color-muted-foreground)' }}>
            {actual ? ` · +${actual.f} h` : ''}
          </span>
        </p>
        <input
          type="range"
          className="w-full"
          style={{ height: 44 }}
          min={0}
          max={Math.max(0, horas.length - 1)}
          step={1}
          value={indice}
          aria-label="Hora del pronóstico"
          aria-valuetext={texto}
          onChange={(e) => onCambio(Number(e.target.value))}
        />
      </div>
      <button
        type="button"
        className={BOTON}
        style={{ width: 44, height: 44, border: '1px solid var(--color-border-strong)', color: 'var(--color-foreground)' }}
        aria-label="Hora siguiente"
        disabled={indice >= horas.length - 1}
        onClick={() => onCambio(indice + 1)}
      >
        <ChevronRight size={20} aria-hidden="true" />
      </button>
    </div>
  )
}
