/**
 * Configuración de los avisos push que sale del entorno de build (FRA-357, T7b): si la campana del header se
 * muestra y cuál es la clave pública VAPID. Es pura: el entorno entra por parámetro (quien llama pasa
 * `import.meta.env`), así `node --test` la cubre sin tocar Vite.
 */

export interface ConfigAlertas {
  /** La campana del header se muestra solo con `VITE_ALERTAS_VISIBLE === 'true'` (la página `/alertas` no depende de esto). */
  visible: boolean
  /** `VITE_VAPID_PUBLIC_KEY` recortada; null si falta, está en blanco o no es texto. */
  claveVapid: string | null
}

const VALOR_VISIBLE = 'true'

function textoDe(env: Record<string, unknown>, nombre: string): string | null {
  const valor = env[nombre]
  return typeof valor === 'string' ? valor : null
}

function claveRecortada(env: Record<string, unknown>): string | null {
  const clave = textoDe(env, 'VITE_VAPID_PUBLIC_KEY')?.trim() ?? ''
  return clave === '' ? null : clave
}

/**
 * La configuración de los avisos. La bandera es estricta: solo el texto exacto "true" muestra la campana
 * ("TRUE", "1" o un valor ausente la dejan oculta). No lanza con un entorno ausente o raro.
 */
export function leerConfigAlertas(env: Record<string, unknown> | undefined): ConfigAlertas {
  const entorno = typeof env === 'object' && env !== null ? env : {}
  return Object.freeze({
    visible: textoDe(entorno, 'VITE_ALERTAS_VISIBLE') === VALOR_VISIBLE,
    claveVapid: claveRecortada(entorno),
  })
}
