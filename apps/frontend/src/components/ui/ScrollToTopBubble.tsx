import { useState, useEffect } from 'react'

export function ScrollToTopBubble() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const handleScroll = () => {
      setVisible(window.scrollY > 300)
    }

    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const handleClick = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <button
      onClick={handleClick}
      aria-label="Volver al inicio"
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '24px',
        zIndex: 50,
        width: '44px',
        height: '44px',
        borderRadius: '50%',
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
        opacity: visible ? 1 : 0,
        transform: visible ? 'scale(1)' : 'scale(0.7)',
        pointerEvents: visible ? 'auto' : 'none',
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
        el.style.transform = visible ? 'scale(1)' : 'scale(0.7)'
        el.style.borderColor = 'var(--color-border)'
        el.style.boxShadow = '0 4px 16px rgba(0,0,0,0.18)'
      }}
    >
      <img
        src="/Logo.png"
        alt="SkyPulse"
        style={{
          width: '28px',
          height: '28px',
          borderRadius: '50%',
          objectFit: 'cover',
          display: 'block',
        }}
      />
    </button>
  )
}
