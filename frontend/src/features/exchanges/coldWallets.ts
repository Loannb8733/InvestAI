import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient, type Schema } from '@/shared/api/client'

export function useColdWallets() {
  return useQuery({ queryKey: queryKeys.coldWallets.list, queryFn: () => apiClient.get('/cold-wallets') })
}

export function useSaveColdWallet(onSaved: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Schema<'ColdWalletCreate'>) => apiClient.post('/cold-wallets', { body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.coldWallets.all })
      onSaved()
      toast({ title: 'Cold wallet enregistré', description: 'L’adresse a été associée à ce nom.' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible d’enregistrer ce cold wallet.' })
    },
  })
}

export function useDeleteColdWallet() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete('/cold-wallets/{wallet_id}', { path: { wallet_id: id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.coldWallets.all })
      toast({ title: 'Cold wallet supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer ce cold wallet.' })
    },
  })
}
