import { motion } from 'motion/react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

// Gotas: posición x + delay propio para que la lluvia no caiga toda en sincro.
const DROPS = [
  { x: 20,  delay: 0 },
  { x: 55,  delay: 0.4 },
  { x: 90,  delay: 0.9 },
  { x: 125, delay: 0.2 },
  { x: 160, delay: 0.7 },
  { x: 195, delay: 1.1 },
  { x: 230, delay: 0.5 },
  { x: 265, delay: 1.3 },
  { x: 40,  delay: 1.6 },
  { x: 210, delay: 1.8 },
]

const DROP_DURATION = 1.6

/** Escena decorativa: una persona bajo un paraguas, lluvia cayendo en loop. Puramente ambiental. */
export function RainyUmbrella() {
  const reducedMotion = useReducedMotion()

  return (
    <svg
      viewBox="0 0 300 220"
      width="220"
      height="161"
      aria-hidden="true"
      style={{ display: 'block' }}
    >
      {/* Lluvia — detrás de la persona. Trazo largo y grueso: una gota fina de
          14px se pierde a este tamaño de ícono; esto necesita leerse de un vistazo. */}
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

      {/* Persona + paraguas — balanceo sutil */}
      <motion.g
        style={{ transformOrigin: '150px 95px' }}
        animate={reducedMotion ? undefined : { rotate: [-3, 3, -3] }}
        transition={reducedMotion ? undefined : { duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
      >
        {/* Mango */}
        <path d="M150 95 L150 170 Q150 182 162 182" stroke="var(--color-muted-foreground)" strokeWidth={3} fill="none" strokeLinecap="round" />
        {/* Cúpula del paraguas */}
        <path
          d="M90 95 Q90 45 150 45 Q210 45 210 95 Z"
          fill="var(--color-primary)"
          opacity={0.9}
        />
        {/* Gajos del paraguas */}
        <path d="M110 95 Q110 60 150 55" stroke="var(--color-background)" strokeWidth={1.5} fill="none" opacity={0.35} />
        <path d="M150 95 L150 45" stroke="var(--color-background)" strokeWidth={1.5} fill="none" opacity={0.35} />
        <path d="M190 95 Q190 60 150 55" stroke="var(--color-background)" strokeWidth={1.5} fill="none" opacity={0.35} />

        {/* Cabeza */}
        <circle cx="150" cy="135" r="10" fill="var(--color-foreground)" opacity={0.85} />
        {/* Cuerpo */}
        <path d="M150 145 L150 190" stroke="var(--color-foreground)" strokeWidth={4} strokeLinecap="round" opacity={0.85} />
        {/* Piernas */}
        <path d="M150 190 L138 215" stroke="var(--color-foreground)" strokeWidth={4} strokeLinecap="round" opacity={0.85} />
        <path d="M150 190 L162 215" stroke="var(--color-foreground)" strokeWidth={4} strokeLinecap="round" opacity={0.85} />
      </motion.g>
    </svg>
  )
}
