import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { counted } from '@/lib/utils'
import { apiClient } from '@/shared/api/client'
import { serverMessage } from '@/shared/api/errors'
import type { ApiKeyCreate, ApiKeyUpdate, TestResult } from './types'

type Toast = ReturnType<typeof useToast>['toast']

export const QUIET = { suppressGlobalError: true }

export function failureToast(toast: Toast, title: string, fallback: string) {
  return (error: unknown) => toast({ variant: 'destructive', title, description: serverMessage(error) || fallback })
}

export function useExchanges() {
  return useQuery({
    queryKey: queryKeys.exchanges.list,
    queryFn: () => apiClient.get('/api-keys/exchanges', { silent: true }),
    meta: QUIET,
  })
}

export function useApiKeys() {
  return useQuery({
    queryKey: queryKeys.apiKeys.list,
    queryFn: () => apiClient.get('/api-keys', { silent: true }),
    meta: QUIET,
  })
}

export function useCreateKey(onCreated: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ApiKeyCreate) => apiClient.post('/api-keys', { body, silent: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      onCreated()
      toast({ title: 'Clé API ajoutée', description: 'La clé API a été enregistrée avec succès.' })
    },
    onError: failureToast(toast, 'Erreur', "Impossible d'ajouter la clé API."),
  })
}

export function useDeleteKey() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete('/api-keys/{api_key_id}', { path: { api_key_id: id }, silent: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Clé API supprimée', description: 'La connexion a été supprimée avec succès.' })
    },
    onError: failureToast(toast, 'Erreur', 'Impossible de supprimer la clé API.'),
  })
}

export interface KeyChange {
  id: string
  data: ApiKeyUpdate
}

export function useUpdateKey(onSaved: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: KeyChange) =>
      apiClient.patch('/api-keys/{api_key_id}', { path: { api_key_id: id }, body: data, silent: true }),
    onSuccess: (_result, { data }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      onSaved()
      if (data.is_active === undefined) {
        toast({ title: 'Label mis à jour', description: 'La connexion a été renommée avec succès.' })
        return
      }
      toast({
        title: data.is_active ? 'Connexion activée' : 'Connexion désactivée',
        description: data.is_active
          ? 'La clé API sera de nouveau utilisée pour les synchronisations.'
          : 'La clé API ne sera plus utilisée pour les synchronisations.',
      })
    },
    onError: failureToast(toast, 'Erreur', 'Impossible de mettre à jour la clé API.'),
  })
}

export function useTestKey(onTested: (result: TestResult) => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.post('/api-keys/{api_key_id}/test', { path: { api_key_id: id }, silent: true }),
    onSuccess: (result) => {
      onTested(result)
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      if (result.success) toast({ title: 'Connexion réussie', description: result.message })
      else toast({ variant: 'destructive', title: 'Échec de connexion', description: result.message })
    },
    onError: failureToast(toast, 'Erreur', 'Erreur lors du test.'),
  })
}

export function useSyncKey() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.post('/api-keys/{api_key_id}/sync', { path: { api_key_id: id }, silent: true }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
      invalidateAllFinancialData(queryClient)
      toast({
        title: 'Synchronisation réussie',
        description: `${counted(result.synced_assets, 'actif synchronisé', 'actifs synchronisés')}.`,
      })
    },
    onError: failureToast(toast, 'Erreur de synchronisation', 'Impossible de synchroniser.'),
  })
}
