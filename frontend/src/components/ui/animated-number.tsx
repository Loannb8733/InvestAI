import { useEffect } from 'react'
import { motion, useSpring, useTransform, useMotionValue } from 'framer-motion'

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
  const motionValue = useMotionValue(0)
  const spring = useSpring(motionValue, { stiffness: 50, damping: 15 })
  const display = useTransform(spring, (latest) => formatter(latest))

  useEffect(() => {
    motionValue.set(value)
  }, [value, motionValue])

  return <motion.span className={className}>{display}</motion.span>
}
