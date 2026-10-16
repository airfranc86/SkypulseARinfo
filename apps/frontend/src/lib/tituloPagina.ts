/**
 * The rule behind `usePageTitle`, pure so `node --test` covers it: the tab title of a route.
 *
 * Routes that only exist behind a build flag (`rutasConBandera`, for now only Mora's review page) do not give themselves away
 * when the flag is off: the route is not registered (it falls through to the 404) and its tab gets the 404 title
 * too (owner decision D8).
 */

/** react-router ignores case and the trailing slash when it matches; the lookup must do the same. */
export function normalizarRuta(pathname: string): string {
  return pathname.toLowerCase().replace(/\/+$/, '') || '/'
}

export function tituloDeRuta(
  pathname: string,
  titulos: Readonly<Record<string, string>>,
  tituloNoEncontrado: string,
  rutasConBandera: ReadonlySet<string>,
  banderaEncendida: boolean,
): string {
  const ruta = normalizarRuta(pathname)
  if (rutasConBandera.has(ruta) && !banderaEncendida) return tituloNoEncontrado
  return titulos[ruta] ?? tituloNoEncontrado
}
