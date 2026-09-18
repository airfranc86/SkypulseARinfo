import { motion } from 'motion/react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

// Gotas: posición x + delay propio para que la lluvia no caiga toda en sincro.
const DROPS = [
  { x: 30,  delay: 0 },
  { x: 70,  delay: 0.5 },
  { x: 230, delay: 0.3 },
  { x: 270, delay: 1.0 },
  { x: 15,  delay: 1.3 },
  { x: 285, delay: 0.8 },
]

const DROP_DURATION = 1.7

// Anillos de radar: retoman la propia metáfora del producto (SkyPulse "buscando
// señal") en vez de una escena decorativa genérica — cada anillo se expande y
// se desvanece, como un ping de sonar que no encuentra la página.
const RINGS = [0, 0.9, 1.8]
const RING_DURATION = 2.7

/**
 * Escena decorativa de la 404: "el radar de SkyPulse perdió la señal de esta
 * página". Lluvia cayendo mientras el radar hace ping buscando algo que no
 * está.
 */
export function SignalLostScene() {
  const reducedMotion = useReducedMotion()

  return (
    <svg
      viewBox="0 0 300 220"
      width="220"
      height="161"
      aria-hidden="true"
      style={{ display: 'block' }}
    >
      {/* Radar ping — geometría pura, sin representar ninguna figura.
          Opacidad en keyframes explícitos (no un fade-out continuo): un
          ease-out entre 2 valores pasa la mayor parte del ciclo casi
          invisible, que es exactamente lo que pasaba antes de este ajuste. */}
      {!reducedMotion && RINGS.map((delay, i) => (
        <motion.circle
          key={i}
          cx={150}
          cy={110}
          r={12}
          fill="none"
          stroke="var(--color-info)"
          strokeWidth={2.5}
          initial={{ scale: 0.3, opacity: 0 }}
          animate={{ scale: [0.3, 2, 5], opacity: [0, 0.9, 0] }}
          transition={{
            duration: RING_DURATION,
            delay,
            repeat: Infinity,
            ease: 'easeOut',
            times: [0, 0.35, 1],
          }}
          style={{ transformOrigin: '150px 110px' }}
        />
      ))}
      {reducedMotion && (
        <circle cx={150} cy={110} r={30} fill="none" stroke="var(--color-info)" strokeWidth={1} opacity={0.25} />
      )}

      {/* Lluvia */}
      {!reducedMotion && DROPS.map((d, i) => (
        <motion.line
          key={i}
          x1={d.x}
          x2={d.x - 10}
          y1={-25}
          y2={5}
          stroke="var(--color-info)"
          strokeWidth={3}
          strokeLinecap="round"
          initial={{ y: 0, opacity: 0 }}
          animate={{ y: 250, opacity: [0, 0.95, 0.95, 0] }}
          transition={{
            duration: DROP_DURATION,
            delay: d.delay,
            repeat: Infinity,
            ease: 'linear',
          }}
        />
      ))}
    </svg>
  )
}
