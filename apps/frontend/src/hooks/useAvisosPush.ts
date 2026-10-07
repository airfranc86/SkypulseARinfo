import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api } from '@/lib/api'
import type { ConfigAlertas } from '@/lib/alertas/config'
import type { EstadoPrueba } from '@/lib/alertas/copy'
import { detectarDisponibilidad, type Disponibilidad } from '@/lib/alertas/plataforma'
import {
  ESTADO_INICIAL,
  claveVapidABytes,
  cuerpoDeAlta,
  idADarDeBaja,
  motivoDeError,
  normalizarPermiso,
  puedeActivar as decidirActivacion,
  transicion,
  type ErrorAvisos,
  type EstadoGuardado,
  type EstadoAvisos,
  type EventoAvisos,
  type PermisoNavegador,
  type ResultadoActivar,
} from '@/lib/alertas/suscripcion'
import {
  borrarEstadoLocal,
  entornoDelNavegador,
  estadoGuardadoDeRespuesta,
  guardarEstadoLocal,
  leerEstadoLocal,
  permisoDelNavegador,
  suscripcionActual,
} from '@/hooks/useRenovarAvisos'

/**
 * Los avisos push de la pantalla `/alertas` (FRA-357, T7b): activar, probar y desactivar, y el estado de
 * cada paso. La lógica pura (estados, errores, cuándo se puede activar) vive en `lib/alertas`; acá solo se
 * llama al navegador y a la API.
 *
 * El permiso del navegador se pide en un único lugar: `activar`, que corre desde el clic en "Activar avisos".
 * Nada lo pide al entrar a la página ni desde un efecto.
 */

const RUTA_SERVICE_WORKER = '/sw.js'
/** Si el navegador no termina de registrar o suscribir en este tiempo, se corta con un error en vez de quedar "Activando…". */
const TOPE_NAVEGADOR_MS = 30_000
const UN_SEGUNDO_MS = 1000

const PRUEBA_LIBRE: EstadoPrueba = Object.freeze({ tipo: 'libre' })

type Despachar = (evento: EventoAvisos) => void

export interface AvisosPush {
  estado: EstadoAvisos
  disponibilidad: Disponibilidad
  /** Slug de la ciudad elegida (o, sin elegir, la guardada o la sugerida por la ubicación). */
  zonaElegida: string | null
  setZona: (slug: string | null) => void
  consentimiento: boolean
  setConsentimiento: (valor: boolean) => void
  activar: () => Promise<void>
  probar: () => Promise<void>
  desactivar: () => Promise<void>
  /** Si "Activar avisos" está habilitado y, si no, por qué. */
  puedeActivar: ResultadoActivar
  /** Hay un paso en curso (el permiso, el alta o la baja): los botones esperan. */
  ocupado: boolean
  prueba: EstadoPrueba
  /** Segundos que faltan para poder probar de nuevo; null si se puede probar ya. */
  esperaProbar: number | null
}

// ── Navegador ────────────────────────────────────────────────────────────────

function conTope<T>(promesa: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolver, rechazar) => {
    const reloj = setTimeout(() => rechazar(new Error('tiempo_agotado')), ms)
    promesa.then(resolver, rechazar).finally(() => clearTimeout(reloj))
  })
}

function mismaClave(suscripcion: PushSubscription, clave: Uint8Array): boolean {
  const actual = suscripcion.options?.applicationServerKey
  if (!actual) return false
  const bytes = new Uint8Array(actual)
  return bytes.length === clave.length && bytes.every((byte, i) => byte === clave[i])
}

/** Registra el service worker (alcance `/`), espera a que esté activo y suscribe con nuestra clave VAPID. */
async function suscribirEnNavegador(clave: Uint8Array): Promise<PushSubscription> {
  await navigator.serviceWorker.register(RUTA_SERVICE_WORKER, { scope: '/' })
  const registro = await navigator.serviceWorker.ready
  const existente = await registro.pushManager.getSubscription()
  // Una suscripción hecha con otra clave no se puede reusar: `subscribe` falla hasta darla de baja.
  if (existente !== null && !mismaClave(existente, clave)) await existente.unsubscribe()
  return registro.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: new Uint8Array(clave) })
}

async function desuscribir(suscripcion: PushSubscription): Promise<void> {
  try {
    await suscripcion.unsubscribe()
  } catch {
    // Sin la suscripción local ya no llegan avisos; si no se pudo borrar no hay nada más que hacer.
  }
}

async function desuscribirLocal(): Promise<void> {
  try {
    const suscripcion = await suscripcionActual()
    if (suscripcion !== null) await desuscribir(suscripcion)
  } catch {
    // Ídem.
  }
}

/** Suscribe en el navegador y da de alta en el servidor. No lanza: devuelve el evento que corresponde. */
async function darDeAlta(clave: Uint8Array, zona: string): Promise<EventoAvisos> {
  let suscripcion: PushSubscription | null = null
  try {
    suscripcion = await conTope(suscribirEnNavegador(clave), TOPE_NAVEGADOR_MS)
    const respuesta = await api.alertasSuscribir(cuerpoDeAlta(suscripcion.toJSON(), zona))
    const guardado = estadoGuardadoDeRespuesta(respuesta, Date.now())
    if (guardado === null) throw new Error('respuesta_invalida')
    guardarEstadoLocal(guardado)
    return { tipo: 'suscripcion-ok', id: guardado.id, zona: guardado.zona }
  } catch (error) {
    // Si el servidor no la registró, la suscripción local quedaría huérfana: se da de baja.
    if (suscripcion !== null) await desuscribir(suscripcion)
    return { tipo: 'suscripcion-fallo', error: motivoDeError(error) }
  }
}

/** La baja de la persona: en el servidor (si falla igual se sigue), en este navegador y en el almacenamiento local. */
async function darDeBaja(id: string | null): Promise<void> {
  try {
    if (id !== null) await api.alertasBaja({ id })
  } catch {
    // Un fallo del servidor no impide dejar de recibir avisos en este navegador: se sigue con lo local.
  }
  await desuscribirLocal()
  borrarEstadoLocal()
}

function pedirBajaEnSegundoPlano(id: string): void {
  api.alertasBaja({ id }).catch(() => undefined)
}

function claveParaSuscribir(clave: string | null): Uint8Array | null {
  if (clave === null) return null
  try {
    return claveVapidABytes(clave)
  } catch {
    return null
  }
}

// ── Estado ───────────────────────────────────────────────────────────────────

/** Con algo guardado y el permiso concedido arranca "activo" (se confirma enseguida); con el permiso bloqueado, "denegado". */
function estadoInicial(guardado: EstadoGuardado | null, permiso: PermisoNavegador): EstadoAvisos {
  if (guardado !== null && permiso === 'granted') return { tipo: 'activo', id: guardado.id, zona: guardado.zona }
  return transicion(ESTADO_INICIAL, { tipo: 'cambio-de-permiso', permiso })
}

/** El permiso cambió desde los ajustes del navegador: si dejó inservible una suscripción activa, se da de baja. */
function aplicarCambioDePermiso(permiso: PermisoNavegador, estadoActual: EstadoAvisos, dispatch: Despachar): void {
  const evento: EventoAvisos = { tipo: 'cambio-de-permiso', permiso }
  const id = idADarDeBaja(estadoActual, evento)
  dispatch(evento)
  if (id === null) return
  borrarEstadoLocal()
  pedirBajaEnSegundoPlano(id)
  void desuscribirLocal()
}

/**
 * Lo guardado ya no sirve si el permiso se retiró o el navegador perdió la suscripción: se borra y, si el
 * servidor la conocía, se da de baja. Si no se puede saber (error al consultar), no se toca nada.
 */
async function verificarGuardado(guardado: EstadoGuardado, dispatch: Despachar, cancelado: () => boolean): Promise<void> {
  let suscripcion: PushSubscription | null = null
  try {
    if (permisoDelNavegador() === 'granted') suscripcion = await suscripcionActual()
  } catch {
    return
  }
  if (cancelado() || suscripcion !== null) return
  borrarEstadoLocal()
  pedirBajaEnSegundoPlano(guardado.id)
  dispatch({ tipo: 'baja-ok' })
}

function pruebaDeError(error: ErrorAvisos): EstadoPrueba {
  return error.motivo === 'espera' ? { tipo: 'espera', segundos: error.segundos } : { tipo: 'error', error }
}

function descontarSegundo(prueba: EstadoPrueba): EstadoPrueba {
  if (prueba.tipo !== 'espera') return prueba
  return prueba.segundos <= 1 ? PRUEBA_LIBRE : { tipo: 'espera', segundos: prueba.segundos - 1 }
}

// ── Hooks internos ───────────────────────────────────────────────────────────

/** Al entrar: lo guardado tiene que seguir siendo cierto en el navegador. */
function useVerificarGuardado(guardado: EstadoGuardado | null, dispatch: Despachar): void {
  useEffect(() => {
    if (guardado === null) return
    let cancelado = false
    void verificarGuardado(guardado, dispatch, () => cancelado)
    return () => {
      cancelado = true
    }
  }, [guardado, dispatch])
}

/** El permiso puede cambiar desde los ajustes del navegador mientras la página está abierta. */
function useObservarPermiso(
  estado: EstadoAvisos,
  dispatch: Despachar,
  setPermiso: (permiso: PermisoNavegador) => void,
): void {
  const estadoRef = useRef(estado)
  useEffect(() => {
    estadoRef.current = estado
  }, [estado])

  useEffect(() => {
    if (!navigator.permissions?.query) return
    let cancelado = false
    let observado: PermissionStatus | null = null
    const alCambiar = () => {
      if (observado === null) return
      const nuevo = normalizarPermiso(observado.state)
      setPermiso(nuevo)
      aplicarCambioDePermiso(nuevo, estadoRef.current, dispatch)
    }
    navigator.permissions
      .query({ name: 'notifications' })
      .then((resultado) => {
        if (cancelado) return
        observado = resultado
        resultado.addEventListener('change', alCambiar)
      })
      .catch(() => undefined)
    return () => {
      cancelado = true
      observado?.removeEventListener('change', alCambiar)
    }
  }, [dispatch, setPermiso])
}

/** El aviso de prueba: su estado, la cuenta regresiva de la espera y la acción de mandarlo. */
function usePrueba(estado: EstadoAvisos, dispatch: Despachar) {
  const [prueba, setPrueba] = useState<EstadoPrueba>(PRUEBA_LIBRE)
  const enEspera = prueba.tipo === 'espera'

  // Cuenta regresiva de "Probar aviso (esperá N s)".
  useEffect(() => {
    if (!enEspera) return
    const reloj = setInterval(() => setPrueba(descontarSegundo), UN_SEGUNDO_MS)
    return () => clearInterval(reloj)
  }, [enEspera])

  const reiniciar = useCallback(() => setPrueba(PRUEBA_LIBRE), [])

  const probar = useCallback(async () => {
    if (estado.tipo !== 'activo' || prueba.tipo === 'enviando' || prueba.tipo === 'espera') return
    setPrueba({ tipo: 'enviando' })
    try {
      await api.alertasPrueba({ id: estado.id })
      setPrueba({ tipo: 'enviada' })
    } catch (error) {
      const motivo = motivoDeError(error)
      setPrueba(pruebaDeError(motivo))
      if (motivo.motivo !== 'vencida') return
      // El servidor ya no la tiene: se limpia todo y la persona vuelve a activar.
      borrarEstadoLocal()
      void desuscribirLocal()
      dispatch({ tipo: 'baja-ok' })
    }
  }, [dispatch, estado, prueba.tipo])

  return { prueba, esperaProbar: enEspera ? prueba.segundos : null, probar, reiniciar }
}

// ── Hook ─────────────────────────────────────────────────────────────────────

/**
 * @param config la clave VAPID del despliegue.
 * @param zonaSugerida slug de la ciudad más cercana a la ubicación, para preseleccionarla.
 */
export function useAvisosPush(config: ConfigAlertas, zonaSugerida: string | null = null): AvisosPush {
  const [disponibilidad] = useState<Disponibilidad>(() => detectarDisponibilidad(entornoDelNavegador()))
  const [guardadoInicial] = useState<EstadoGuardado | null>(leerEstadoLocal)
  const [permiso, setPermiso] = useState<PermisoNavegador>(permisoDelNavegador)
  const [estado, dispatch] = useReducer(transicion, undefined, () => estadoInicial(guardadoInicial, permiso))
  const [zonaManual, setZona] = useState<string | null>(null)
  const [consentimiento, setConsentimiento] = useState(false)
  const [desactivando, setDesactivando] = useState(false)
  const activando = useRef(false)
  const desactivandoRef = useRef(false)
  const { prueba, esperaProbar, probar, reiniciar } = usePrueba(estado, dispatch)

  useVerificarGuardado(guardadoInicial, dispatch)
  useObservarPermiso(estado, dispatch, setPermiso)

  const zonaElegida = zonaManual ?? guardadoInicial?.zona ?? zonaSugerida
  const puedeActivar = decidirActivacion({ consentimiento, zona: zonaElegida, disponibilidad, permiso })
  const ocupado = desactivando || estado.tipo === 'pidiendo-permiso' || estado.tipo === 'suscribiendo'

  const activar = useCallback(async () => {
    if (activando.current) return
    const zona = zonaElegida
    const decision = decidirActivacion({ consentimiento, zona, disponibilidad, permiso: permisoDelNavegador() })
    if (!decision.habilitado || zona === null) return
    activando.current = true
    reiniciar()
    dispatch({ tipo: 'tap-activar' })
    try {
      const clave = claveParaSuscribir(config.claveVapid)
      if (clave === null) {
        dispatch({ tipo: 'suscripcion-fallo', error: { motivo: 'no-disponible' } })
        return
      }
      const concedido = normalizarPermiso(await Notification.requestPermission())
      setPermiso(concedido)
      dispatch({ tipo: 'permiso-resuelto', permiso: concedido })
      if (concedido === 'granted') dispatch(await darDeAlta(clave, zona))
    } catch (error) {
      dispatch({ tipo: 'suscripcion-fallo', error: motivoDeError(error) })
    } finally {
      activando.current = false
    }
  }, [config.claveVapid, consentimiento, disponibilidad, reiniciar, zonaElegida])

  const desactivar = useCallback(async () => {
    if (desactivandoRef.current) return
    desactivandoRef.current = true
    setDesactivando(true)
    try {
      await darDeBaja(estado.tipo === 'activo' ? estado.id : (leerEstadoLocal()?.id ?? null))
      reiniciar()
      setConsentimiento(false)
      dispatch({ tipo: 'baja-ok' })
    } finally {
      setDesactivando(false)
      desactivandoRef.current = false
    }
  }, [estado, reiniciar])

  return {
    estado,
    disponibilidad,
    zonaElegida,
    setZona,
    consentimiento,
    setConsentimiento,
    activar,
    probar,
    desactivar,
    puedeActivar,
    ocupado,
    prueba,
    esperaProbar,
  }
}
