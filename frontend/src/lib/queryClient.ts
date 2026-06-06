import { QueryCache, QueryClient } from '@tanstack/react-query'

import { toast } from '@/hooks/use-toast'

/**
 * Singleton TanStack Query client.
 *
 * Exported so non-React modules (e.g. the Zustand auth store) can wipe the
 * cache on logout — otherwise a logout leaves the previous user's portfolio,
 * transactions and analytics queries cached and visible to whoever logs in next
 * in the same tab.
 *
 * Pages with bespoke error UI opt out of the global error toast by setting
 * `meta: { suppressGlobalError: true }` on their query.
 */
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (_error, query) => {
      if (query.meta?.suppressGlobalError) return
      toast({
        variant: 'destructive',
        title: 'Erreur de chargement',
        description: 'Impossible de récupérer les données. Vérifiez votre connexion et réessayez.',
      })
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
})
