import { motion } from 'motion/react'
import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { RadarBackdrop } from '@/components/not-found/RadarBackdrop'
import { StatusPanel } from '@/components/not-found/StatusPanel'
import { revealContainer, revealItem } from '@/components/not-found/motionVariants'
import '@/components/not-found/notFound.css'

const SUGGESTIONS = [
  { to: '/prevision', label: 'Previsión' },
  { to: '/terremotos', label: 'Terremotos' },
  { to: '/nubes', label: 'Nubes' },
]

/** 404 "Visibilidad Nula" — diseño refinado en Replit (FRA-168) y portado a los tokens de SkyPulse. */
export function NotFound() {
  const reducedMotion = useReducedMotion()
  const initial = reducedMotion ? false : 'hidden'

  return (
    <section
      className="nf-station"
      data-motion={reducedMotion ? 'reduced' : 'full'}
      aria-labelledby="nf-title"
    >
      <motion.div
        className="nf-header"
        aria-hidden="true"
        initial={reducedMotion ? false : { opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: 'easeOut' }}
      >
        Modo monitoreo / Nocturno
      </motion.div>

      <div className="nf-glow" aria-hidden="true" />
      <RadarBackdrop reducedMotion={reducedMotion} />

      <div className="nf-content">
        <motion.div className="nf-hero" initial={initial} animate="visible" variants={revealContainer}>
          <motion.div variants={revealItem}>
            <motion.p
              className="nf-code"
              animate={reducedMotion ? undefined : { opacity: [0.15, 0.35, 0.15] }}
              transition={reducedMotion ? undefined : { duration: 3, ease: 'easeInOut', repeat: Infinity }}
            >
              404
            </motion.p>
          </motion.div>
          <motion.p className="nf-eyebrow" variants={revealItem}>
            Reporte fuera de cobertura
          </motion.p>
          <motion.h1 className="nf-title" id="nf-title" variants={revealItem}>
            Visibilidad Nula
          </motion.h1>
          <motion.p className="nf-description" variants={revealItem}>
            El reporte meteorológico que buscas está fuera de nuestro radar o la señal se ha perdido en la
            tormenta.
          </motion.p>

          <motion.div className="nf-actions" variants={revealItem}>
            <motion.div
              whileHover={reducedMotion ? undefined : { scale: 1.03 }}
              whileTap={reducedMotion ? undefined : { scale: 0.97 }}
            >
              <Link to="/" className="nf-return">
                <ArrowLeft aria-hidden="true" />
                <span>Volver a la Base</span>
              </Link>
            </motion.div>

            <nav className="nf-suggest" aria-label="Otras secciones">
              <span>Probá también:</span>
              {SUGGESTIONS.map(s => (
                <Link key={s.to} to={s.to}>
                  {s.label}
                </Link>
              ))}
            </nav>
          </motion.div>
        </motion.div>

        <motion.div initial={initial} animate="visible" variants={revealContainer}>
          <StatusPanel reducedMotion={reducedMotion} />
        </motion.div>
      </div>

      <motion.div
        className="nf-footer"
        aria-hidden="true"
        initial={reducedMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1, delay: reducedMotion ? 0 : 0.7 }}
      >
        <span>Estación meteorológica</span>
        <span>Protocolo de contingencia 04</span>
      </motion.div>
    </section>
  )
}
