/**
 * Links shared by the footer and the "De dónde salen los datos" page: one place, so the credit,
 * the licence and the contribution link never drift apart. Pure constants (no React, no env).
 */

/** Open-Meteo home: credit link for the weather data (CC BY 4.0 asks for attribution). */
export const OPEN_METEO_URL = 'https://open-meteo.com/'

/** Open-Meteo licence page (CC BY 4.0). */
export const OPEN_METEO_LICENCE_URL = 'https://open-meteo.com/en/licence'

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
