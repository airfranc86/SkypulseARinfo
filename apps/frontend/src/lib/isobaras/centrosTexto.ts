/**
 * Text alternative to the H and L marks on the map ("Alta de 1028 hPa, 38,3° S 52,5° O, a 410 km de tu
 * ubicación"), for screen readers and for anyone who cannot make out the map. Pure module.
 */
import { formatearKm, haversineKm, type LatLon } from '../medicion/distancia.ts'
import type { Centro } from './formato.ts'

const UN_DECIMAL = new Intl.NumberFormat('es-AR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/**
 * "38,3° S" / "52,5° O": degrees to one decimal with the hemisphere letter, Argentine style. The hemisphere is
 * decided on the ROUNDED value, so a point that shows as "0,0°" carries no letter (never "0,0° S" or "0,0° N").
 */
function grados(valor: number, positivo: string, negativo: string): string {
  const texto = UN_DECIMAL.format(Math.abs(valor))
  const esCero = Number(texto.replace(',', '.')) === 0
  return esCero ? `${texto}°` : `${texto}° ${valor < 0 ? negativo : positivo}`
}

export function textoDelCentro(centro: Centro, usuario: LatLon | null): string {
  const nombre = centro.t === 'H' ? 'Alta' : 'Baja'
  // The pressure is written without a thousands separator ("1028"), as on every weather chart.
  const base = `${nombre} de ${Math.round(centro.p)} hPa, ${grados(centro.lat, 'N', 'S')} ${grados(centro.lon, 'E', 'O')}`
  if (!usuario) return base
  return `${base}, a ${formatearKm(haversineKm(usuario, centro))} de tu ubicación`
}

export function textosDeLosCentros(centros: ReadonlyArray<Centro>, usuario: LatLon | null): string[] {
  return centros.map((c) => textoDelCentro(c, usuario))
}
