import { useState, useEffect, type ReactNode, type ReactElement, type CSSProperties } from 'react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

interface FadeContentProps {
  children: ReactNode
  delay?: number
  className?: string
}

export function FadeContent({ children, delay = 0, className }: FadeContentProps): ReactElement {
  const [visible, setVisible] = useState(false)
  const reducedMotion = useReducedMotion()

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(timer)
  }, [delay])

  // Con movimiento reducido el contenido aparece sin desplazamiento ni transición.
  const style: CSSProperties = {
    opacity: visible ? 1 : 0,
    // `none` y no `translateY(0)`: cualquier transform, aunque sea identidad, vuelve a este div el bloque
    // contenedor de los descendientes con position:fixed.
    transform: visible || reducedMotion ? 'none' : 'translateY(8px)',
    transition: reducedMotion ? 'none' : 'opacity 0.4s ease, transform 0.4s ease',
  }

  return (
    <div style={style} className={className}>
      {children}
    </div>
  )
}
