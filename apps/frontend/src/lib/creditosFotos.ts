/**
 * Credits of the 23 photos hosted by the site (`public/fotos/<id>.webp`): the 13 clouds of /nubes and
 * the 10 cards of /desastres. This list is the single source of truth for authors, licences and sources;
 * the pages and the "Fotos" section of /datos read from here. Pure data (no React, no import.meta.env).
 */

export interface LicenciaFoto {
  nombre: string
  /** Legal text of the licence. Public domain photos have none. */
  url?: string
}

export interface FuenteFoto {
  nombre: string
  url: string
}

export interface CreditoFoto {
  /** File name without extension: `/fotos/<id>.webp`. Same as the cloud id or the Desastres card id. */
  id: string
  /** Name shown at the start of the credit line. */
  tema: string
  autor: string
  licencia: LicenciaFoto
  fuente: FuenteFoto
  /**
   * The photo differs from the original: scaled down, converted to WebP and cropped by the card frame.
   * CC BY and CC BY-SA ask to indicate changes, so those photos always carry it (see `TEXTO_CAMBIOS`).
   */
  redimensionada: boolean
}

/** Notice printed after the credit of a photo that was changed (the pages and `textoCredito` share it). */
export const TEXTO_CAMBIOS = 'redimensionada y recortada'

const CC0: LicenciaFoto = { nombre: 'CC0', url: 'https://creativecommons.org/publicdomain/zero/1.0/' }
const DOMINIO_PUBLICO: LicenciaFoto = { nombre: 'Dominio público' }
const DOMINIO_PUBLICO_LIBERADA: LicenciaFoto = { nombre: 'Dominio público (liberada por el autor)' }

function ccBy(version: '2.0' | '3.0' | '4.0'): LicenciaFoto {
  return { nombre: `CC BY ${version}`, url: `https://creativecommons.org/licenses/by/${version}/` }
}

function ccBySa(version: '2.0' | '3.0' | '4.0'): LicenciaFoto {
  return { nombre: `CC BY-SA ${version}`, url: `https://creativecommons.org/licenses/by-sa/${version}/` }
}

/** Page of a file on Wikimedia Commons. Only what a URL needs is encoded: parentheses and commas stay readable. */
function commons(archivo: string): FuenteFoto {
  return { nombre: 'Wikimedia Commons', url: `https://commons.wikimedia.org/wiki/File:${encodeURI(archivo)}` }
}

const flickr = (url: string): FuenteFoto => ({ nombre: 'Flickr', url })
const pixabay = (url: string): FuenteFoto => ({ nombre: 'Pixabay', url })

export const CREDITOS_FOTOS: readonly CreditoFoto[] = [
  // Clouds
  { id: 'cirros', tema: 'Cirros', autor: 'Dimitry B. (ru_boff)', licencia: ccBy('2.0'), fuente: flickr('https://www.flickr.com/photos/ru_boff/8690313402/'), redimensionada: true },
  { id: 'cirrostratos', tema: 'Cirrostratos', autor: 'jingoba', licencia: CC0, fuente: pixabay('https://pixabay.com/photos/cirrostratus-246295/'), redimensionada: false },
  { id: 'cirrocumulos', tema: 'Cirrocúmulos', autor: 'Typhoonchaser', licencia: ccBySa('3.0'), fuente: commons('Cirrocumulus_in_Hong_Kong.jpg'), redimensionada: true },
  { id: 'altocumulos', tema: 'Altocúmulos', autor: 'MabelAmber', licencia: CC0, fuente: pixabay('https://pixabay.com/photos/sky-1430070/'), redimensionada: false },
  { id: 'altostratos', tema: 'Altostratos', autor: 'W.carter', licencia: CC0, fuente: commons('Altostratus_with_stratocumulus_under_2.jpg'), redimensionada: false },
  { id: 'estrato', tema: 'Estrato', autor: 'Rollcloud', licencia: ccBy('3.0'), fuente: commons('Stratus_nebulosus_opacus_and_Stratus_fractus_(14122021).jpg'), redimensionada: true },
  { id: 'estratocumulos', tema: 'Estratocúmulos', autor: 'sarangib', licencia: CC0, fuente: pixabay('https://pixabay.com/photos/palm-trees-266438/'), redimensionada: false },
  { id: 'nimboestrato', tema: 'Nimboestrato', autor: 'Jacek Halicki', licencia: ccBySa('3.0'), fuente: commons('2014_Nimbostratus_rekadr.jpg'), redimensionada: true },
  { id: 'cumulo', tema: 'Cúmulo', autor: 'Medium69 (William Crochot)', licencia: ccBySa('4.0'), fuente: commons('Cumulus_humilis_-_39.jpg'), redimensionada: true },
  { id: 'cumulonimbo', tema: 'Cumulonimbo', autor: 'Jakub Hałun', licencia: ccBy('4.0'), fuente: commons('Chmura_burzowa_na_wschód_od_Krakowa,_20250904_1851_4432.jpg'), redimensionada: true },
  { id: 'lenticular', tema: 'Lenticular', autor: 'NOAA Earth System Research Laboratory', licencia: DOMINIO_PUBLICO, fuente: commons('Lenticular_clouds_in_Boulder_CO_-_NOAA_Earth_System_Research_Laboratory.jpg'), redimensionada: false },
  { id: 'mammatus', tema: 'Mammatus', autor: 'Cbaile19', licencia: CC0, fuente: commons('Mammatus_clouds,_Pittsburgh,_2022-06-16,_02.jpg'), redimensionada: false },
  { id: 'niebla', tema: 'Niebla', autor: 'Jay Huang', licencia: ccBy('2.0'), fuente: commons('Beautiful_sunrise_over_Pleasanton_valley.jpg'), redimensionada: true },
  // Natural disasters
  { id: 'terremotos', tema: 'Terremotos', autor: 'USGS', licencia: CC0, fuente: commons('2010_Haiti_Earthquake_(After).jpg'), redimensionada: true },
  { id: 'inundaciones', tema: 'Inundaciones', autor: 'Flocci Nivis', licencia: ccBy('4.0'), fuente: commons('20240517_Flood_Saarland_07.jpg'), redimensionada: true },
  { id: 'tornados', tema: 'Tornado F5 en Elie, Manitoba (2007)', autor: 'Justin Hobson (Justin1569)', licencia: ccBySa('3.0'), fuente: commons('F5_tornado_Elie_Manitoba_2007.jpg'), redimensionada: true },
  { id: 'huracanes', tema: 'Huracanes', autor: 'Mike Trenchard, NASA JSC (ISS007-E-14750)', licencia: DOMINIO_PUBLICO, fuente: commons('Hurricane_Isabel_from_ISS.jpg'), redimensionada: false },
  { id: 'incendios', tema: 'Incendios', autor: 'John McColgan (US Forest Service), edición Fir0002', licencia: DOMINIO_PUBLICO, fuente: commons('Deerfire_high_res_edit.jpg'), redimensionada: false },
  { id: 'tsunamis', tema: 'Tsunamis', autor: 'Sofwathulla Mohamed', licencia: DOMINIO_PUBLICO_LIBERADA, fuente: commons('2004_Indian_Ocean_earthquake_Maldives_tsunami_wave.jpg'), redimensionada: false },
  { id: 'micro-tsunamis', tema: 'Micro-tsunamis', autor: 'NOAA GLERL / L.S. Gerstner', licencia: ccBySa('2.0'), fuente: commons('High_waves_in_Lake_Michigan_along_the_Chicago_shoreline_(16807304806).jpg'), redimensionada: true },
  { id: 'ola-de-calor', tema: 'Ola de calor', autor: 'Christopher Michel', licencia: ccBy('2.0'), fuente: commons('Ladakh,_India_(14687115252).jpg'), redimensionada: true },
  { id: 'granizo-severo', tema: 'Granizo severo', autor: 'NOAA/NSSL', licencia: DOMINIO_PUBLICO, fuente: commons('Granizo.jpg'), redimensionada: false },
  { id: 'erupcion-volcanica', tema: 'Erupción volcánica', autor: 'FEMA / Kelly Hudson (NARA vía DPLA)', licencia: DOMINIO_PUBLICO, fuente: commons('Close_u_of_red_hot_lava_flowing_on_a_dirt_road,_a_result_of_the_Kilauea_Volcano_eruption_and_lava_flow_in_2014._-_DPLA_-_ced6ae979602bcc6905f497b87d35e8f.JPG'), redimensionada: false },
]

/** Photos under CC BY-SA: they are shared under the same licence (the "Fotos" section of /datos lists them). */
export const FOTOS_COMPARTIR_IGUAL: readonly CreditoFoto[] = CREDITOS_FOTOS.filter(c => c.licencia.nombre.startsWith('CC BY-SA'))

/** Credit of one photo by id. Throws if there is none: a photo without credit must not be shown. */
export function creditoDe(id: string): CreditoFoto {
  const credito = CREDITOS_FOTOS.find(c => c.id === id)
  if (!credito) throw new Error(`Foto sin crédito: ${id}`)
  return credito
}

/** Plain-text credit line: "<tema>: <autor>, <licencia>, <fuente>[, redimensionada y recortada]". */
export function textoCredito(credito: CreditoFoto): string {
  const partes = [credito.autor, credito.licencia.nombre, credito.fuente.nombre]
  if (credito.redimensionada) partes.push(TEXTO_CAMBIOS)
  return `${credito.tema}: ${partes.join(', ')}`
}
