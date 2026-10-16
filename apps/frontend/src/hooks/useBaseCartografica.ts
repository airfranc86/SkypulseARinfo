import { useQuery } from '@tanstack/react-query'
import { cargarBase, type BaseCartografica } from '@/lib/mapa/base'

/**
 * The map's background (coastlines and borders), loaded once from the site's own origin. It never changes while the
 * page is open, so it is cached for good. If it cannot be loaded the map is drawn without it: it is a help to find
 * your way, not data, so a failure here must not show an error.
 */
export function useBaseCartografica(): { base: BaseCartografica | null } {
  const query = useQuery({
    queryKey: ['mapa', 'base'],
    queryFn: () => cargarBase((url) => fetch(url)),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  })
  return { base: query.data ?? null }
}
