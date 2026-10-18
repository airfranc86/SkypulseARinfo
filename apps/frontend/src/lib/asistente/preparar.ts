/**
 * What the panel does when the person presses "Preguntar": the text, the place and the page are checked and shaped in one
 * pure step, before anything leaves the browser. The first thing that is wrong is what the panel tells the person: the
 * text first (it is what they are looking at), then the place.
 */
import { paginaParaEnviar, ubicacionValida, validarPregunta, type PreguntaAsistente } from './cliente.ts'

export type PreparacionPregunta =
  | { ok: true; pregunta: PreguntaAsistente }
  | { ok: false; motivo: 'vacia' | 'larga' | 'sin-ubicacion' }

export function prepararPregunta(
  texto: string,
  lat: number | null | undefined,
  lon: number | null | undefined,
  ruta: string | null | undefined,
): PreparacionPregunta {
  const validada = validarPregunta(texto)
  if (!validada.ok) return { ok: false, motivo: validada.motivo }
  const ubicacion = ubicacionValida(lat, lon)
  if (ubicacion === null) return { ok: false, motivo: 'sin-ubicacion' }
  return { ok: true, pregunta: { pregunta: validada.pregunta, pagina: paginaParaEnviar(ruta), ...ubicacion } }
}
