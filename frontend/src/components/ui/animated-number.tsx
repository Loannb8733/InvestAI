import { useEffect } from 'react'
import { motion, useReducedMotion, useSpring, useTransform, useMotionValue } from 'framer-motion'

interface AnimatedNumberProps {
  value: number
  formatter?: (n: number) => string
  className?: string
}

export default function AnimatedNumber({
  value,
  formatter = (n) => n.toFixed(2),
  className,
}: AnimatedNumberProps) {
  // La media query CSS globale ne couvre pas ce cas : framer-motion pilote la
  // valeur en JS, sans animation ni transition CSS à neutraliser. Le compteur
  // continuait donc à défiler de 0 jusqu'au montant, préférence système ignorée
  // (A11Y-02). `useReducedMotion` est réactif, contrairement à un matchMedia lu
  // une fois au montage.
  const reduceMotion = useReducedMotion()

  const motionValue = useMotionValue(0)
  const spring = useSpring(motionValue, { stiffness: 50, damping: 15 })
  const display = useTransform(spring, (latest) => formatter(latest))

  useEffect(() => {
    motionValue.set(value)
  }, [value, motionValue])

  if (reduceMotion) {
    return <span className={className}>{formatter(value)}</span>
  }

  return <motion.span className={className}>{display}</motion.span>
}
