/** The city search of the header (LocationPicker), found by its accessible name. */
const CITY_SEARCH_SELECTOR = 'header input[aria-label="Buscar ciudad"]'

/** "Cambiar ciudad": moves the focus to the header search, which is always on screen (sticky header). */
export function focusCitySearch(): void {
  document.querySelector<HTMLInputElement>(CITY_SEARCH_SELECTOR)?.focus()
}
