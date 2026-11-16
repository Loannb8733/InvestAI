import { QueryCache, QueryClient } from '@tanstack/react-query'

import { toast } from '@/hooks/use-toast'

const FIVE_MINUTES_MS = 5 * 60 * 1000

export function createQueryClient(retry: number | false = 1) {
  return new QueryClient({
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
        staleTime: FIVE_MINUTES_MS,
        retry,
      },
    },
  })
}

export const queryClient = createQueryClient()
