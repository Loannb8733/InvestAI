import { useEffect, useRef, useState } from 'react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'
import { cn } from '@/lib/utils'

/**
 * NumberTicker — chiffre financier vivant.
 *
 * Anime la valeur vers sa cible (spring), et « flashe » brièvement en
 * gain/perte quand la valeur bouge — le tick d'un terminal de marché.
 *
 * Accessibilité :
 * - le span animé est `aria-hidden` (le défilement serait du bruit pour un
 *   lecteur d'écran) ; la valeur finale est exposée dans un span visuellement
 *   masqué avec `aria-live="polite"` ;
 * - `prefers-reduced-motion` : rendu statique instantané, pas de flash.
 */

const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

interface NumberTickerProps {
  value: number
  /** Formateur d'affichage (ex: formatCurrency). Défaut: 2 décimales. */
  format?: (n: number) => string
  /** Flash coloré gain/perte quand la valeur change (défaut true). */
  flashOnChange?: boolean
  className?: string
}

export default function NumberTicker({
  value,
  format = (n) => n.toFixed(2),
  flashOnChange = true,
  className,
}: NumberTickerProps) {
  const isStatic = reducedMotion()
  const motionValue = useMotionValue(value)
  const spring = useSpring(motionValue, { stiffness: 80, damping: 20 })
  const display = useTransform(spring, (latest) => format(latest))

  const prev = useRef(value)
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)

  useEffect(() => {
    motionValue.set(value)
    if (flashOnChange && !isStatic && value !== prev.current) {
      setFlash(value > prev.current ? 'up' : 'down')
      const t = setTimeout(() => setFlash(null), 900)
      prev.current = value
      return () => clearTimeout(t)
    }
    prev.current = value
  }, [value, motionValue, flashOnChange, isStatic])

  if (isStatic) {
    return <span className={className}>{format(value)}</span>
  }

  return (
    <span className={cn('relative inline-block', className)}>
      <motion.span
        aria-hidden
        className={cn(
          'transition-colors duration-700',
          flash === 'up' && 'text-gain',
          flash === 'down' && 'text-loss'
        )}
      >
        {display}
      </motion.span>
      <span className="sr-only" aria-live="polite">
        {format(value)}
      </span>
    </span>
  )
}
