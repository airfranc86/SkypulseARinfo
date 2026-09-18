import { motion } from 'motion/react'

interface Props {
  reducedMotion: boolean
}

/** Campo de radar decorativo: retícula, barrido (CSS), dos pulsos y dos blancos (motion). */
export function RadarBackdrop({ reducedMotion }: Props) {
  return (
    <div className="nf-radar" aria-hidden="true">
      <div className="nf-crosshair" />
      <div className="nf-sweep" />
      <motion.div
        className="nf-pulse nf-pulse-one"
        animate={reducedMotion ? undefined : { opacity: [0.08, 0.28, 0.08], scale: [0.92, 1.08, 0.92] }}
        transition={reducedMotion ? undefined : { duration: 5.5, ease: 'easeInOut', repeat: Infinity }}
      />
      <motion.div
        className="nf-pulse nf-pulse-two"
        animate={reducedMotion ? undefined : { opacity: [0.04, 0.2, 0.04], scale: [0.9, 1.12, 0.9] }}
        transition={
          reducedMotion ? undefined : { duration: 6.5, delay: 1.4, ease: 'easeInOut', repeat: Infinity }
        }
      />
      <motion.span
        className="nf-target nf-target-one"
        animate={reducedMotion ? undefined : { opacity: [0.15, 0.85, 0.15], scale: [0.8, 1, 0.8] }}
        transition={reducedMotion ? undefined : { duration: 3.6, ease: 'easeInOut', repeat: Infinity }}
      />
      <motion.span
        className="nf-target nf-target-two"
        animate={reducedMotion ? undefined : { opacity: [0.08, 0.6, 0.08], scale: [0.7, 1, 0.7] }}
        transition={
          reducedMotion ? undefined : { duration: 4.4, delay: 0.7, ease: 'easeInOut', repeat: Infinity }
        }
      />
    </div>
  )
}
