/**
 * ApiError y su clasificación — separado de api.ts a propósito: api.ts lee
 * `import.meta.env` a nivel de módulo (inyectado por Vite), lo que revienta
 * si algo lo importa bajo `node --test` (sin bundler). Este módulo no tiene
 * ese problema, así que es el que se testea directo.
 */

/** Error de API con status HTTP — permite distinguir 503 (cold start de Render) de otros fallos. */
export class ApiError extends Error {
  status: number
  /** Segundos hasta poder reintentar, del header Retry-After (slowapi en 429). Null si no vino. */
  retryAfter: number | null
  /**
   * True cuando el body trajo un `detail`/`message`/`error` reconocible — o sea, es NUESTRO
   * backend respondiendo con una razón real (ej. un proveedor upstream saturado), no el 503
   * nativo de Render al hibernar (que no es JSON nuestro y cae al fallback `HTTP 503`).
   * `isColdStart()` usa este flag para no confundir ambos casos.
   */
  hasDetail: boolean
  constructor(message: string, status: number, retryAfter: number | null = null, hasDetail = false) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
    this.hasDetail = hasDetail
  }
}

// ── Clasificación de ApiError — usada por useWeather.ts para decidir reintentos y mensajes ──

/** El backend (Render free-tier) hiberna tras ~15min de inactividad — el primer
 *  request tras hibernar puede tardar 20-30s en despertar. Render devuelve un 503 nativo
 *  (sin JSON nuestro) mientras tanto — se distingue de isProviderSaturated() por eso. */
export function isColdStart(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503 && !error.hasDetail
}

/**
 * 503 con `detail` reconocible = nuestro backend está despierto pero un proveedor upstream
 * (Open-Meteo, SMN) no le contesta — típicamente un 429 por cuota de IP compartida agotada
 * en Render, no un cold start. Confirmado en logs de Render el 2026-09-20 (ver FRA-2026-09-20).
 * Reintentar unas pocas veces ayuda si es un blip pasajero; si es cuota diaria agotada, no se
 * resuelve solo, así que no vale la pena la espera larga de isColdStart.
 */
export function isProviderSaturated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503 && error.hasDetail
}

/** Errores 4xx (validación, rate limit, ICAO inválido, etc.) son permanentes para
 *  el mismo request — reintentar no cambia el resultado (las coordenadas no cambian
 *  entre reintentos), solo agrega latencia antes de mostrar el error real. */
export function isClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500
}
