/**
 * The texts of Mora's question panel (rioplatense voseo). Plain data and pure functions, so `node --test` covers them.
 *
 * Rules: they never name the model or the provider, never show a status code or an error code, never alarm, and
 * always give a way forward. The first-use notice (D6) says the same as the "Asistente Mora (opcional)" section of
 * the privacy policy (`lib/privacidad.ts`); a test keeps them together. The owner approves every text before it ships.
 */
import type { ErrorPanel } from './cliente.ts'

export const AVISO_PRIMER_USO = Object.freeze({
  titulo: 'Antes de preguntar',
  texto:
    'Lo que escribís se envía a un proveedor de IA en EE. UU. para redactar la respuesta. No incluyas datos personales. No guardamos lo que escribís.',
  boton: 'Entendido',
})

/** The heading over the quick answers shown when the model cannot answer. */
export const TITULO_RESPUESTAS_RAPIDAS = 'Mientras tanto, esto es lo que ya tengo cargado'

/** "30 s", "5 min", "2 h": always rounded up, and never garbage for an odd number. */
export function esperaLegible(segundos: number): string {
  const s = Number.isFinite(segundos) && segundos > 0 ? Math.ceil(segundos) : 1
  if (s < 60) return `${s} s`
  if (s < 3600) return `${Math.ceil(s / 60)} min`
  return `${Math.ceil(s / 3600)} h`
}

export function textoDeValidacion(motivo: 'vacia' | 'larga' | 'sin-ubicacion'): string {
  switch (motivo) {
    case 'vacia':
      return 'Escribí tu pregunta.'
    case 'larga':
      return 'La pregunta puede tener hasta 300 caracteres.'
    case 'sin-ubicacion':
      return 'Elegí un lugar en Argentina para preguntarme por su clima.'
  }
}

export function textoDeError(error: ErrorPanel): string {
  switch (error.tipo) {
    case 'cupo-diario':
      return 'Llegaste al máximo de preguntas de hoy. Mañana podés seguir preguntándome.'
    case 'espera':
      return error.motivo === 'en-curso'
        ? `Todavía estoy respondiendo tu pregunta anterior. Probá de nuevo en ${esperaLegible(error.segundos)}.`
        : `Estás preguntando muy seguido. Probá de nuevo en ${esperaLegible(error.segundos)}.`
    case 'no-disponible':
      return error.segundos === null
        ? 'Ahora no puedo responder. Mirá la página de Previsión mientras tanto.'
        : `Ahora no puedo responder. Probá de nuevo en ${esperaLegible(error.segundos)} o mirá la página de Previsión.`
    case 'apagado':
      return 'Ahora no puedo responder. Mirá la página de Previsión mientras tanto.'
    case 'invalida':
      return 'No pude entender esa pregunta. Probá escribirla de otra forma.'
    case 'sin-conexion':
      return 'No pude conectarme. Revisá tu conexión y probá de nuevo.'
  }
}
