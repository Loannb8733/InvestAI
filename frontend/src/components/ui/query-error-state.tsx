import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/empty-state'

/**
 * QueryErrorState — ce qu'une page affiche quand sa requête a échoué.
 *
 * Sans lui, une `useQuery` en erreur ne rend rien : la page reste vide ou tourne
 * indéfiniment, et le `RouteErrorBoundary` ne la rattrape pas — une query qui
 * rejette ne lève pas d'exception pendant le rendu. L'utilisateur n'a alors aucun
 * moyen de savoir si la donnée est vide ou si l'API est tombée, ni comment réessayer.
 *
 * Enveloppe `EmptyState` (variante `error`, déjà en `role="alert"`) plutôt que de
 * refaire un composant concurrent : une seule apparence pour tous les états de page.
 *
 * ```tsx
 * const { data, isError, error, refetch, isFetching } = useQuery(...)
 * if (isError) return <QueryErrorState error={error} onRetry={refetch} busy={isFetching} />
 * ```
 */

interface QueryErrorStateProps {
  /** L'erreur remontée par React Query. Son message n'est affiché qu'en développement. */
  error?: unknown
  /** Typiquement le `refetch` de la query. Sans lui, aucun bouton n'est proposé. */
  onRetry?: () => void
  /** Grise le bouton pendant que la nouvelle tentative est en cours. */
  busy?: boolean
  /** Remplace le titre par défaut quand la page a un contexte plus précis. */
  title?: string
  /** Remplace la description par défaut. */
  description?: string
  className?: string
}

/** Message technique — affiché uniquement hors production. */
function detail(error: unknown): string | null {
  if (!import.meta.env.DEV) return null
  if (error instanceof Error) return error.message
  return typeof error === 'string' ? error : null
}

export default function QueryErrorState({
  error,
  onRetry,
  busy = false,
  title = 'Impossible de charger ces données',
  description,
  className,
}: QueryErrorStateProps) {
  const technique = detail(error)

  return (
    <EmptyState
      variant="error"
      icon={AlertTriangle}
      title={title}
      description={
        description ??
        (technique
          ? `La requête a échoué : ${technique}`
          : 'La requête n’a pas abouti. Vérifiez votre connexion, puis réessayez.')
      }
      action={
        onRetry ? (
          <Button variant="outline" size="sm" onClick={onRetry} disabled={busy}>
            {busy ? 'Nouvelle tentative…' : 'Réessayer'}
          </Button>
        ) : undefined
      }
      className={className}
    />
  )
}
