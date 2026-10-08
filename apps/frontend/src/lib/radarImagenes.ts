// Capturas de referencia de /radar: solo sirven para que la gente sepa cuál es la imagen de radar,
// cuál la de satélite visible y cuál la de satélite infrarrojo. Los archivos viven en public/radar/
// (propios del sitio, nada enlazado de afuera). La página solo dibuja estos datos.

export interface RadarImagen {
  id: 'radar' | 'satelite-visible' | 'satelite-infrarrojo'
  /** Ruta pública del archivo propio del sitio. */
  src: string
  alt: string
  width: number
  height: number
  titulo: string
  /** Una sola frase referencial, sin guía de interpretación. */
  frase: string
  /** Crédito visible de la fuente. */
  credito: string
}

export const RADAR_IMAGENES: readonly RadarImagen[] = [
  {
    id: 'radar',
    src: '/radar/radar-rain-alarm-20261008.webp',
    alt: 'Captura de un mapa de radar de lluvia con manchas de colores y la leyenda de mm/h',
    width: 975,
    height: 720,
    titulo: 'Radar',
    frase: 'Muestra dónde llueve; los colores indican los mm/h (cada app usa su propia escala de colores).',
    credito:
      'Captura de Rain Alarm (Michael Diener, Software; Powered by Foreca). Datos de radar: Servicio Meteorológico Nacional (CC BY 2.5 AR, editados), REDEMET Brasil y NOAA.',
  },
  {
    id: 'satelite-visible',
    src: '/radar/satelite-visible-goes19-20261008.webp',
    alt: 'Imagen de satélite visible del sur de América del Sur, con las nubes en blanco',
    width: 1400,
    height: 840,
    titulo: 'Satélite visible',
    frase: 'Es como una foto desde el espacio: de día se ven los colores reales y las nubes se ven blancas.',
    credito: 'Imagen: NOAA/NESDIS/STAR, GOES-19 (GeoColor, color real de día), 8 de octubre de 2026, 18:20Z.',
  },
  {
    id: 'satelite-infrarrojo',
    src: '/radar/satelite-infrarrojo-goes19-20261008.webp',
    alt: 'Imagen de satélite infrarrojo del sur de América del Sur, con colores según la temperatura de las nubes',
    width: 1400,
    height: 840,
    titulo: 'Satélite infrarrojo',
    frase:
      'Mide la temperatura de lo que ve: en las nubes, cuanto más frías y altas, más color; funciona de día y de noche.',
    credito:
      'Imagen: NOAA/NESDIS/STAR, GOES-19 (Banda 13, infrarrojo limpio), 8 de octubre de 2026, 18:20Z.',
  },
]
