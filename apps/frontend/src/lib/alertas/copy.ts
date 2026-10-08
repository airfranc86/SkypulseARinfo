/**
 * Todo el texto de la pantalla de avisos push (FRA-357, T7b), en un módulo puro para poder probarlo con
 * `node --test`: la página, el consentimiento, los botones y un mensaje por cada estado, error y caso de
 * disponibilidad. Voseo rioplatense, tono neutro, sin jerga técnica ni códigos HTTP.
 *
 * BORRADOR: el dueño aprueba estos textos antes de publicar. Los pasos para instalar la app en el iPhone
 * no están acá: los fija `PASOS_INSTALAR_IOS` en `plataforma.ts`.
 */
import { VERSION_MINIMA_IOS, type Disponibilidad } from './plataforma.ts'
import type { ErrorAvisos, EstadoAvisos, MotivoNoActivable } from './suscripcion.ts'

/** Cómo va el aviso de prueba, aparte del estado de la suscripción. */
export type EstadoPrueba =
  | { tipo: 'libre' }
  | { tipo: 'enviando' }
  | { tipo: 'enviada' }
  /** El servidor pidió esperar (una prueba por minuto): faltan `segundos`. */
  | { tipo: 'espera'; segundos: number }
  | { tipo: 'error'; error: ErrorAvisos }

export const RUTA_PRIVACIDAD = '/privacidad'

/** Nombre accesible de la campana del header (un enlace a `/alertas`). */
export const NOMBRE_CAMPANA = 'Avisos de tormenta'

/**
 * ¿Existe el envío programado de avisos de tormenta (FRA-355/356)? Mientras sea `false`, todos los textos
 * describen solo lo que existe hoy: registrar el celular para una ciudad, mandarse un aviso de prueba y
 * desactivar, y dicen que los avisos automáticos todavía no están activos. Con `true` vuelven los textos
 * originales (los de `TEXTOS_CON_ENVIO`). Cuando el envío exista, se cambia esta constante.
 *
 * Antes de ponerla en `true`: (1) el consentimiento de hoy cubre solo el aviso de prueba, así que hay que pedir
 * consentimiento nuevo a quienes ya se registraron o darlos de baja (Ley 25.326, finalidad y consentimiento);
 * (2) la campana (`VITE_ALERTAS_VISIBLE`) no se enciende antes de que el envío exista.
 */
export const ENVIO_AUTOMATICO_ACTIVO = false

/** Los textos que dependen de si el envío automático existe, cada uno con su versión según el modo. */
interface TextosPorModo {
  titulo: string
  intro: string
  consentimiento: string
  tituloInstalarIos: string
  /** El estado "activo": con o sin nombre de ciudad. */
  estadoActivo: (nombreZona: string | null) => string
}

/** Los textos ORIGINALES, con el envío automático activo. No tocar: es lo que vuelve al activar la constante. */
const TEXTOS_CON_ENVIO: TextosPorModo = Object.freeze({
  titulo: 'Avisos de tormenta en tu celular',
  intro:
    'SkyPulse avisa a las 21 h cuando se esperan tormentas para mañana y, durante el día, si aparece algo nuevo. No manda nada entre las 22 y las 7.',
  consentimiento:
    'Acepto que SkyPulse guarde la dirección técnica de entrega de mi navegador y mi ciudad, solo para enviarme estos avisos. Puedo darme de baja cuando quiera.',
  tituloInstalarIos: '¿Usás iPhone? Instalá SkyPulse para recibir avisos',
  estadoActivo: (nombreZona: string | null) => (nombreZona === null ? 'Avisos activados.' : `Avisos activados para ${nombreZona}.`),
})

/** Los textos de hoy, sin envío automático. */
const TEXTOS_SIN_ENVIO: TextosPorModo = Object.freeze({
  titulo: 'Avisos de tormenta: todavía no están activos',
  intro:
    'Los avisos automáticos de tormenta todavía no están activos. Por ahora podés registrar tu celular para una ciudad, mandarte un aviso de prueba y desactivar el registro cuando quieras.',
  consentimiento:
    'Acepto que SkyPulse guarde la dirección técnica de entrega de mi navegador y mi ciudad, solo para mandarme el aviso de prueba que pida. Puedo darme de baja cuando quiera.',
  tituloInstalarIos: '¿Usás iPhone? Instalá SkyPulse para probar los avisos',
  estadoActivo: (nombreZona: string | null) =>
    `${nombreZona === null ? 'Celular registrado.' : `Celular registrado para ${nombreZona}.`} Los avisos automáticos todavía no están activos. Por ahora podés mandarte un aviso de prueba.`,
})

/**
 * Los textos de la pantalla según el modo. `envioAutomatico` es un parámetro (por defecto, la constante) para
 * que las pruebas puedan pedir cualquiera de los dos sin depender del estado del módulo.
 */
export function copyDe(envioAutomatico: boolean = ENVIO_AUTOMATICO_ACTIVO) {
  const { titulo, intro, consentimiento, tituloInstalarIos } = envioAutomatico ? TEXTOS_CON_ENVIO : TEXTOS_SIN_ENVIO
  return Object.freeze({
    titulo,
    intro,
    /** La leyenda va en tres partes para que `smn.gob.ar` sea un enlace; los bordes van sin espacios (los pone quien arma la frase). */
    aclaracionOficial: Object.freeze({
      antes: 'Es un pronóstico de SkyPulse, no un aviso oficial. Los avisos oficiales están en',
      enlace: 'smn.gob.ar',
      despues: '.',
    }),
    etiquetaCiudad: 'Ciudad',
    opcionCiudad: 'Elegí una ciudad',
    consentimiento,
    enlacePrivacidad: 'Leer la política de privacidad',
    activar: 'Activar avisos',
    activando: 'Activando…',
    probar: 'Probar aviso',
    probando: 'Mandando el aviso de prueba…',
    desactivar: 'Desactivar avisos',
    desactivando: 'Desactivando…',
    notaProbar: 'Se puede probar una vez por minuto.',
    tituloInstalarIos,
  })
}

/** Los textos que se publican: los del modo que fija `ENVIO_AUTOMATICO_ACTIVO`. */
export const COPY = copyDe()

// ── Ciudad ───────────────────────────────────────────────────────────────────

/** La línea bajo el selector: la ciudad sugerida según la ubicación o, sin sugerencia, que elija una. */
export function lineaCiudad(nombreSugerida: string | null): string {
  return nombreSugerida === null
    ? 'Elegí tu ciudad'
    : `Ciudad sugerida según tu ubicación: ${nombreSugerida}. Confirmala o elegí otra.`
}

// ── Botones ──────────────────────────────────────────────────────────────────

function segundosValidos(segundos: number | null): segundos is number {
  return typeof segundos === 'number' && Number.isFinite(segundos) && segundos > 0
}

/** "Probar aviso", o "Probar aviso (esperá N s)" mientras el servidor pide esperar. */
export function etiquetaProbar(segundos: number | null): string {
  return segundosValidos(segundos) ? `${COPY.probar} (esperá ${Math.ceil(segundos)} s)` : COPY.probar
}

const RAZON_DESHABILITADO: Record<MotivoNoActivable, string> = {
  'sin-soporte': 'Tu navegador no puede recibir avisos.',
  'permiso-denegado':
    'El navegador tiene bloqueados los avisos de SkyPulse. Podés habilitarlos desde los ajustes de tu navegador.',
  'sin-consentimiento': 'Para activar los avisos, tildá la casilla de consentimiento.',
  'sin-zona': 'Para activar los avisos, elegí tu ciudad.',
}

/** Por qué "Activar avisos" está deshabilitado: el texto que describe al botón. */
export function razonDeshabilitado(motivo: MotivoNoActivable): string {
  return RAZON_DESHABILITADO[motivo]
}

// ── Errores y estados ────────────────────────────────────────────────────────

/** Un error de la suscripción o de la prueba, en lenguaje de todos los días (sin códigos de estado). */
export function mensajeDeError(error: ErrorAvisos): string {
  switch (error.motivo) {
    case 'vencida':
      return 'La suscripción venció. Activá los avisos de nuevo.'
    case 'espera':
      return segundosValidos(error.segundos)
        ? `Esperá ${Math.ceil(error.segundos)} s y probá de nuevo.`
        : 'Esperá un momento y probá de nuevo.'
    case 'servicio-push':
      return 'El servicio de notificaciones de tu navegador no aceptó el aviso. Probá de nuevo en unos minutos.'
    case 'no-disponible':
      return 'Los avisos no están disponibles en este momento. Probá de nuevo más tarde.'
    case 'datos-invalidos':
      return 'No pudimos registrar tu pedido. Revisá la ciudad elegida y probá de nuevo.'
    default:
      return 'No pudimos completar la acción. Revisá tu conexión y probá de nuevo.'
  }
}

/** El mensaje del estado de la suscripción; vacío en "inactivo" (no hay nada que anunciar). */
export function mensajeDeEstado(
  estado: EstadoAvisos,
  nombreZona: string | null,
  envioAutomatico: boolean = ENVIO_AUTOMATICO_ACTIVO,
): string {
  switch (estado.tipo) {
    case 'pidiendo-permiso':
      return 'Activando… Respondé el pedido de permiso de tu navegador.'
    case 'suscribiendo':
      return COPY.activando
    case 'sin-respuesta':
      return 'Todavía no respondiste el pedido de permiso. Tocá «Activar avisos» para intentarlo de nuevo.'
    case 'denegado':
      return 'No diste permiso para recibir avisos. Podés habilitarlo desde los ajustes de tu navegador.'
    case 'activo':
      return (envioAutomatico ? TEXTOS_CON_ENVIO : TEXTOS_SIN_ENVIO).estadoActivo(nombreZona)
    case 'error':
      return mensajeDeError(estado.error)
    default:
      return ''
  }
}

/** El mensaje del aviso de prueba; vacío cuando no hay nada que decir. */
export function mensajeDePrueba(prueba: EstadoPrueba): string {
  switch (prueba.tipo) {
    case 'enviando':
      return COPY.probando
    case 'enviada':
      return 'Te mandamos un aviso de prueba. Puede tardar unos segundos en llegar.'
    case 'espera':
      return segundosValidos(prueba.segundos)
        ? `Todavía no se puede mandar otro aviso de prueba. Esperá ${Math.ceil(prueba.segundos)} s.`
        : 'Todavía no se puede mandar otro aviso de prueba. Esperá un momento.'
    case 'error':
      return mensajeDeError(prueba.error)
    default:
      return ''
  }
}

// ── Disponibilidad ───────────────────────────────────────────────────────────

const NOMBRE_APP = { instagram: 'Instagram', facebook: 'Facebook' } as const
const NOMBRE_NAVEGADOR = { safari: 'Safari', chrome: 'Chrome' } as const

const SIN_SOPORTE = 'Tu navegador no puede recibir avisos.'

const DETALLE_SIN_SOPORTE = {
  'sin-push-manager': 'No admite notificaciones de páginas web. Probá con otro navegador o actualizalo.',
  'sin-service-worker': 'No deja que SkyPulse funcione en segundo plano. Probá con otro navegador o actualizalo.',
  'sin-notification': 'No permite mostrar notificaciones. Probá con otro navegador o actualizalo.',
  'ios-viejo': `Hace falta iOS ${VERSION_MINIMA_IOS} o posterior. Actualizá el iPhone desde Ajustes, en General, Actualización de software.`,
} as const

/**
 * El mensaje principal según dónde se abrió la página. Vacío cuando se puede activar. Los pasos del iPhone
 * van aparte (`PASOS_INSTALAR_IOS` y `notaInstalarIos`).
 */
export function mensajeDeDisponibilidad(disponibilidad: Disponibilidad): string {
  switch (disponibilidad.tipo) {
    case 'instalar-ios':
      return 'En el iPhone, los avisos solo funcionan con SkyPulse instalado en la pantalla de inicio.'
    case 'abrir-en-navegador':
      return `Estás viendo SkyPulse dentro de ${NOMBRE_APP[disponibilidad.app]}, y ahí no se pueden activar los avisos. Abrí la página en ${NOMBRE_NAVEGADOR[disponibilidad.sugerido]}.`
    case 'sin-soporte':
      return `${SIN_SOPORTE} ${DETALLE_SIN_SOPORTE[disponibilidad.motivo]}`
    default:
      return ''
  }
}

/** La nota bajo los pasos del iPhone: la versión mínima y que hay que volver a elegir la ciudad. */
export function notaInstalarIos(versionMinima: string): string {
  return `Hace falta iOS ${versionMinima} o posterior. La app de inicio no comparte datos con Safari, así que vas a elegir la ciudad de nuevo.`
}
