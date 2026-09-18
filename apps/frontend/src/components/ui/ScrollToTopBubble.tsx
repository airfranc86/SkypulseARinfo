import { useState, useEffect } from 'react'

const SIZE = 44
const MARGIN = 24

/**
 * ¿El rect pisa la esquina donde vive la burbuja? Un elemento marcado con
 * `data-scroll-bubble-guard` (p. ej. el resultado de Altitud de densidad) la
 * esconde mientras pasa por ahí, para no tapar valores alineados a la derecha.
 */
function overlapsBubble(rect: DOMRect): boolean {
  const left = window.innerWidth - MARGIN - SIZE
  const top = window.innerHeight - MARGIN - SIZE
  return rect.right > left && rect.left < left + SIZE && rect.bottom > top && rect.top < top + SIZE
}

export function ScrollToTopBubble() {
  const [visible, setVisible] = useState(false)
  const [blocked, setBlocked] = useState(false)

  useEffect(() => {
    let frame = 0

    const update = () => {
      frame = 0
      setVisible(window.scrollY > 300)
      const guard = document.querySelector('[data-scroll-bubble-guard]')
      setBlocked(guard ? overlapsBubble(guard.getBoundingClientRect()) : false)
    }

    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }

    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule, { passive: true })
    update()

    return () => {
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [])

  const shown = visible && !blocked

  const handleClick = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <button
      onClick={handleClick}
      aria-label="Volver al inicio"
      aria-hidden={shown ? undefined : true}
      tabIndex={shown ? undefined : -1}
      className="rounded-full"
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: 50,
        width: '44px',
        height: '44px',
        border: '1px solid var(--color-border)',
        background: 'color-mix(in srgb, var(--color-background) 80%, transparent)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        padding: 0,
        opacity: shown ? 1 : 0,
        transform: shown ? 'scale(1)' : 'scale(0.7)',
        pointerEvents: shown ? 'auto' : 'none',
        transition: 'opacity 200ms ease, transform 200ms ease, border-color 200ms ease, box-shadow 200ms ease',
      }}
      onMouseEnter={e => {
        const el = e.currentTarget
        el.style.transform = 'scale(1.08)'
        el.style.borderColor = 'var(--color-primary)'
        el.style.boxShadow = '0 4px 20px rgba(0,0,0,0.28)'
      }}
      onMouseLeave={e => {
        const el = e.currentTarget
        el.style.transform = shown ? 'scale(1)' : 'scale(0.7)'
        el.style.borderColor = 'var(--color-border)'
        el.style.boxShadow = '0 4px 16px rgba(0,0,0,0.18)'
      }}
    >
      <img
        src="/Logo.png"
        alt="SkyPulse"
        className="rounded-full"
        style={{
          width: '28px',
          height: '28px',
          objectFit: 'cover',
          display: 'block',
        }}
      />
    </button>
  )
}
