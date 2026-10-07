import { useEffect } from 'react'
import { api } from '@/lib/api'
import type { ConfigAlertas } from '@/lib/alertas/config'
import { detectarDisponibilidad, type EntornoPush } from '@/lib/alertas/plataforma'
import {
  claveEstadoGuardado,
  cuerpoDeAlta,
  debeRenovar,
  esIdSuscripcion,
  leerEstadoGuardado,
  motivoDeError,
  normalizarPermiso,
  serializarEstadoGuardado,
  type EstadoGuardado,
  type PermisoNavegador,
} from '@/lib/alertas/suscripcion'
import { zonaPorSlug } from '@/lib/alertas/zonaSugerida'

/**
 * Renovación silenciosa de los avisos push (FRA-357, T7b) y, en el mismo módulo, el acceso al navegador que
 * comparten los dos hooks de avisos (entorno, permiso, estado guardado y suscripción actual).
 *
 * `useRenovarAvisos` va una sola vez en el layout raíz. Sin estado guardado no hace nada: ni red ni service
 * worker ni permiso, así que no cambia nada para quien nunca activó los avisos. Nunca pide permiso y nunca
 * registra el service worker (eso solo lo hace "Activar avisos").
 */

// ── Acceso al navegador ──────────────────────────────────────────────────────

/** Lo que `detectarDisponibilidad` necesita saber del navegador, leído una vez. */
export function entornoDelNavegador(): EntornoPush {
  const nav = navigator as Navigator & { standalone?: boolean }
  let standalone = nav.standalone === true
  try {
    standalone = standalone || window.matchMedia('(display-mode: standalone)').matches
  } catch {
    // Sin matchMedia (entornos viejos): se queda con `navigator.standalone`.
  }
  return {
    userAgent: nav.userAgent,
    platform: nav.platform,
    maxTouchPoints: nav.maxTouchPoints ?? 0,
    standalone,
    tienePushManager: 'PushManager' in window,
    tieneServiceWorker: 'serviceWorker' in navigator,
    tieneNotification: 'Notification' in window,
  }
}

/** El permiso de notificaciones ahora; "default" si el navegador no tiene `Notification`. */
export function permisoDelNavegador(): PermisoNavegador {
  return typeof Notification === 'undefined' ? 'default' : normalizarPermiso(Notification.permission)
}

export function leerEstadoLocal(): EstadoGuardado | null {
  try {
    return leerEstadoGuardado(localStorage.getItem(claveEstadoGuardado))
  } catch {
    return null
  }
}

export function guardarEstadoLocal(estado: EstadoGuardado): void {
  try {
    localStorage.setItem(claveEstadoGuardado, serializarEstadoGuardado(estado))
  } catch {
    // localStorage puede no estar disponible (modo privado, cuota): la suscripción sigue andando sin el guardado.
  }
}

export function borrarEstadoLocal(): void {
  try {
    localStorage.removeItem(claveEstadoGuardado)
  } catch {
    // Ídem: no hay nada que borrar si no se puede escribir.
  }
}

/**
 * El estado a guardar para la respuesta del alta (el servidor repite el `id` y la ciudad), o null si la
 * respuesta no trae un id de 22 caracteres base64url y una ciudad conocida.
 */
export function estadoGuardadoDeRespuesta(respuesta: unknown, ahoraMs: number): EstadoGuardado | null {
  const { id, zona } = (typeof respuesta === 'object' && respuesta !== null ? respuesta : {}) as Record<string, unknown>
  if (!esIdSuscripcion(id) || typeof zona !== 'string' || zonaPorSlug(zona) === null) return null
  return { id, zona, ultimaRenovacion: ahoraMs }
}

/** La suscripción push de este navegador, sin registrar nada: null si no hay service worker registrado o suscripción. */
export async function suscripcionActual(): Promise<PushSubscription | null> {
  if (!('serviceWorker' in navigator)) return null
  const registro = await navigator.serviceWorker.getRegistration('/')
  return registro ? registro.pushManager.getSubscription() : null
}

// ── Renovación ───────────────────────────────────────────────────────────────

let renovando = false

/** Repite el alta con la suscripción que ya existe (mismo id, renueva el vencimiento del servidor). */
async function renovar(guardado: EstadoGuardado): Promise<void> {
  try {
    const suscripcion = await suscripcionActual()
    if (suscripcion === null) return
    const respuesta = await api.alertasSuscribir(cuerpoDeAlta(suscripcion.toJSON(), guardado.zona))
    const nuevo = estadoGuardadoDeRespuesta(respuesta, Date.now())
    if (nuevo !== null) guardarEstadoLocal(nuevo)
  } catch (error) {
    // Si el servidor ya no la tiene hay que volver a activar desde la página; cualquier otro fallo se reintenta en la próxima visita.
    if (motivoDeError(error).motivo === 'vencida') borrarEstadoLocal()
  }
}

function hayQueRenovar(guardado: EstadoGuardado | null): guardado is EstadoGuardado {
  if (guardado === null || !debeRenovar(guardado.ultimaRenovacion, Date.now())) return false
  if (detectarDisponibilidad(entornoDelNavegador()).tipo !== 'activar') return false
  return permisoDelNavegador() === 'granted'
}

/**
 * Al abrir la web, si hay un estado guardado que ya toca renovar (7 días o más) y el permiso sigue concedido,
 * repite el alta en silencio. Sin clave VAPID en este despliegue (los avisos no están configurados) no hace nada.
 */
export function useRenovarAvisos(config: ConfigAlertas): void {
  const { claveVapid } = config
  useEffect(() => {
    if (claveVapid === null || renovando) return
    const guardado = leerEstadoLocal()
    if (!hayQueRenovar(guardado)) return
    renovando = true
    void renovar(guardado).finally(() => {
      renovando = false
    })
  }, [claveVapid])
}
