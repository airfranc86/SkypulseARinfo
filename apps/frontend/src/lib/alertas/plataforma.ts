/**
 * Qué se le muestra a la persona para activar los avisos push según su navegador (FRA-357, T7a):
 * activar, instalar la app (iPhone), abrir en el navegador (Instagram/Facebook) o "sin soporte".
 * Todo entra por parámetro (`EntornoPush`): el módulo no toca `window` ni `navigator`, así que
 * `node --test` puede cubrir cada regla. Los textos largos de la pantalla los pone T7b; acá solo
 * van los códigos y los pasos de instalación que fija el ticket.
 *
 * Orden de las reglas:
 *  1. Navegador interno de Instagram/Facebook/Messenger: no deja instalar ni pedir permiso, aunque
 *     exponga PushManager. Se pide abrir la página en Safari (iOS) o Chrome (Android).
 *  2. iOS: con una versión anterior a 16.4 no hay forma de recibir push. Si no, sin instalar se
 *     explican los pasos (una pestaña de Safari no tiene PushManager hasta instalar: no es "sin
 *     soporte"); instalada se activa si están las tres APIs.
 *  3. El resto (Android, escritorio): se activa si están PushManager, service worker y Notification.
 */

export interface EntornoPush {
  userAgent: string
  /** `navigator.platform`; solo ayuda a reconocer iOS, puede faltar. */
  platform?: string
  maxTouchPoints: number
  /** App instalada: `display-mode: standalone` o `navigator.standalone` (iOS). */
  standalone: boolean
  tienePushManager: boolean
  tieneServiceWorker: boolean
  tieneNotification: boolean
}

export type PlataformaPush = 'ios' | 'android' | 'escritorio'
export type AppEmbebida = 'instagram' | 'facebook'
export type NavegadorSugerido = 'safari' | 'chrome'
export type MotivoSinSoporte = 'sin-push-manager' | 'sin-service-worker' | 'sin-notification' | 'ios-viejo'

export type Disponibilidad =
  | { tipo: 'activar'; plataforma: PlataformaPush }
  | {
      tipo: 'instalar-ios'
      pasos: readonly string[]
      /** iOS mínimo para recibir push de una página web instalada. */
      versionMinima: string
      /** La app instalada no comparte datos con Safari: la ciudad hay que elegirla de nuevo. */
      datosSeparados: true
    }
  | { tipo: 'abrir-en-navegador'; app: AppEmbebida; sugerido: NavegadorSugerido }
  | { tipo: 'sin-soporte'; motivo: MotivoSinSoporte }

export const VERSION_MINIMA_IOS = '16.4'

/** Los pasos del ticket para instalar SkyPulse en el iPhone. */
export const PASOS_INSTALAR_IOS: readonly string[] = Object.freeze([
  'Abrí esta página en Safari.',
  'Tocá Compartir y elegí «Agregar a inicio».',
  'Abrí SkyPulse desde el ícono y tocá «Activar avisos».',
])

const [IOS_MAYOR_MINIMO, IOS_MENOR_MINIMO] = VERSION_MINIMA_IOS.split('.').map(Number)

const RE_IOS = /iPhone|iPad|iPod/
const RE_MAC = /Macintosh/
const RE_VERSION_IOS = /OS (\d+)_(\d+)/
const RE_INSTAGRAM = /Instagram/
const RE_FACEBOOK = /FBAN|FBAV|FB_IAB/

function textoSeguro(valor: unknown): string {
  return typeof valor === 'string' ? valor : ''
}

/** iPhone/iPad/iPod, o un iPad que pide el sitio de escritorio y se anuncia como Mac (con pantalla táctil). */
function esIos(userAgent: string, platform: string, maxTouchPoints: number): boolean {
  if (RE_IOS.test(userAgent) || RE_IOS.test(platform)) return true
  return RE_MAC.test(userAgent) && Number.isFinite(maxTouchPoints) && maxTouchPoints > 1
}

/** `{mayor, menor}` de iOS si el user agent la trae ("CPU iPhone OS 16_3"); null si no (iPad como Mac). */
function versionDeIos(userAgent: string): { mayor: number; menor: number } | null {
  const partes = RE_VERSION_IOS.exec(userAgent)
  return partes ? { mayor: Number(partes[1]), menor: Number(partes[2]) } : null
}

function esIosAnterior(userAgent: string): boolean {
  const version = versionDeIos(userAgent)
  if (version === null) return false
  if (version.mayor !== IOS_MAYOR_MINIMO) return version.mayor < IOS_MAYOR_MINIMO
  return version.menor < IOS_MENOR_MINIMO
}

function appEmbebida(userAgent: string): AppEmbebida | null {
  if (RE_INSTAGRAM.test(userAgent)) return 'instagram'
  if (RE_FACEBOOK.test(userAgent)) return 'facebook'
  return null
}

/** El primer API que falta, en el orden PushManager, service worker, Notification; null si están los tres. */
function apiFaltante(entorno: EntornoPush): MotivoSinSoporte | null {
  if (!entorno.tienePushManager) return 'sin-push-manager'
  if (!entorno.tieneServiceWorker) return 'sin-service-worker'
  if (!entorno.tieneNotification) return 'sin-notification'
  return null
}

function conApis(entorno: EntornoPush, plataforma: PlataformaPush): Disponibilidad {
  const faltante = apiFaltante(entorno)
  return faltante === null ? { tipo: 'activar', plataforma } : { tipo: 'sin-soporte', motivo: faltante }
}

function disponibilidadIos(entorno: EntornoPush, userAgent: string): Disponibilidad {
  if (esIosAnterior(userAgent)) return { tipo: 'sin-soporte', motivo: 'ios-viejo' }
  if (!entorno.standalone) {
    return {
      tipo: 'instalar-ios',
      pasos: PASOS_INSTALAR_IOS,
      versionMinima: VERSION_MINIMA_IOS,
      datosSeparados: true,
    }
  }
  return conApis(entorno, 'ios')
}

/** Qué mostrar para activar los avisos en este entorno. No lanza con datos ausentes o raros. */
export function detectarDisponibilidad(entorno: EntornoPush): Disponibilidad {
  const userAgent = textoSeguro(entorno.userAgent)
  const platform = textoSeguro(entorno.platform)
  const ios = esIos(userAgent, platform, entorno.maxTouchPoints)

  const app = appEmbebida(userAgent)
  if (app !== null) return { tipo: 'abrir-en-navegador', app, sugerido: ios ? 'safari' : 'chrome' }

  if (ios) return disponibilidadIos(entorno, userAgent)
  return conApis(entorno, userAgent.includes('Android') ? 'android' : 'escritorio')
}
