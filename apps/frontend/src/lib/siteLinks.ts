/**
 * Links shared by the footer and the "De dónde salen los datos" page: one place, so the credit,
 * the licence and the contribution link never drift apart. Pure constants (no React, no env).
 */

/** Open-Meteo home: credit link for the weather data (CC BY 4.0 asks for attribution). */
export const OPEN_METEO_URL = 'https://open-meteo.com/'

/** Open-Meteo licence page (CC BY 4.0). */
export const OPEN_METEO_LICENCE_URL = 'https://open-meteo.com/en/licence'

/** SMN (Servicio Meteorológico Nacional) home: credit link for the official alerts. */
export const SMN_URL = 'https://www.smn.gob.ar/'

/**
 * Legal text of CC BY 4.0: the licence the SMN open CAP feed declares for the official alerts in its own
 * copyright line (checked on the real feed, 2026-10-06). Other SMN open data may carry a different licence.
 */
export const CC_BY_4_URL = 'https://creativecommons.org/licenses/by/4.0/'

/** SIB (Sistema de Información de Biodiversidad, Parques Nacionales): where to learn about the species Mora is inspired by. */
export const SIB_URL = 'https://sib.gob.ar/'

/** Aves Argentinas (Asociación Ornitológica del Plata): its digital bird guide, for the same species. */
export const AVES_ARGENTINAS_URL = 'https://www.avesargentinas.org.ar/'

/** Voluntary contribution. It unlocks nothing: every feature is the same for everyone. */
export const CAFECITO_URL = 'https://cafecito.app/skypulse-ar'

/**
 * Official Cafecito button, exactly as Cafecito publishes it (images served from their CDN: the CSP
 * `img-src` in vercel.json must allow that origin). 1x, 2x and 3.75x for sharp screens.
 */
export const CAFECITO_BUTTON_SRC = 'https://cdn.cafecito.app/imgs/buttons/button_5.png'
export const CAFECITO_BUTTON_SRCSET = [
  'https://cdn.cafecito.app/imgs/buttons/button_5.png 1x',
  'https://cdn.cafecito.app/imgs/buttons/button_5_2x.png 2x',
  'https://cdn.cafecito.app/imgs/buttons/button_5_3.75x.png 3.75x',
].join(', ')
export const CAFECITO_BUTTON_ALT = 'Invitame un café en cafecito.app'
/** Intrinsic size (px) of the 1x image, so the layout does not shift while it loads. */
export const CAFECITO_BUTTON_WIDTH = 192
export const CAFECITO_BUTTON_HEIGHT = 40

/** Internal route of the page that explains where the data comes from. */
export const DATA_PAGE_PATH = '/datos'
