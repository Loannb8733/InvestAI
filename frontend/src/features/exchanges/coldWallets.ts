import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient, type Schema } from '@/shared/api/client'
import { failureToast, QUIET } from './hooks'

export function useColdWallets() {
  return useQuery({
    queryKey: queryKeys.coldWallets.list,
    queryFn: () => apiClient.get('/cold-wallets', { silent: true }),
    meta: QUIET,
  })
}

export function useSaveColdWallet(onSaved: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Schema<'ColdWalletCreate'>) => apiClient.post('/cold-wallets', { body, silent: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.coldWallets.all })
      onSaved()
      toast({ title: 'Cold wallet enregistré', description: 'L’adresse a été associée à ce nom.' })
    },
    onError: failureToast(toast, 'Erreur', 'Impossible d’enregistrer ce cold wallet.'),
  })
}

export function useDeleteColdWallet() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete('/cold-wallets/{wallet_id}', { path: { wallet_id: id }, silent: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.coldWallets.all })
      toast({ title: 'Cold wallet supprimé' })
    },
    onError: failureToast(toast, 'Erreur', 'Impossible de supprimer ce cold wallet.'),
  })
}
