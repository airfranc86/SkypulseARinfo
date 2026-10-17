import type { ErrorAvisos } from './suscripcion.ts'

/**
 * El aviso de lluvia persistente (opt-in), PR 3b: la bandera que lo muestra y qué viaja con el alta.
 *
 * `AVISO_LLUVIA_DISPONIBLE` está en `true` desde el PR 3c: aparece la casilla, los textos y la política cuentan el aviso
 * y cada alta manda `lluvia` explícito. Con ella en `false` la pantalla, los textos y la política vuelven a ser los de
 * siempre y el alta NO manda el campo `lluvia` (para el servidor, "no cambiar lo que ya tenía"): sirve para apagar la
 * casilla sin tocar el servidor. Orden en que se encendió: (1) los textos, aprobados por el dueño; (2)
 * `ALERTAS_LLUVIA_ACTIVA=true` en el servidor (Render); (3) esta constante. Encenderla antes de (2) habría mostrado un
 * aviso que el servidor todavía no mandaba.
 */
export const AVISO_LLUVIA_DISPONIBLE = true

/** Cómo va el cambio de la casilla de lluvia con los avisos activos (se reenvía el alta con la preferencia). */
export type EstadoLluvia =
  | { tipo: 'libre' }
  | { tipo: 'guardando' }
  | { tipo: 'activada' }
  | { tipo: 'desactivada' }
  | { tipo: 'error'; error: ErrorAvisos }

/**
 * La preferencia que va en el alta y en cada renovación. Con la bandera apagada, `undefined`: el campo no viaja y el
 * servidor conserva lo que tenía. Con la bandera encendida, siempre `true` o `false` explícito: así cada alta y cada
 * renovación también repara cualquier índice que hubiera quedado desfasado en el servidor.
 */
export function lluviaDelAlta(disponible: boolean, lluvia: boolean): boolean | undefined {
  return disponible ? lluvia : undefined
}
