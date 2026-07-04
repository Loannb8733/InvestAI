import { useCallback, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * SpotlightGroup — halo lumineux qui suit le pointeur sur une grille de cartes.
 *
 * Un seul listener sur le conteneur met à jour `--mx/--my` ; chaque enfant
 * portant la classe `spot-card` peint son dégradé radial via CSS pur
 * (voir index.css). Coût constant quel que soit le nombre de cartes.
 * Inerte au clavier/tactile et sans effet sous prefers-reduced-motion
 * (l'opacité du halo reste alors pilotée par :hover, jamais déclenchée).
 */

interface SpotlightGroupProps {
  children: ReactNode
  className?: string
}

export default function SpotlightGroup({ children, className }: SpotlightGroupProps) {
  const ref = useRef<HTMLDivElement>(null)

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const el = ref.current
    if (!el) return
    // Coordonnées locales à CHAQUE carte : on propage la position absolue du
    // pointeur et chaque .spot-card la convertit via sa propre bounding box.
    for (const card of el.querySelectorAll<HTMLElement>('.spot-card')) {
      const rect = card.getBoundingClientRect()
      card.style.setProperty('--mx', `${e.clientX - rect.left}px`)
      card.style.setProperty('--my', `${e.clientY - rect.top}px`)
    }
  }, [])

  return (
    <div
      ref={ref}
      onPointerMove={handlePointerMove}
      className={cn('spotlight-group', className)}
    >
      {children}
    </div>
  )
}
