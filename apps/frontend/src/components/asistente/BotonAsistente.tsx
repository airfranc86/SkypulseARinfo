import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useLocation as useRutaActual } from 'react-router-dom'
import { Mascota } from '@/components/asistente/Mascota'
import { PanelAsistente } from '@/components/asistente/PanelAsistente'
import { useAsistente } from '@/hooks/useAsistente'
import { useHumorMora } from '@/hooks/useHumorMora'
import { useParpadeo } from '@/hooks/useParpadeo'
import { useRespuestasRapidas } from '@/hooks/useRespuestasRapidas'

/**
 * Bigger than the "Volver al inicio" bubble on the right (44 px): at 44 px Mora's detail does not read (owner feedback, 72 px).
 * Same margin as that bubble, so both sit on the same line of the screen.
 */
const SIZE = 72
const MARGIN = 24

/** Space between the bubble and the panel above it (wide screens). */
const SEPARACION = 12

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

export interface BotonAsistenteProps {
  /** The place the app is showing; Mora reads what the app already loaded for it (nothing is requested). */
  lat: number | null
  lon: number | null
  /** The cookie banner is open (it covers this corner): the bubble waits. */
  oculto: boolean
}

/**
 * Mora's floating bubble, bottom-left (the "Volver al inicio" one stays bottom-right). It shows her mood, which comes
 * from the forecast and the SMN warnings that other pages already loaded (it never asks for data), and opens the question
 * panel: a tap on the bubble opens or closes it; Escape (with the focus on the bubble or in the panel) and the panel's own
 * button close it and give the focus back here.
 * The panel's moods (thinking, answering, confused) take over the bubble while the panel is open or a question is on its way,
 * unless there is a warning.
 * Only mounted when the assistant flag is on (see App.tsx).
 */
export function BotonAsistente({ lat, lon, oculto }: BotonAsistenteProps) {
  const humorClima = useHumorMora(lat, lon)
  const { pathname } = useRutaActual()
  const uso = useAsistente(lat, lon, pathname)
  const [abierta, setAbierta] = useState(false)
  // The panel's moods (thinking, answering, confused) only exist while the panel is open or a question is on its way, and a
  // warning always wins over them (the priority in lib/asistente/humor.ts): once it is closed, the weather's mood comes back.
  const humorDelPanel = abierta || uso.estado.fase === 'enviando' ? uso.humor : null
  const humor = humorClima === 'alerta' ? humorClima : (humorDelPanel ?? humorClima)
  const { parpadeo, alTerminarParpadeo } = useParpadeo(humor === 'dormido')
  // The panel is mounted the first time it opens and stays mounted (hidden when closed): the answer is not lost.
  const [montado, setMontado] = useState(false)
  const rapidas = useRespuestasRapidas(lat, lon, abierta)
  const idPanel = useId()
  const boton = useRef<HTMLButtonElement>(null)
  const contenedor = useRef<HTMLDivElement>(null)

  const cerrar = useCallback(() => {
    setAbierta(false)
    boton.current?.focus()
  }, [])

  useEffect(() => {
    if (!abierta) return undefined
    const alTeclear = (e: KeyboardEvent) => {
      // Only with the focus on the bubble or inside the panel: another widget (the place search) uses Escape for itself.
      if (e.key === 'Escape' && !e.defaultPrevented && e.target instanceof Node && contenedor.current?.contains(e.target)) cerrar()
    }
    document.addEventListener('keydown', alTeclear)
    return () => document.removeEventListener('keydown', alTeclear)
  }, [abierta, cerrar])

  if (oculto) return null

  return (
    <div ref={contenedor} style={{ position: 'fixed', bottom: MARGIN, left: MARGIN, zIndex: 50 }}>
      <button
        ref={boton}
        type="button"
        aria-label="Preguntarle a Mora"
        aria-haspopup="dialog"
        aria-expanded={abierta}
        aria-controls={montado ? idPanel : undefined}
        onClick={() => {
          setMontado(true)
          setAbierta((v) => !v)
        }}
        className={`flex items-center justify-center overflow-hidden rounded-full border border-[var(--color-border)] p-0 transition-colors hover:border-[var(--color-primary)] motion-reduce:transition-none ${FOCUS_RING}`}
        style={{
          width: SIZE,
          height: SIZE,
          background: 'color-mix(in srgb, var(--color-background) 80%, transparent)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
          cursor: 'pointer',
        }}
      >
        <Mascota estado={humor} tamano={64} parpadeo={parpadeo} alTerminarParpadeo={alTerminarParpadeo} />
      </button>
      {montado && (
        <PanelAsistente
          id={idPanel}
          abierto={abierta}
          humor={humor}
          uso={uso}
          rapidas={rapidas}
          separacionInferior={MARGIN + SIZE + SEPARACION}
          alCerrar={cerrar}
        />
      )}
    </div>
  )
}
