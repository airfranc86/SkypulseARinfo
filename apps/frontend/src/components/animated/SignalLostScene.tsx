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
 * página". Un paraguas (geometría — arco + mango, sin figura humana: ver
 * craft-floor sobre por qué un stick-figure está prohibido) flota bajo la
 * lluvia mientras el radar hace ping buscando algo que no está. El ícono de
 * niebla es un asset real de Meteocons (gradiente/sombreado propio del
 * catálogo, no un boceto de líneas) — coherente con "perdido en la niebla".
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

      {/* Paraguas — geometría (arco + mango), sin persona debajo: el objeto
          quedó, lo que faltaba era la página. Balanceo sutil. */}
      <motion.g
        style={{ transformOrigin: '150px 70px' }}
        animate={reducedMotion ? undefined : { rotate: [-3, 3, -3] }}
        transition={reducedMotion ? undefined : { duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
      >
        <path d="M150 95 L150 130 Q150 140 160 140" stroke="var(--color-muted-foreground)" strokeWidth={3} fill="none" strokeLinecap="round" />
        <path d="M90 95 Q90 45 150 45 Q210 45 210 95 Z" fill="var(--color-primary)" opacity={0.9} />
        <path d="M110 95 Q110 60 150 55" stroke="var(--color-background)" strokeWidth={1.5} fill="none" opacity={0.35} />
        <path d="M150 95 L150 45" stroke="var(--color-background)" strokeWidth={1.5} fill="none" opacity={0.35} />
        <path d="M190 95 Q190 60 150 55" stroke="var(--color-background)" strokeWidth={1.5} fill="none" opacity={0.35} />
      </motion.g>
    </svg>
  )
}
