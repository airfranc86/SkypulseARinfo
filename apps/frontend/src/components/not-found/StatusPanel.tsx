import { motion } from 'motion/react'
import { TriangleAlert, WifiOff } from 'lucide-react'
import { revealContainer, revealItem } from './motionVariants'

interface Props {
  reducedMotion: boolean
}

const ICON_PULSE = {
  boxShadow: [
    '0 0 0 0 rgba(219, 121, 93, 0)',
    '0 0 0 8px rgba(219, 121, 93, 0.08)',
    '0 0 0 0 rgba(219, 121, 93, 0)',
  ],
}

/** Consola de enlace estilo terminal aeronáutico: señal perdida + telemetría en cero. */
export function StatusPanel({ reducedMotion }: Props) {
  return (
    <motion.aside className="nf-panel" aria-label="Estado de la estación" variants={revealItem}>
      <motion.div className="nf-panel-top" variants={revealItem}>
        <span className="nf-panel-label">Consola de enlace</span>
        <span className="nf-panel-id">ERR / 404</span>
      </motion.div>

      <motion.div className="nf-signal" role="status" aria-live="polite" variants={revealItem}>
        <motion.div
          className="nf-status-icon"
          aria-hidden="true"
          animate={reducedMotion ? undefined : ICON_PULSE}
          transition={reducedMotion ? undefined : { duration: 2.8, ease: 'easeOut', repeat: Infinity }}
        >
          <TriangleAlert />
        </motion.div>
        <div className="nf-signal-copy">
          <span className="nf-signal-title">Señal perdida</span>
          <span className="nf-signal-detail">
            <WifiOff aria-hidden="true" />
            No se recibe telemetría
          </span>
        </div>
      </motion.div>

      <motion.div className="nf-panel-rule" variants={revealItem} />

      <motion.div className="nf-telemetry" aria-label="Lecturas de telemetría" variants={revealContainer}>
        <motion.div className="nf-telemetry-row" variants={revealItem}>
          <span>Canal</span>
          <span className="nf-telemetry-value nf-offline">Desconectado</span>
        </motion.div>
        <motion.div className="nf-telemetry-row" variants={revealItem}>
          <span>Visibilidad</span>
          <span className="nf-telemetry-value">0.0 km</span>
        </motion.div>
        <motion.div className="nf-telemetry-row" variants={revealItem}>
          <span>Último pulso</span>
          <span className="nf-telemetry-value">— — : — —</span>
        </motion.div>
      </motion.div>

      <motion.div className="nf-panel-foot" variants={revealItem}>
        <span>
          <span className="nf-led-wrap" aria-hidden="true">
            <span className="nf-led-ping" />
            <span className="nf-led" />
          </span>
          Alerta activa
        </span>
        <span>SP / OPS</span>
      </motion.div>
    </motion.aside>
  )
}
