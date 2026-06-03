import { useRef, type ReactNode } from 'react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'

interface MotionCardProps {
  children: ReactNode
  className?: string
  disableHover?: boolean
}

const canHover =
  typeof window !== 'undefined' &&
  window.matchMedia('(hover: hover)').matches &&
  !window.matchMedia('(prefers-reduced-motion: reduce)').matches

export default function MotionCard({ children, className, disableHover = false }: MotionCardProps) {
  const ref = useRef<HTMLDivElement>(null)

  const rawX = useMotionValue(0)
  const rawY = useMotionValue(0)

  const springX = useSpring(rawX, { stiffness: 400, damping: 30 })
  const springY = useSpring(rawY, { stiffness: 400, damping: 30 })

  const rotateX = useTransform(springY, [-0.5, 0.5], [6, -6])
  const rotateY = useTransform(springX, [-0.5, 0.5], [-6, 6])

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!ref.current || !canHover || disableHover) return
    const rect = ref.current.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width - 0.5
    const y = (e.clientY - rect.top) / rect.height - 0.5
    rawX.set(x)
    rawY.set(y)
  }

  const handleMouseLeave = () => {
    rawX.set(0)
    rawY.set(0)
  }

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      whileTap={{ scale: 0.98 }}
      style={
        canHover && !disableHover
          ? { rotateX, rotateY, transformStyle: 'preserve-3d' }
          : undefined
      }
      whileHover={canHover && !disableHover ? { scale: 1.01 } : undefined}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className={className}
    >
      <div className="rounded-[inherit] border border-border bg-card h-full w-full">
        {children}
      </div>
    </motion.div>
  )
}
