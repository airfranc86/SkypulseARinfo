import { useState, useEffect, type ReactNode, type ReactElement, type CSSProperties } from 'react'

interface FadeContentProps {
  children: ReactNode
  delay?: number
  className?: string
}

export function FadeContent({ children, delay = 0, className }: FadeContentProps): ReactElement {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(timer)
  }, [delay])

  const style: CSSProperties = {
    opacity: visible ? 1 : 0,
    transform: visible ? 'translateY(0)' : 'translateY(8px)',
    transition: 'opacity 0.4s ease, transform 0.4s ease',
  }

  return (
    <div style={style} className={className}>
      {children}
    </div>
  )
}
