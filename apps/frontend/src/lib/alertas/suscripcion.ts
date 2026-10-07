/**
 * Lógica pura de la suscripción a las alertas push (FRA-357, T7a): estados del permiso, cuándo se puede
 * activar, cuándo renovar, el cuerpo del alta, la clave VAPID, el estado guardado y los motivos de error
 * de la API. Sin React, sin `window` y sin `import.meta.env`: todo entra por parámetro para que
 * `node --test` pueda cubrir cada regla. Las llamadas al navegador y a la API las hace T7b.
 */
import type { Disponibilidad } from './plataforma.ts'
import { zonaPorSlug } from './zonaSugerida.ts'

// ── Permiso ──────────────────────────────────────────────────────────────────

/** Los valores de `Notification.permission`. */
export type PermisoNavegador = 'default' | 'granted' | 'denied'

/**
 * `permissionStatus.state` dice "prompt" donde `Notification.permission` dice "default": cualquier cosa
 * que no sea granted o denied se toma como "todavía sin decidir".
 */
export function normalizarPermiso(valor: unknown): PermisoNavegador {
  return valor === 'granted' || valor === 'denied' ? valor : 'default'
}

// ── Errores de la API ────────────────────────────────────────────────────────

export type ErrorAvisos =
  /** 429: hay que esperar `segundos` antes de reintentar. */
  | { motivo: 'espera'; segundos: number }
  | {
      motivo:
        | 'vencida' // 404/410: la suscripción ya no existe en el servidor, hay que volver a activar
        | 'servicio-push' // 502: el servicio push del navegador no aceptó el aviso
        | 'no-disponible' // 503: el servidor de alertas no está disponible o llegó al tope
        | 'datos-invalidos' // 422: el servidor rechazó lo enviado
        | 'desconocido' // 504, red caída o cualquier otro
    }

const ERROR_DESCONOCIDO: ErrorAvisos = Object.freeze({ motivo: 'desconocido' })
const ESPERA_POR_DEFECTO_S = 60

function segundosDeEspera(retryAfter: unknown): number {
  return typeof retryAfter === 'number' && Number.isFinite(retryAfter) && retryAfter > 0
    ? Math.ceil(retryAfter)
    : ESPERA_POR_DEFECTO_S
}

/**
 * El motivo que muestra la pantalla para un fallo de alta, baja o prueba. Recibe lo que haya en el `catch`:
 * un `ApiError` (le alcanza `status` y `retryAfter`, no se importa la clase) o cualquier otra cosa.
 */
export function motivoDeError(error: unknown): ErrorAvisos {
  const datos = typeof error === 'object' && error !== null ? (error as Record<string, unknown>) : {}
  switch (datos.status) {
    case 404:
    case 410:
      return { motivo: 'vencida' }
    case 429:
      return { motivo: 'espera', segundos: segundosDeEspera(datos.retryAfter) }
    case 502:
      return { motivo: 'servicio-push' }
    case 503:
      return { motivo: 'no-disponible' }
    case 422:
      return { motivo: 'datos-invalidos' }
    default:
      return ERROR_DESCONOCIDO
  }
}

// ── Identificador de la suscripción ──────────────────────────────────────────

const PATRON_ID = /^[A-Za-z0-9_-]{22}$/

/** El `id` que devuelve el alta: 22 caracteres base64url (lo mismo que exige el backend en la baja). */
export function esIdSuscripcion(valor: unknown): valor is string {
  return typeof valor === 'string' && PATRON_ID.test(valor)
}

// ── Máquina de estados ───────────────────────────────────────────────────────

export type EstadoAvisos =
  | { tipo: 'inactivo' }
  | { tipo: 'pidiendo-permiso' } // se tocó "Activar" y la ventana del navegador está abierta
  | { tipo: 'sin-respuesta' } // la ventana se cerró sin respuesta (Chrome lo hace solo): se puede reintentar
  | { tipo: 'denegado' }
  | { tipo: 'suscribiendo' } // permiso concedido: se registra en el navegador y en el servidor
  | { tipo: 'activo'; id: string; zona: string }
  | { tipo: 'error'; error: ErrorAvisos }

export type EventoAvisos =
  | { tipo: 'tap-activar' }
  | { tipo: 'permiso-resuelto'; permiso: PermisoNavegador }
  | { tipo: 'suscripcion-ok'; id: string; zona: string }
  | { tipo: 'suscripcion-fallo'; error: ErrorAvisos }
  | { tipo: 'baja-ok' }
  /** Aviso posterior de `permissionStatus.onchange`: el permiso cambió desde los ajustes del navegador. */
  | { tipo: 'cambio-de-permiso'; permiso: PermisoNavegador }

export const ESTADO_INICIAL: EstadoAvisos = Object.freeze({ tipo: 'inactivo' })
const PIDIENDO: EstadoAvisos = Object.freeze({ tipo: 'pidiendo-permiso' })
const SIN_RESPUESTA: EstadoAvisos = Object.freeze({ tipo: 'sin-respuesta' })
const DENEGADO: EstadoAvisos = Object.freeze({ tipo: 'denegado' })
const SUSCRIBIENDO: EstadoAvisos = Object.freeze({ tipo: 'suscribiendo' })
const ERROR_RESPUESTA_INVALIDA: EstadoAvisos = Object.freeze({ tipo: 'error', error: ERROR_DESCONOCIDO })

/** Un `suscripcion-ok` solo da un "activo" si el id y la zona son válidos; si no, es un error. */
function activoSiEsValido(evento: Extract<EventoAvisos, { tipo: 'suscripcion-ok' }>): EstadoAvisos | null {
  if (!esIdSuscripcion(evento.id) || typeof evento.zona !== 'string' || zonaPorSlug(evento.zona) === null) return null
  return { tipo: 'activo', id: evento.id, zona: evento.zona }
}

function desdeInactivo(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  if (evento.tipo === 'tap-activar') return PIDIENDO
  if (evento.tipo === 'cambio-de-permiso' && normalizarPermiso(evento.permiso) === 'denied') return DENEGADO
  return estado
}

function desdePidiendo(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  // `cambio-de-permiso` no decide acá: manda lo que responda la ventana (`permiso-resuelto`).
  if (evento.tipo === 'suscripcion-fallo') return { tipo: 'error', error: evento.error ?? ERROR_DESCONOCIDO }
  if (evento.tipo !== 'permiso-resuelto') return estado
  const permiso = normalizarPermiso(evento.permiso)
  if (permiso === 'granted') return SUSCRIBIENDO
  return permiso === 'denied' ? DENEGADO : SIN_RESPUESTA
}

function desdeSinRespuesta(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  if (evento.tipo === 'tap-activar') return PIDIENDO
  if (evento.tipo !== 'cambio-de-permiso') return estado
  const permiso = normalizarPermiso(evento.permiso)
  if (permiso === 'denied') return DENEGADO
  return permiso === 'granted' ? ESTADO_INICIAL : estado
}

function desdeDenegado(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  if (evento.tipo !== 'cambio-de-permiso') return estado
  // Concedido, o vuelto a "preguntar" desde los ajustes: la persona puede activar de nuevo.
  return normalizarPermiso(evento.permiso) === 'denied' ? estado : ESTADO_INICIAL
}

function desdeSuscribiendo(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  if (evento.tipo === 'suscripcion-ok') return activoSiEsValido(evento) ?? ERROR_RESPUESTA_INVALIDA
  if (evento.tipo === 'suscripcion-fallo') return { tipo: 'error', error: evento.error ?? ERROR_DESCONOCIDO }
  if (evento.tipo === 'cambio-de-permiso' && normalizarPermiso(evento.permiso) === 'denied') return DENEGADO
  return estado
}

function desdeActivo(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  if (evento.tipo === 'baja-ok') return ESTADO_INICIAL
  // Renovar o cambiar de ciudad repite el alta: devuelve el mismo id con la zona nueva.
  if (evento.tipo === 'suscripcion-ok') return activoSiEsValido(evento) ?? estado
  if (evento.tipo !== 'cambio-de-permiso') return estado
  // Permiso retirado después de activar: ya no se pueden entregar avisos (ver `idADarDeBaja`).
  const permiso = normalizarPermiso(evento.permiso)
  if (permiso === 'granted') return estado
  return permiso === 'denied' ? DENEGADO : ESTADO_INICIAL
}

function desdeError(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  if (evento.tipo === 'tap-activar') return PIDIENDO
  if (evento.tipo === 'baja-ok') return ESTADO_INICIAL
  if (evento.tipo === 'cambio-de-permiso' && normalizarPermiso(evento.permiso) === 'denied') return DENEGADO
  return estado
}

/**
 * El estado siguiente. Pura: no modifica lo que recibe. Una combinación que no corresponde (o un evento
 * desconocido) devuelve el mismo estado, la misma referencia; nunca lanza.
 */
export function transicion(estado: EstadoAvisos, evento: EventoAvisos): EstadoAvisos {
  if (typeof evento?.tipo !== 'string') return estado
  switch (estado?.tipo) {
    case 'inactivo':
      return desdeInactivo(estado, evento)
    case 'pidiendo-permiso':
      return desdePidiendo(estado, evento)
    case 'sin-respuesta':
      return desdeSinRespuesta(estado, evento)
    case 'denegado':
      return desdeDenegado(estado, evento)
    case 'suscribiendo':
      return desdeSuscribiendo(estado, evento)
    case 'activo':
      return desdeActivo(estado, evento)
    case 'error':
      return desdeError(estado, evento)
    default:
      return estado
  }
}

/**
 * El `id` a dar de baja en el servidor cuando este evento deja inservible una suscripción activa (el
 * permiso se retiró desde los ajustes del navegador); null si no hay nada que dar de baja. Va aparte de
 * `transicion` para que siga devolviendo solo el estado: la pantalla llama las dos con el mismo evento.
 */
export function idADarDeBaja(estado: EstadoAvisos, evento: EventoAvisos): string | null {
  if (estado?.tipo !== 'activo' || evento?.tipo !== 'cambio-de-permiso') return null
  return normalizarPermiso(evento.permiso) === 'granted' ? null : estado.id
}

// ── Cuándo se puede activar ──────────────────────────────────────────────────

export type MotivoNoActivable = 'sin-soporte' | 'permiso-denegado' | 'sin-consentimiento' | 'sin-zona'

export interface EntradaActivar {
  consentimiento: boolean
  /** Slug de la ciudad elegida. */
  zona: string | null
  disponibilidad: Disponibilidad
  permiso: PermisoNavegador
}

export type ResultadoActivar = { habilitado: true; motivo?: undefined } | { habilitado: false; motivo: MotivoNoActivable }

/**
 * Si el botón "Activar avisos" está habilitado y, si no, por qué (el primer motivo de esta lista: plataforma,
 * permiso, consentimiento, ciudad). El consentimiento es obligatorio: sin un `true` el botón queda deshabilitado
 * aunque todo lo demás esté bien. Cualquier plataforma que no sea "activar" (instalar, abrir en el navegador,
 * sin soporte) cuenta como "sin-soporte" para este botón.
 */
export function puedeActivar(entrada: EntradaActivar): ResultadoActivar {
  if (entrada.disponibilidad?.tipo !== 'activar') return { habilitado: false, motivo: 'sin-soporte' }
  if (entrada.permiso === 'denied') return { habilitado: false, motivo: 'permiso-denegado' }
  if (entrada.consentimiento !== true) return { habilitado: false, motivo: 'sin-consentimiento' }
  if (typeof entrada.zona !== 'string' || zonaPorSlug(entrada.zona) === null) {
    return { habilitado: false, motivo: 'sin-zona' }
  }
  return { habilitado: true }
}

// ── Renovación ───────────────────────────────────────────────────────────────

/** Cada cuánto se repite el alta para renovar el vencimiento (el servidor guarda 180 días). */
export const UMBRAL_RENOVACION_MS = 7 * 24 * 60 * 60 * 1000

/**
 * Toca renovar a los 7 días o más de la última renovación. Una fecha que no es un número finito se renueva
 * (no se sabe cuándo fue); una del futuro (reloj corrido) no.
 */
export function debeRenovar(ultimaRenovacionMs: number, ahoraMs: number): boolean {
  if (!Number.isFinite(ultimaRenovacionMs) || !Number.isFinite(ahoraMs)) return true
  return ahoraMs - ultimaRenovacionMs >= UMBRAL_RENOVACION_MS
}

// ── Cuerpo del alta ──────────────────────────────────────────────────────────

/** La suscripción no trae endpoint o claves (mensaje fijo: no repite nada de lo recibido). */
export class SuscripcionIncompleta extends Error {
  constructor() {
    super('suscripcion_incompleta')
    this.name = 'SuscripcionIncompleta'
  }
}

/** La zona no es un slug de `ZONAS_ALERTAS` (mensaje fijo). */
export class ZonaDesconocida extends Error {
  constructor() {
    super('zona_desconocida')
    this.name = 'ZonaDesconocida'
  }
}

/** Lo que espera `POST /api/alertas/suscripcion`. */
export interface CuerpoDeAlta {
  endpoint: string
  keys: { p256dh: string; auth: string }
  zona: string
}

function esTextoNoVacio(valor: unknown): valor is string {
  return typeof valor === 'string' && valor.length > 0
}

/**
 * El cuerpo del alta a partir de `PushSubscription.toJSON()` y el slug de la ciudad. Solo se copian
 * endpoint, p256dh y auth (se ignora `expirationTime` y cualquier otro campo). Lanza `SuscripcionIncompleta`
 * o `ZonaDesconocida`; el servidor valida otra vez el host del endpoint y las claves.
 */
export function cuerpoDeAlta(subscriptionJson: unknown, zonaSlug: string): CuerpoDeAlta {
  if (typeof subscriptionJson !== 'object' || subscriptionJson === null) throw new SuscripcionIncompleta()
  const { endpoint, keys } = subscriptionJson as Record<string, unknown>
  if (!esTextoNoVacio(endpoint) || typeof keys !== 'object' || keys === null) throw new SuscripcionIncompleta()
  const { p256dh, auth } = keys as Record<string, unknown>
  if (!esTextoNoVacio(p256dh) || !esTextoNoVacio(auth)) throw new SuscripcionIncompleta()
  if (typeof zonaSlug !== 'string' || zonaPorSlug(zonaSlug) === null) throw new ZonaDesconocida()
  return { endpoint, keys: { p256dh, auth }, zona: zonaSlug }
}

// ── Clave VAPID ──────────────────────────────────────────────────────────────

/** La clave pública VAPID no es un punto P-256 sin comprimir en base64url (mensaje fijo: no la repite). */
export class ClaveVapidInvalida extends Error {
  constructor() {
    super('clave_vapid_invalida')
    this.name = 'ClaveVapidInvalida'
  }
}

const LARGO_CLAVE_VAPID = 65
const PRIMER_BYTE_SIN_COMPRIMIR = 0x04
const PATRON_BASE64URL = /^[A-Za-z0-9_-]+={0,2}$/

/**
 * La clave pública VAPID (base64url, con o sin relleno) como bytes para `applicationServerKey`. Tiene que ser
 * un punto P-256 sin comprimir: exactamente 65 bytes y el primero 0x04. Lanza `ClaveVapidInvalida`.
 */
export function claveVapidABytes(base64url: string): Uint8Array {
  if (typeof base64url !== 'string' || !PATRON_BASE64URL.test(base64url)) throw new ClaveVapidInvalida()
  const sinRelleno = base64url.replace(/=+$/, '')
  if (sinRelleno.length % 4 === 1) throw new ClaveVapidInvalida()
  const relleno = '='.repeat((4 - (sinRelleno.length % 4)) % 4)
  let binario: string
  try {
    binario = atob(sinRelleno.replace(/-/g, '+').replace(/_/g, '/') + relleno)
  } catch {
    throw new ClaveVapidInvalida()
  }
  if (binario.length !== LARGO_CLAVE_VAPID || binario.charCodeAt(0) !== PRIMER_BYTE_SIN_COMPRIMIR) {
    throw new ClaveVapidInvalida()
  }
  const bytes = new Uint8Array(LARGO_CLAVE_VAPID)
  for (let i = 0; i < LARGO_CLAVE_VAPID; i++) bytes[i] = binario.charCodeAt(i)
  return bytes
}

// ── Estado guardado ──────────────────────────────────────────────────────────

/** Clave del almacenamiento local donde se guarda la suscripción activa. */
export const claveEstadoGuardado = 'skypulse:alertas'

export interface EstadoGuardado {
  id: string
  zona: string
  /** Milisegundos desde la época de la última vez que se repitió el alta. */
  ultimaRenovacion: number
}

/**
 * Lee lo guardado en `claveEstadoGuardado`. Devuelve null ante nada, JSON roto o datos que no cumplen: id de
 * 22 caracteres base64url, zona conocida y renovación numérica finita. Nunca lanza.
 */
export function leerEstadoGuardado(raw: string | null): EstadoGuardado | null {
  if (typeof raw !== 'string' || raw === '') return null
  let datos: unknown
  try {
    datos = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof datos !== 'object' || datos === null || Array.isArray(datos)) return null
  const { id, zona, ultimaRenovacion } = datos as Record<string, unknown>
  if (!esIdSuscripcion(id)) return null
  if (typeof zona !== 'string' || zonaPorSlug(zona) === null) return null
  if (typeof ultimaRenovacion !== 'number' || !Number.isFinite(ultimaRenovacion)) return null
  return { id, zona, ultimaRenovacion }
}

/** El texto a guardar en `claveEstadoGuardado`: solo id, zona y última renovación. */
export function serializarEstadoGuardado(estado: EstadoGuardado): string {
  return JSON.stringify({ id: estado.id, zona: estado.zona, ultimaRenovacion: estado.ultimaRenovacion })
}
