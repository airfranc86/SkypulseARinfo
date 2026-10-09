/**
 * Textos de la política de privacidad (FRA-358). Datos puros, sin React ni `@/`: así se prueban con `node --test`.
 *
 * Cada afirmación tiene que coincidir con lo que el código hace:
 * - la suscripción guarda `endpoint`, `p256dh`, `auth`, `zona` y `actualizada` (la última renovación), sin
 *   fecha de alta (`apps/backend/app/services/alertas/suscripcion.py`);
 * - la base es la de Upstash, en us-east-1 (Virginia, EE. UU.);
 * - el servidor corre en Render con el registro de accesos de uvicorn por defecto, que incluye la IP y la ruta con
 *   su query (las coordenadas): por eso se dice, y no se afirma ningún plazo de conservación que no se verificó.
 *
 * Son un BORRADOR que aprueba el dueño antes de publicar.
 */

import { ENVIO_AUTOMATICO_ACTIVO } from './alertas/copy.ts'

export interface SeccionPrivacidad {
  titulo: string
  parrafos: readonly string[]
  /** La sección que muestra el botón y la dirección de contacto. */
  contacto?: boolean
}

/** Nombre de la variable de entorno de Vite (Vercel) con la dirección de contacto. No hay ninguna en el repo. */
export const VARIABLE_CONTACTO_PRIVACIDAD = 'VITE_PRIVACY_CONTACT_EMAIL'

export const CONTACTO_PRIVACIDAD = Object.freeze({
  asunto: 'SkyPulse: consulta sobre mis datos',
  cuerpo: 'Hola, quiero hacer una consulta sobre mis datos en SkyPulse (avisos en el celular).\n\n',
})

export interface ContactoPrivacidad {
  email: string
  /** El enlace `mailto:` ya armado, con el asunto y el cuerpo codificados. */
  mailto: string
}

const MAX_LARGO_EMAIL = 254
// Conservadora a propósito: la dirección termina dentro de un `mailto:`, así que no admite nada que pueda abrir
// parámetros (`?`, `&`), inyectar encabezados (`%`, saltos de línea) o sumar destinatarios (`,`, `;`, espacios).
const USUARIO = /^[A-Za-z0-9](?:[A-Za-z0-9._+-]*[A-Za-z0-9])?$/
const ETIQUETA_DOMINIO = /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/
const TLD = /^[A-Za-z]{2,}$/

/**
 * La dirección recortada si es una dirección de email simple y segura para un `mailto:`; null si falta, no es texto
 * o tiene cualquier forma dudosa. Nunca lanza.
 */
export function emailContactoValido(valor: unknown): string | null {
  if (typeof valor !== 'string') return null
  const email = valor.trim()
  if (email === '' || email.length > MAX_LARGO_EMAIL) return null
  const partes = email.split('@')
  if (partes.length !== 2) return null
  const [usuario, dominio] = partes
  if (!USUARIO.test(usuario)) return null
  const etiquetas = dominio.split('.')
  if (etiquetas.length < 2) return null
  if (!etiquetas.every((etiqueta) => ETIQUETA_DOMINIO.test(etiqueta))) return null
  return TLD.test(etiquetas[etiquetas.length - 1]) ? email : null
}

/**
 * El enlace `mailto:` que abre el correo que la persona tenga configurado (el del navegador, el del celular...).
 * Devuelve null si la dirección no es válida: sin dirección no hay enlace.
 */
export function mailtoPrivacidad(email: unknown): string | null {
  const valida = emailContactoValido(email)
  if (valida === null) return null
  const { asunto, cuerpo } = CONTACTO_PRIVACIDAD
  return `mailto:${valida}?subject=${encodeURIComponent(asunto)}&body=${encodeURIComponent(cuerpo)}`
}

/**
 * El contacto de privacidad que sale del entorno de build (`VITE_PRIVACY_CONTACT_EMAIL`, definida en Vercel). Es
 * pura: el entorno entra por parámetro (quien llama pasa `import.meta.env`), igual que `leerConfigAlertas`, así
 * `node --test` la cubre sin tocar Vite. Devuelve null si la variable falta, está en blanco o no es una dirección
 * válida: la página muestra entonces el texto sin botón y sin inventar ninguna dirección.
 */
export function leerContactoPrivacidad(env: Record<string, unknown> | undefined): ContactoPrivacidad | null {
  const entorno = typeof env === 'object' && env !== null ? env : {}
  const email = emailContactoValido(entorno[VARIABLE_CONTACTO_PRIVACIDAD])
  if (email === null) return null
  const mailto = mailtoPrivacidad(email)
  return mailto === null ? null : Object.freeze({ email, mailto })
}

/**
 * El párrafo de para qué se usan los datos de los avisos. Con el envío automático activo es el texto original;
 * sin él, dice lo verdadero hoy: el único aviso que se envía es el de prueba que la persona pide.
 */
function parrafoDeUso(envioAutomatico: boolean): string {
  return envioAutomatico
    ? 'Usamos esos datos solo para enviarte esos avisos: a las 21 h para el día siguiente y, durante el día, si aparece algo nuevo; nunca entre las 22 y las 7. También para la notificación de prueba cuando la pedís. No los usamos para nada más ni los compartimos.'
    : 'Hoy usamos esos datos solo para mandarte el aviso de prueba cuando lo pedís: es el único aviso que se envía. Los avisos automáticos de tormenta todavía no están activos. Si se activan, vamos a actualizar esta política y a pedirte de nuevo tu consentimiento. No los usamos para nada más ni los compartimos.'
}

/**
 * Las secciones de la política según el modo. `envioAutomatico` es un parámetro (por defecto, la constante) para
 * que las pruebas puedan pedir cualquiera de los dos sin depender del estado del módulo.
 */
export function seccionesPrivacidad(
  envioAutomatico: boolean = ENVIO_AUTOMATICO_ACTIVO,
): readonly SeccionPrivacidad[] {
  return Object.freeze([
    {
      titulo: 'Qué datos recolectamos',
      parrafos: [
        'SkyPulse no tiene registro de usuarios ni formularios que pidan nombre, email o teléfono. El único dato personal que puede usarse es tu ubicación geográfica (latitud/longitud), y es opcional: se pide vía el permiso de geolocalización del navegador, solo para mostrarte clima, terremotos y demás datos cerca tuyo. Podés rechazar el permiso y buscar tu ciudad manualmente.',
        'Si activás los avisos en el celular (también opcional), se guarda además lo que se explica en la sección «Avisos en el celular (opcional)».',
      ],
    },
    {
      titulo: 'Dónde se guarda y adónde viaja tu ubicación',
      parrafos: [
        'La última ubicación que elegiste se guarda en el almacenamiento local de tu navegador (localStorage), en tu dispositivo.',
        'Para mostrarte el clima y el resto de los datos, el navegador envía esas coordenadas al servidor de SkyPulse (alojado en Render), que las usa para consultar las fuentes meteorológicas y sísmicas y te devuelve el resultado. SkyPulse no la guarda en una base de datos ni la asocia a vos; puede quedar unos minutos en la memoria del servidor para no repetir la misma consulta.',
        'Como en cualquier servidor web, los registros de acceso del servidor pueden guardar la dirección IP desde la que te conectás y la ruta que consultaste, que incluye las coordenadas. Esos registros los conserva el proveedor de alojamiento y los usamos solo para detectar y corregir fallas. Si el servidor tiene un error, el servicio de reporte de fallas que usamos (Sentry) puede recibir la dirección de esa consulta, sin tu nombre ni datos de contacto.',
      ],
    },
    {
      titulo: 'Avisos en el celular (opcional)',
      contacto: true,
      parrafos: [
        'Si activás los avisos de tormenta en el celular, SkyPulse guarda: la dirección técnica de entrega que genera tu navegador para recibir notificaciones, dos claves de cifrado de esa suscripción, la ciudad que elegiste y la fecha de la última renovación. No guardamos tu nombre, email, teléfono ni tu ubicación exacta. La suscripción no incluye tu IP; igual que en cualquier otro pedido, la IP puede quedar en los registros de acceso descriptos arriba.',
        parrafoDeUso(envioAutomatico),
        'Cada aviso viaja cifrado a través del servicio de notificaciones de tu navegador (Google, Mozilla, Apple o Microsoft, según cuál uses), que recibe la dirección técnica de entrega y el momento en que llega el aviso. Es un pronóstico de SkyPulse, no un aviso oficial del SMN.',
        'Los datos se guardan en una base de datos de Upstash ubicada en Estados Unidos (Virginia). Se borran cuando desactivás los avisos, automáticamente a los 180 días sin abrir SkyPulse (la fecha se renueva cada vez que abrís la web con los avisos activados) y cuando el servicio de notificaciones informa que esa suscripción dejó de existir.',
        'Podés darte de baja cuando quieras: entrá a /alertas y tocá «Desactivar avisos». Eso borra tu suscripción de nuestra base. Bloquear las notificaciones desde los ajustes del navegador corta los avisos, pero no borra lo que ya guardamos: para eso tenés que desactivarlos desde esa página.',
        'Para consultas, o para pedir el acceso o el borrado de tus datos (por ejemplo, si ya no tenés el navegador donde activaste los avisos), escribinos. Como no guardamos tu nombre ni tu email, no podemos reconocerte: la forma más directa de borrar tus datos es desactivar los avisos desde la página.',
      ],
    },
    {
      titulo: 'Cookies y analítica',
      parrafos: [
        'Usamos Google Tag Manager y Vercel Analytics para entender cómo se usa el sitio (páginas visitadas, básicamente). Estas herramientas solo se activan si aceptás el banner de cookies que aparece en tu primera visita. Podés rechazarlo y seguir usando SkyPulse sin ninguna limitación — tu elección se recuerda en tu navegador.',
      ],
    },
    {
      titulo: 'Servicios externos que consultamos',
      parrafos: [
        'Los datos meteorológicos y sísmicos que mostramos vienen de fuentes públicas: SMN, USGS, EMSC y Open-Meteo. Nuestro servidor consulta esas APIs con las coordenadas que elegiste, pero no les enviamos ningún otro dato tuyo. El botón de contribución de Cafecito se carga desde su servidor (cdn.cafecito.app), por lo que ese servicio recibe tu dirección IP cuando se muestra la página.',
      ],
    },
    {
      titulo: 'Tus opciones',
      parrafos: [
        'Podés borrar la ubicación guardada y las cookies de analítica en cualquier momento desde la configuración de tu navegador. Al hacerlo, SkyPulse vuelve a pedirte el permiso de ubicación y a mostrar el banner de cookies en tu próxima visita.',
        'Si activaste los avisos en el celular, podés desactivarlos cuando quieras desde /alertas.',
      ],
    },
  ])
}

/** La política que se publica: la del modo que fija `ENVIO_AUTOMATICO_ACTIVO`. */
export const SECCIONES_PRIVACIDAD: readonly SeccionPrivacidad[] = seccionesPrivacidad()
