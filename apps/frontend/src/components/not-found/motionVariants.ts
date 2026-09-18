import type { Variants } from 'motion/react'

export const revealContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { delayChildren: 0.08, staggerChildren: 0.1 },
  },
}

export const revealItem: Variants = {
  hidden: { opacity: 0, y: 16, filter: 'blur(7px)' },
  visible: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: 0.58, ease: 'easeOut' },
  },
}
