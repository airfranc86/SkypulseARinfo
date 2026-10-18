import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { BASE_URL } from '@/lib/api'
import { bloqueoDelError, proximoTicMs, segundosHasta } from '@/lib/asistente/bloqueo'
import { preguntar } from '@/lib/asistente/cliente'
import type { HumorMora } from '@/lib/asistente/humor'
import { estadoInicialDelPanel, humorDelPanel, reducirPanel, type EstadoPanel } from '@/lib/asistente/panel'
import { prepararPregunta } from '@/lib/asistente/preparar'

/** What `enviar` did: `enviada` is the only one that left the browser; the others say why nothing was sent. */
export type ResultadoEnvio = 'enviada' | 'ocupada' | 'bloqueada' | 'vacia' | 'larga' | 'sin-ubicacion'

export interface UsoAsistente {
  estado: EstadoPanel
  /** The mood the panel gives Mora, or `null` (then the bubble keeps the one the weather gives). */
  humor: HumorMora | null
  /** Seconds the person still has to wait before asking again (a limit the server asked for); 0 when nothing blocks. */
  esperaSegundos: number
  enviar: (texto: string) => ResultadoEnvio
}

/**
 * The question flow of Mora's panel: checks and sends the question (`prepararPregunta`, `preguntar`), keeps the state of
 * the panel (`reducirPanel`) and the wait the server asked for. One question in flight at a time. Closing the panel does
 * NOT cancel the question (the answer is waiting when it opens again); leaving the page does (the cleanup aborts it). All
 * the rules are in pure modules covered by tests: this hook is only the wiring.
 */
export function useAsistente(lat: number | null, lon: number | null, ruta: string | null): UsoAsistente {
  const [estado, despachar] = useReducer(reducirPanel, undefined, estadoInicialDelPanel)
  const [bloqueo, setBloqueo] = useState<number | null>(null)
  const [reloj, setReloj] = useState(0)
  // The question in flight, in a box: the cleanup reads the box itself, not a value that may have changed.
  const enVuelo = useRef<{ actual: AbortController | null }>({ actual: null })

  useEffect(() => {
    const caja = enVuelo.current
    return () => caja.actual?.abort()
  }, [])

  useEffect(() => {
    if (bloqueo === null) return undefined
    // The countdown redraws as often as its text can change (`proximoTicMs`): every 30 s for a long wait, every second at the end.
    let tic: ReturnType<typeof setTimeout> | undefined
    const siguiente = () => {
      const ahora = Date.now()
      setReloj(ahora)
      const espera = proximoTicMs(bloqueo - ahora)
      if (espera === 0) setBloqueo(null)
      else tic = setTimeout(siguiente, espera)
    }
    tic = setTimeout(siguiente, proximoTicMs(bloqueo - Date.now()))
    return () => clearTimeout(tic)
  }, [bloqueo])

  const enviar = useCallback(
    (texto: string): ResultadoEnvio => {
      const caja = enVuelo.current
      if (caja.actual !== null) return 'ocupada'
      if (segundosHasta(bloqueo, Date.now()) > 0) return 'bloqueada'
      const preparada = prepararPregunta(texto, lat, lon, ruta)
      if (!preparada.ok) return preparada.motivo

      const controlador = new AbortController()
      caja.actual = controlador
      despachar({ tipo: 'enviar', pregunta: preparada.pregunta.pregunta })
      void preguntar(preparada.pregunta, {
        fetch: (url, init) => fetch(url, init),
        baseUrl: BASE_URL,
        signal: controlador.signal,
      }).then((resultado) => {
        if (caja.actual !== controlador) return // the panel was cleared: this answer is stale
        caja.actual = null
        despachar({ tipo: 'resultado', resultado })
        if (resultado.tipo !== 'respuesta' && resultado.tipo !== 'cancelada') {
          const ahora = Date.now()
          setReloj(ahora)
          setBloqueo(bloqueoDelError(resultado, ahora))
        }
      })
      return 'enviada'
    },
    [bloqueo, lat, lon, ruta],
  )

  return { estado, humor: humorDelPanel(estado), esperaSegundos: segundosHasta(bloqueo, reloj), enviar }
}
