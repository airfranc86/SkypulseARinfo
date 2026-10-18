import { useId, type FormEvent, type KeyboardEvent } from 'react'
import { Mascota } from '@/components/asistente/Mascota'
import { MAX_PREGUNTA } from '@/lib/asistente/cliente'
import {
  AVISO_PRIMER_USO,
  BOTON_CERRAR,
  BOTON_ENVIAR,
  ETIQUETA_PREGUNTA,
  PLACEHOLDER_PREGUNTA,
  TEXTO_ENVIANDO,
  textoContador,
  textoDeError,
  textoEsperaBoton,
  TITULO_PANEL,
  TITULO_RESPUESTAS_RAPIDAS,
} from '@/lib/asistente/copy'
import type { HumorMora } from '@/lib/asistente/humor'
import type { EstadoPanel } from '@/lib/asistente/panel'
import type { RespuestaRapida } from '@/lib/asistente/respuestasRapidas'

const FOCUS_RING =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--color-primary)]'

/** Red that keeps 4.5:1 on the card in both themes (the plain destructive red misses it by a hair on the dark card). */
const COLOR_ERROR = 'color-mix(in srgb, var(--color-destructive) 78%, var(--color-foreground))'

const BOTON_PRIMARIO = `inline-flex min-h-11 items-center justify-center rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-[var(--color-primary-foreground)] transition-colors hover:opacity-90 motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`

export interface ContenidoPanelProps {
  /** The mood Mora shows in the header. */
  humor: HumorMora
  /** The first-use notice has not been accepted yet: it is shown instead of the field. */
  avisoPendiente: boolean
  estado: EstadoPanel
  texto: string
  /** Why the last attempt was not sent (empty, too long, no place), or null. */
  mensajeValidacion: string | null
  /** Seconds the person has to wait before asking again; 0 when nothing blocks. */
  esperaSegundos: number
  /** Shown when the model could not answer. */
  rapidas: readonly RespuestaRapida[]
  /** Callback refs (not ref objects), so the container can focus them without reading a ref while rendering. */
  alMontarCampo?: (elemento: HTMLTextAreaElement | null) => void
  alMontarEntendido?: (elemento: HTMLButtonElement | null) => void
  alCambiarTexto: (texto: string) => void
  alEnviar: () => void
  alEntender: () => void
  /** Without it there is no close button (the review page shows the panel as a fixed picture). */
  alCerrar?: () => void
}

/** The errors where the model could not answer: there the quick answers (computed in the browser) are offered. */
function sinRespuestaDelModelo(estado: EstadoPanel): boolean {
  return (
    estado.fase === 'error' &&
    (estado.error.tipo === 'no-disponible' || estado.error.tipo === 'apagado' || estado.error.tipo === 'sin-conexion')
  )
}

function IconoCerrar() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  )
}

/**
 * What the question panel shows, with no state of its own: everything comes in as props. The container
 * (`PanelAsistente`) feeds it from `useAsistente`; the mascot review page feeds it fixed states to see them all.
 */
export function ContenidoPanel(props: ContenidoPanelProps) {
  const { humor, avisoPendiente, estado, texto, mensajeValidacion, esperaSegundos, rapidas } = props
  const { alMontarCampo, alMontarEntendido, alCambiarTexto, alEnviar, alEntender, alCerrar } = props
  const campoId = useId()
  const contadorId = useId()
  const validacionId = useId()
  const rapidasId = useId()

  const enviando = estado.fase === 'enviando'
  const bloqueado = esperaSegundos > 0
  const sobreElLimite = Array.from(texto).length > MAX_PREGUNTA

  const alEnviarForm = (e: FormEvent) => {
    e.preventDefault()
    alEnviar()
  }
  const alTeclear = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends (Shift+Enter writes a new line); never while an IME composition (e.g. a phone keyboard) is open.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      alEnviar()
    }
  }

  return (
    <div className="flex min-h-0 flex-col gap-3 p-4">
      <header className="flex items-center gap-3">
        <Mascota estado={humor} tamano={44} />
        <h2 className="flex-1 text-base font-semibold" style={{ color: 'var(--color-foreground)' }}>
          {TITULO_PANEL}
        </h2>
        {alCerrar && (
          <button
            type="button"
            aria-label={BOTON_CERRAR}
            onClick={alCerrar}
            className={`inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg transition-colors hover:bg-[var(--color-muted)] motion-reduce:transition-none ${FOCUS_RING}`}
            style={{ color: 'var(--color-muted-foreground)' }}
          >
            <IconoCerrar />
          </button>
        )}
      </header>

      {avisoPendiente ? (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold" style={{ color: 'var(--color-foreground)' }}>
            {AVISO_PRIMER_USO.titulo}
          </h3>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
            {AVISO_PRIMER_USO.texto}
          </p>
          <button type="button" ref={alMontarEntendido} onClick={alEntender} className={`${BOTON_PRIMARIO} w-full sm:w-auto`}>
            {AVISO_PRIMER_USO.boton}
          </button>
        </div>
      ) : (
        <>
          {/* Always in the page, so what appears in it is announced; it only has text when there is something to say. */}
          <div role="status" aria-live="polite" aria-atomic="true" className="space-y-2 empty:sr-only">
            {enviando && (
              <p className="text-sm" style={{ color: 'var(--color-muted-foreground)' }}>
                {TEXTO_ENVIANDO}
              </p>
            )}
            {estado.fase === 'respondida' && (
              <p
                className="whitespace-pre-line break-words rounded-xl bg-[var(--color-muted)] p-3 text-sm leading-relaxed"
                style={{ color: 'var(--color-foreground)' }}
              >
                {estado.texto}
              </p>
            )}
            {estado.fase === 'error' && (
              <p className="break-words text-sm leading-relaxed" style={{ color: 'var(--color-foreground)' }}>
                {textoDeError(estado.error)}
              </p>
            )}
          </div>

          {sinRespuestaDelModelo(estado) && rapidas.length > 0 && (
            <section aria-labelledby={rapidasId} className="space-y-2 rounded-xl border border-[var(--color-border)] p-3">
              <h3 id={rapidasId} className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--color-muted-foreground)' }}>
                {TITULO_RESPUESTAS_RAPIDAS}
              </h3>
              <ul className="space-y-2">
                {rapidas.map((r) => (
                  <li key={r.id}>
                    <p className="text-sm font-medium" style={{ color: 'var(--color-foreground)' }}>
                      {r.pregunta}
                    </p>
                    <p className="break-words text-sm leading-relaxed" style={{ color: 'var(--color-muted-foreground)' }}>
                      {r.texto}
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <form onSubmit={alEnviarForm} className="space-y-2">
            <label htmlFor={campoId} className="sr-only">
              {ETIQUETA_PREGUNTA}
            </label>
            {/* 16 px (text-base): below that, iOS Safari zooms the page when the field takes focus. */}
            <textarea
              id={campoId}
              ref={alMontarCampo}
              value={texto}
              rows={2}
              enterKeyHint="send"
              placeholder={PLACEHOLDER_PREGUNTA}
              aria-describedby={`${contadorId}${mensajeValidacion ? ` ${validacionId}` : ''}`}
              aria-invalid={sobreElLimite || mensajeValidacion !== null}
              onChange={(e) => alCambiarTexto(e.target.value)}
              onKeyDown={alTeclear}
              className={`block w-full resize-none rounded-lg border bg-[var(--color-background)] p-2 text-base ${FOCUS_RING}`}
              // Inline: the global `* { border-color }` rule of index.css is unlayered and beats every border-color utility.
              style={{ color: 'var(--color-foreground)', borderColor: 'var(--color-border-strong)' }}
            />
            {mensajeValidacion && (
              <p id={validacionId} role="alert" className="text-sm" style={{ color: COLOR_ERROR }}>
                {mensajeValidacion}
              </p>
            )}
            <div className="flex items-center justify-between gap-3">
              <span
                id={contadorId}
                className="text-xs tabular-nums"
                style={{ color: sobreElLimite ? COLOR_ERROR : 'var(--color-muted-foreground)' }}
              >
                {textoContador(texto)}
              </span>
              <button type="submit" disabled={enviando || bloqueado} className={BOTON_PRIMARIO}>
                {bloqueado ? textoEsperaBoton(esperaSegundos) : BOTON_ENVIAR}
              </button>
            </div>
          </form>
        </>
      )}
    </div>
  )
}
