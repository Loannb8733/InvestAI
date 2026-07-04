import { type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, Inbox, SearchX, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * EmptyState — l'état vide comme un moment soigné, pas un trou dans la page.
 *
 * Trois variantes sémantiques :
 * - `empty`  (role="status")  : pas encore de données — invite à l'action ;
 * - `search` (role="status")  : aucun résultat pour ce filtre ;
 * - `error`  (role="alert")   : le chargement a échoué — propose de réessayer.
 *
 * L'icône flotte doucement (désactivé sous prefers-reduced-motion via la
 * variante `initial` identique) pour garder la surface vivante sans distraire.
 */

const reducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

const DEFAULT_ICONS: Record<EmptyStateVariant, LucideIcon> = {
  empty: Inbox,
  search: SearchX,
  error: AlertTriangle,
}

type EmptyStateVariant = 'empty' | 'search' | 'error'

interface EmptyStateProps {
  variant?: EmptyStateVariant
  /** Icône Lucide custom (sinon icône par défaut de la variante). */
  icon?: LucideIcon
  title: string
  description?: string
  /** Slot d'action (bouton « Ajouter », « Réessayer »…). */
  action?: ReactNode
  className?: string
}

export default function EmptyState({
  variant = 'empty',
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  const Icon = icon ?? DEFAULT_ICONS[variant]
  const float = !reducedMotion()

  return (
    <div
      role={variant === 'error' ? 'alert' : 'status'}
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-12 text-center',
        className
      )}
    >
      <motion.div
        aria-hidden
        animate={float ? { y: [0, -6, 0] } : undefined}
        transition={float ? { duration: 4, repeat: Infinity, ease: 'easeInOut' } : undefined}
        className={cn(
          'flex h-12 w-12 items-center justify-center rounded-full elev-1',
          variant === 'error' ? 'bg-loss/10 text-loss' : 'bg-muted text-muted-foreground'
        )}
      >
        <Icon className="h-6 w-6" />
      </motion.div>
      <div className="space-y-1">
        <p className="font-serif text-lg font-medium">{title}</p>
        {description && (
          <p className="mx-auto max-w-sm text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
