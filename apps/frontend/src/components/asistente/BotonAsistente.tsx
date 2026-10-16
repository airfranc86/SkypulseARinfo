import { useEffect, useRef, useState } from 'react'
import { Mascota } from '@/components/asistente/Mascota'
import { useHumorMora } from '@/hooks/useHumorMora'
import { useParpadeo } from '@/hooks/useParpadeo'

/**
 * Bigger than the "Volver al inicio" bubble on the right (44 px): at 44 px Mora's detail does not read (owner feedback, 72 px).
 * Same margin as that bubble, so both sit on the same line of the screen.
 */
const SIZE = 72
const MARGIN = 24

/** How long the note stays open by itself. */
const NOTA_MS = 4000

const NOTA = 'Pronto vas a poder preguntarme por el clima'

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
 * Mora's floating bubble, bottom-left (the "Volver al inicio" one stays bottom-right). It shows her mood, which
 * comes from the forecast and the SMN warnings that other pages already loaded; it never asks for data.
 *
 * For now it does not answer questions (the panel comes later): a tap opens a one-line note that closes by itself
 * after 4 s, with Escape or with a tap outside. Only mounted when the assistant flag is on (see App.tsx).
 */
export function BotonAsistente({ lat, lon, oculto }: BotonAsistenteProps) {
  const humor = useHumorMora(lat, lon)
  const { parpadeo, alTerminarParpadeo } = useParpadeo(humor === 'dormido')
  const [abierta, setAbierta] = useState(false)
  const contenedor = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierta) return undefined
    const cerrarSola = setTimeout(() => setAbierta(false), NOTA_MS)
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAbierta(false)
    }
    const alTocarFuera = (e: PointerEvent) => {
      if (e.target instanceof Node && !contenedor.current?.contains(e.target)) setAbierta(false)
    }
    document.addEventListener('keydown', alTeclear)
    document.addEventListener('pointerdown', alTocarFuera)
    return () => {
      clearTimeout(cerrarSola)
      document.removeEventListener('keydown', alTeclear)
      document.removeEventListener('pointerdown', alTocarFuera)
    }
  }, [abierta])

  if (oculto) return null

  return (
    <div ref={contenedor} style={{ position: 'fixed', bottom: MARGIN, left: MARGIN, zIndex: 50 }}>
      {/* a live region that is always there and never `visibility: hidden` (that would take it out of the accessibility
          tree and the text would not be announced when it appears): empty text, opacity 0 and no pointer events hide it */}
      <div
        role="status"
        className="pointer-events-none absolute bottom-full left-0 mb-2 w-max max-w-[min(15rem,calc(100vw-3rem))] rounded-xl border border-[var(--color-border)] px-3 py-2 text-sm shadow-lg motion-reduce:transition-none"
        style={{
          background: 'color-mix(in srgb, var(--color-background) 92%, transparent)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          color: 'var(--color-foreground)',
          opacity: abierta ? 1 : 0,
          transform: abierta ? 'translateY(0)' : 'translateY(4px)',
          transition: 'opacity 200ms ease, transform 200ms ease',
        }}
      >
        {abierta ? NOTA : ''}
      </div>
      <button
        type="button"
        aria-label="Preguntarle a Mora"
        onClick={() => setAbierta((v) => !v)}
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
    </div>
  )
}
