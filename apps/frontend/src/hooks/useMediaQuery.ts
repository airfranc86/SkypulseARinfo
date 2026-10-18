import { useSyncExternalStore } from 'react'

/**
 * Whether a CSS media query matches, and it follows the changes (a phone turned sideways, a window resized, the zoom).
 * It reads the browser through `useSyncExternalStore`, so there is no state to keep in step with an effect. Without
 * `matchMedia` (a server render) it says `false`.
 */
export function useMediaQuery(consulta: string): boolean {
  return useSyncExternalStore(
    (avisar) => {
      const medio = window.matchMedia(consulta)
      medio.addEventListener('change', avisar)
      return () => medio.removeEventListener('change', avisar)
    },
    () => window.matchMedia(consulta).matches,
    () => false,
  )
}
