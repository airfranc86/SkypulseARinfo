import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { ContenidoPanel } from '@/components/asistente/ContenidoPanel'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useViewportVisual } from '@/hooks/useViewportVisual'
import type { UsoAsistente } from '@/hooks/useAsistente'
import { aceptarAviso, almacenLocal, avisoAceptado } from '@/lib/asistente/consentimiento'
import { TITULO_PANEL, textoDeValidacion } from '@/lib/asistente/copy'
import { destinoDelTab } from '@/lib/asistente/foco'
import type { HumorMora } from '@/lib/asistente/humor'
import type { RespuestaRapida } from '@/lib/asistente/respuestasRapidas'

export interface PanelAsistenteProps {
  /** Id of the dialog (the bubble points at it with `aria-controls`). */
  id: string
  abierto: boolean
  /** The mood Mora shows in the header (the panel's own or the weather's). */
  humor: HumorMora
  uso: UsoAsistente
  rapidas: readonly RespuestaRapida[]
  /** Px between the bottom of the screen and the panel on a wide screen (it sits above the bubble). */
  separacionInferior: number
  alCerrar: () => void
}

/** The elements of `raiz` the keyboard can reach, in order (visible, not disabled). */
function elementosEnfocables(raiz: HTMLElement): HTMLElement[] {
  const candidatos = raiz.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )
  return Array.from(candidatos).filter((elemento) => elemento.offsetParent !== null)
}

/**
 * Mora's question panel: a floating card above the bubble on a wide screen and a bottom sheet on a phone. It stays mounted
 * once opened (hidden when closed), so closing it by accident does not lose the answer nor cancel the question.
 *
 * On a wide screen it is not modal: the page behind stays usable. On a phone the sheet covers most of the screen, so there it
 * is modal (`aria-modal` and Tab stays inside it). It lifts above the on-screen keyboard (`useViewportVisual`) and never
 * takes more than the visible screen. The look is `ContenidoPanel`; this only holds the
 * text the person types, the first-use notice and the focus.
 */
export function PanelAsistente(props: PanelAsistenteProps) {
  const { abierto, uso } = props
  const [texto, setTexto] = useState('')
  const [mensaje, setMensaje] = useState<string | null>(null)
  const [aceptado, setAceptado] = useState(() => avisoAceptado(almacenLocal(window)))
  const campoRef = useRef<HTMLTextAreaElement | null>(null)
  const entendidoRef = useRef<HTMLButtonElement | null>(null)
  const alMontarCampo = useCallback((el: HTMLTextAreaElement | null) => {
    campoRef.current = el
  }, [])
  const alMontarEntendido = useCallback((el: HTMLButtonElement | null) => {
    entendidoRef.current = el
  }, [])
  const esAncho = useMediaQuery('(min-width: 640px)')
  // On a wide screen the card floats above the bubble: that space is not available height.
  const { desplazamiento, alturaMaxima } = useViewportVisual(abierto, esAncho ? props.separacionInferior : 0)

  // When it opens, the focus goes to what the person has to do: accept the notice or write.
  useEffect(() => {
    if (!abierto) return undefined
    const foco = setTimeout(() => (aceptado ? campoRef : entendidoRef).current?.focus({ preventScroll: true }), 0)
    return () => clearTimeout(foco)
  }, [abierto, aceptado])

  const alEnviar = () => {
    const resultado = uso.enviar(texto)
    if (resultado === 'vacia' || resultado === 'larga' || resultado === 'sin-ubicacion') {
      setMensaje(textoDeValidacion(resultado))
    } else if (resultado === 'enviada') {
      setMensaje(null)
    }
  }

  // On a phone (modal) Tab wraps around inside the sheet instead of walking to the page hidden under it.
  const alTeclear = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab' || esAncho) return
    const lista = elementosEnfocables(e.currentTarget)
    if (lista.length === 0) {
      e.preventDefault()
      return
    }
    const destino = destinoDelTab(lista.indexOf(document.activeElement as HTMLElement), lista.length, e.shiftKey)
    if (destino !== null) {
      e.preventDefault()
      lista[destino].focus()
    }
  }

  const alEntender = () => {
    aceptarAviso(almacenLocal(window)) // if it cannot be saved it is asked again next time; this session goes on
    setAceptado(true)
  }

  return (
    <div
      id={props.id}
      role="dialog"
      aria-label={TITULO_PANEL}
      aria-modal={esAncho ? undefined : true}
      hidden={!abierto}
      onKeyDown={alTeclear}
      className="fixed inset-x-0 bottom-[var(--mora-desplazamiento)] z-50 flex flex-col overflow-hidden rounded-t-2xl border border-b-0 border-[var(--color-border)] shadow-2xl sm:inset-x-auto sm:bottom-[calc(var(--mora-separacion)+var(--mora-desplazamiento))] sm:left-6 sm:w-96 sm:rounded-2xl sm:border-b"
      style={
        {
          '--mora-desplazamiento': `${desplazamiento}px`,
          '--mora-separacion': `${props.separacionInferior}px`,
          maxHeight: alturaMaxima,
          background: 'var(--color-card)',
        } as CSSProperties
      }
    >
      <div className="min-h-0 overflow-y-auto overscroll-contain">
        <ContenidoPanel
          humor={props.humor}
          avisoPendiente={!aceptado}
          estado={uso.estado}
          texto={texto}
          mensajeValidacion={mensaje}
          esperaSegundos={uso.esperaSegundos}
          rapidas={props.rapidas}
          alMontarCampo={alMontarCampo}
          alMontarEntendido={alMontarEntendido}
          alCambiarTexto={(t) => {
            setTexto(t)
            if (mensaje !== null) setMensaje(null)
          }}
          alEnviar={alEnviar}
          alEntender={alEntender}
          alCerrar={props.alCerrar}
        />
      </div>
    </div>
  )
}
