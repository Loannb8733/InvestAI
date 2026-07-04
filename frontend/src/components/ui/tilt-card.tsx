import { useCallback, useRef, type ReactNode } from 'react'
import { motion, useMotionTemplate, useMotionValue, useSpring, useTransform } from 'framer-motion'
import { cn } from '@/lib/utils'

/**
 * TiltCard — surface 3D vivante.
 *
 * Incline la carte vers le pointeur (perspective réelle, springs), avec un
 * reflet spéculaire qui suit le curseur. Le relief repose sur le système
 * d'élévation (`elev-*`) : l'ombre s'intensifie quand la carte « se lève ».
 *
 * Accessibilité & robustesse :
 * - inerte sur écrans tactiles (`hover: none`) et si `prefers-reduced-motion` ;
 * - la profondeur reste perceptible sans mouvement (élévation statique) ;
 * - conteneur passif : aucune sémantique interactive n'est ajoutée ici.
 */

const canTilt = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(hover: hover)').matches &&
  !window.matchMedia('(prefers-reduced-motion: reduce)').matches

interface TiltCardProps {
  children: ReactNode
  className?: string
  /** Inclinaison max en degrés (défaut 5 — subtil, financier, pas gadget). */
  intensity?: number
  /** Reflet spéculaire qui suit le pointeur (défaut true). */
  glare?: boolean
  /** Désactive tout mouvement (la carte reste une surface élevée statique). */
  static?: boolean
}

export default function TiltCard({
  children,
  className,
  intensity = 5,
  glare = true,
  static: isStatic = false,
}: TiltCardProps) {
  const ref = useRef<HTMLDivElement>(null)
  const enabled = !isStatic && canTilt()

  const rawX = useMotionValue(0)
  const rawY = useMotionValue(0)
  const springX = useSpring(rawX, { stiffness: 300, damping: 28 })
  const springY = useSpring(rawY, { stiffness: 300, damping: 28 })
  const rotateX = useTransform(springY, [-0.5, 0.5], [intensity, -intensity])
  const rotateY = useTransform(springX, [-0.5, 0.5], [-intensity, intensity])
  // Reflet spéculaire : position en % qui suit le pointeur
  const glareX = useTransform(springX, [-0.5, 0.5], [20, 80])
  const glareY = useTransform(springY, [-0.5, 0.5], [15, 85])
  const glareBackground = useMotionTemplate`radial-gradient(320px circle at ${glareX}% ${glareY}%, oklch(1 0 0 / 0.06), transparent 70%)`

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!ref.current || !enabled) return
      const rect = ref.current.getBoundingClientRect()
      rawX.set((e.clientX - rect.left) / rect.width - 0.5)
      rawY.set((e.clientY - rect.top) / rect.height - 0.5)
    },
    [enabled, rawX, rawY]
  )

  const handlePointerLeave = useCallback(() => {
    rawX.set(0)
    rawY.set(0)
  }, [rawX, rawY])

  return (
    <div style={enabled ? { perspective: 900 } : undefined} className="h-full">
      <motion.div
        ref={ref}
        onPointerMove={enabled ? handlePointerMove : undefined}
        onPointerLeave={enabled ? handlePointerLeave : undefined}
        style={enabled ? { rotateX, rotateY, transformStyle: 'preserve-3d' } : undefined}
        className={cn(
          'group relative h-full rounded-lg border border-border bg-card text-card-foreground elev-1',
          enabled && 'transition-shadow duration-300 hover:elev-2',
          className
        )}
      >
        {children}
        {glare && enabled && (
          <motion.div
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
            style={{ background: glareBackground }}
          />
        )}
      </motion.div>
    </div>
  )
}
