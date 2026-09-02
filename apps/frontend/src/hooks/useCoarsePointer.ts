import { useState, useEffect } from 'react'

function getCoarsePointer(): boolean {
  if (typeof window === 'undefined') return false
  return window.matchMedia('(pointer: coarse)').matches
}

/** true cuando el dispositivo de entrada principal es táctil (sin cursor persistente). */
export function useCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState<boolean>(getCoarsePointer)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const mediaQuery = window.matchMedia('(pointer: coarse)')
    const handleChange = (e: MediaQueryListEvent) => setCoarse(e.matches)
    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [])

  return coarse
}
