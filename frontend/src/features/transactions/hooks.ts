import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient } from '@/shared/api/client'
import { serverMessage } from '@/shared/api/errors'
import { http } from '@/shared/api/http'
import { counted } from './format'
import type { AssetCreate, CsvImportResult, ServerFilters, TransactionCreate, TransactionPage, TransactionUpdate } from './types'

export const TX_PAGE_SIZE = 200

export function useTransactionPage(filters: ServerFilters, skip: number) {
  return useQuery({
    queryKey: [...queryKeys.transactions.list(filters.portfolio_id), filters, skip],
    queryFn: async (): Promise<TransactionPage> => {
      const page = await apiClient.get('/transactions', {
        query: { ...filters, skip, limit: TX_PAGE_SIZE, include_total: true },
        silent: true,
      })
      return Array.isArray(page) ? { items: page, total: page.length } : page
    },
    placeholderData: keepPreviousData,
    meta: { suppressGlobalError: true },
  })
}

export function useCsvPlatforms() {
  return useQuery({
    queryKey: queryKeys.transactions.csvPlatforms,
    queryFn: () => apiClient.get('/transactions/csv-platforms'),
    staleTime: 10 * 60_000,
  })
}

export function useUserPlatforms() {
  return useQuery({
    queryKey: queryKeys.platforms.user,
    queryFn: () => apiClient.get('/transactions/platforms'),
    staleTime: 60_000,
  })
}

export async function fetchTransactionsCsv(portfolioId?: string): Promise<Blob> {
  const response = await http.get<Blob>('/transactions/export-csv', {
    params: portfolioId ? { portfolio_id: portfolioId } : {},
    responseType: 'blob',
    silent: true,
  })
  return response.data
}

interface CsvImport {
  file: File
  portfolioId?: string
  platform?: string
  destinationExchange?: string
}

async function importCsv({ file, portfolioId, platform, destinationExchange }: CsvImport) {
  const formData = new FormData()
  formData.append('file', file)
  const params: Record<string, string> = {}
  if (portfolioId) params.portfolio_id = portfolioId
  if (platform) params.platform = platform
  if (destinationExchange) params.destination_exchange = destinationExchange
  const response = await http.post<CsvImportResult>('/transactions/import-csv', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params,
    silent: true,
  })
  return response.data
}

export function useImportCsv(onImported: (result: CsvImportResult) => void, onFailed: (error: unknown) => void) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: importCsv,
    onSuccess: (result) => {
      invalidateAllFinancialData(queryClient)
      onImported(result)
    },
    onError: onFailed,
  })
}

const deleteOne = (id: string) =>
  apiClient.delete('/transactions/{transaction_id}', { path: { transaction_id: id }, silent: true })

function useLedgerMutation<T, R>(mutationFn: (variables: T) => Promise<R>, onDone: (result: R) => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (result) => {
      invalidateAllFinancialData(queryClient)
      onDone(result)
    },
    onError: () => {
      toast({ title: 'Erreur lors de la suppression', variant: 'destructive' })
    },
  })
}

export function useDeleteTransaction(onDeleted: () => void) {
  const { toast } = useToast()
  return useLedgerMutation(deleteOne, () => {
    toast({ title: 'Transaction supprimée' })
    onDeleted()
  })
}

async function deleteMany(ids: string[]) {
  let deleted = 0
  const errors: string[] = []
  for (const id of ids) {
    try {
      await deleteOne(id)
      deleted++
    } catch {
      errors.push(id)
    }
  }
  return { deleted, errors }
}

export function useDeleteSelected(onDeleted: () => void) {
  const { toast } = useToast()
  return useLedgerMutation(deleteMany, ({ deleted, errors }) => {
    if (errors.length > 0) {
      toast({
        title: `${counted(deleted, 'supprimée', 'supprimées')}, ${counted(errors.length, 'erreur', 'erreurs')}`,
        variant: 'destructive',
      })
    } else {
      toast({ title: counted(deleted, 'transaction supprimée', 'transactions supprimées') })
    }
    onDeleted()
  })
}

export function useDeleteAll(portfolioId: string | undefined) {
  const { toast } = useToast()
  return useLedgerMutation(
    () => apiClient.delete('/transactions/all', { query: portfolioId ? { portfolio_id: portfolioId } : undefined, silent: true }),
    (result) => toast({ title: counted(result.deleted_count, 'transaction supprimée', 'transactions supprimées') })
  )
}

export function useUpdateTransaction(id: string | undefined, onSaved: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TransactionUpdate) =>
      apiClient.patch('/transactions/{transaction_id}', { path: { transaction_id: id ?? '' }, body, silent: true }),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Transaction mise à jour' })
      onSaved()
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de mettre à jour la transaction' })
    },
  })
}

export function useCreateTransaction(onCreated: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TransactionCreate) => apiClient.post('/transactions', { body, silent: true }),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Transaction ajoutée', description: 'La transaction a été enregistrée.' })
      onCreated()
    },
    onError: (error) => {
      toast({ variant: 'destructive', title: 'Erreur', description: serverMessage(error) ?? "Impossible d'ajouter la transaction." })
    },
  })
}

export function useCreateAsset(onCreated: (asset: { id: string; symbol: string }) => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AssetCreate) => apiClient.post('/assets', { body, silent: true }),
    onSuccess: (asset) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.assets.all })
      onCreated(asset)
      toast({ title: 'Actif créé', description: `${asset.symbol} ajouté au portefeuille.` })
    },
    onError: (error) => {
      toast({ variant: 'destructive', title: 'Erreur', description: serverMessage(error) ?? "Impossible de créer l'actif." })
    },
  })
}
