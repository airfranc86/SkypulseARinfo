import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Pause, Play } from 'lucide-react'
import type { HoraDelManifest } from '@/lib/isobaras/formato'
import { textoDeLaHora } from '@/lib/isobaras/horas'
import {
  ESPERA_MAXIMA_MS,
  PASO_REPRODUCCION_MS,
  indiceSiguienteEnBucle,
  puedeAvanzar,
} from '@/lib/isobaras/reproduccion'

interface HourSliderProps {
  horas: ReadonlyArray<HoraDelManifest>
  /** Index into `horas` of the hour being shown. */
  indice: number
  onCambio: (indice: number) => void
  /** Forecast hour (`f`) drawn on the map right now, or null while none is. Playback waits for it. */
  fDibujada: number | null
}

const BOTON =
  'inline-flex items-center justify-center rounded-lg disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2'

/** Play button colours, indexed by "is playing" (0 = stopped, 1 = playing): the accent shows it is on. */
const COLOR_BORDE_PLAY = ['var(--color-border-strong)', 'var(--color-primary)'] as const
const COLOR_TEXTO_PLAY = ['var(--color-foreground)', 'var(--color-primary)'] as const

/**
 * Slider over the forecast hours, with play, previous and next buttons (44 px touch targets) and the hour in
 * Argentine time. Playing steps through the hours in a loop; touching the slider or the arrows, hiding the tab or an
 * hour that does not arrive pauses it.
 */
export function HourSlider({ horas, indice, onCambio, fDibujada }: HourSliderProps) {
  const [reproduciendo, setReproduciendo] = useState(false)
  const actual = horas[indice]
  const texto = actual ? textoDeLaHora(actual.valid) : '—'
  const dibujada = puedeAvanzar(actual?.f ?? null, fDibujada)

  // A chain of timeouts, not an interval: each step starts only after the previous hour is on the map, and every
  // change of hour cancels the pending one.
  useEffect(() => {
    if (!reproduciendo || !dibujada) return
    const espera = window.setTimeout(() => onCambio(indiceSiguienteEnBucle(indice, horas.length)), PASO_REPRODUCCION_MS)
    return () => window.clearTimeout(espera)
  }, [reproduciendo, dibujada, indice, horas.length, onCambio])

  // The hour asked for never got drawn (slow network, failed file): stop instead of showing "playing" forever.
  useEffect(() => {
    if (!reproduciendo || dibujada) return
    const espera = window.setTimeout(() => setReproduciendo(false), ESPERA_MAXIMA_MS)
    return () => window.clearTimeout(espera)
  }, [reproduciendo, dibujada, indice])

  useEffect(() => {
    if (!reproduciendo) return
    const alCambiarVisibilidad = () => {
      if (document.hidden) setReproduciendo(false)
    }
    document.addEventListener('visibilitychange', alCambiarVisibilidad)
    return () => document.removeEventListener('visibilitychange', alCambiarVisibilidad)
  }, [reproduciendo])

  // Whoever moves the slider or the arrows takes control: playback stops. The automatic step does not go through here.
  const cambioManual = (i: number) => {
    setReproduciendo(false)
    onCambio(i)
  }

  return (
    <div
      className="rounded-xl p-3 flex items-center gap-3"
      style={{ background: 'var(--color-card)', border: '1px solid var(--color-border)' }}
    >
      <button
        type="button"
        className={BOTON}
        style={{ width: 44, height: 44, border: `1px solid ${COLOR_BORDE_PLAY[+reproduciendo]}`, color: COLOR_TEXTO_PLAY[+reproduciendo] }}
        aria-label="Reproducir las horas"
        aria-pressed={reproduciendo}
        disabled={horas.length < 2}
        onClick={() => setReproduciendo((r) => !r)}
      >
        {reproduciendo ? <Pause size={20} aria-hidden="true" /> : <Play size={20} aria-hidden="true" />}
      </button>
      <button
        type="button"
        className={BOTON}
        style={{ width: 44, height: 44, border: '1px solid var(--color-border-strong)', color: 'var(--color-foreground)' }}
        aria-label="Hora anterior"
        disabled={indice <= 0}
        onClick={() => cambioManual(indice - 1)}
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
          onChange={(e) => cambioManual(Number(e.target.value))}
        />
      </div>
      <button
        type="button"
        className={BOTON}
        style={{ width: 44, height: 44, border: '1px solid var(--color-border-strong)', color: 'var(--color-foreground)' }}
        aria-label="Hora siguiente"
        disabled={indice >= horas.length - 1}
        onClick={() => cambioManual(indice + 1)}
      >
        <ChevronRight size={20} aria-hidden="true" />
      </button>
    </div>
  )
}
