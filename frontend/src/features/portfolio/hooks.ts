import { useCallback, useMemo } from 'react'
import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { formatCurrency } from '@/lib/utils'
import { apiClient } from '@/shared/api/client'
import { serverMessage } from '@/shared/api/errors'
import { useAuthStore } from '@/stores/authStore'
import type { AssetCreate, AssetTransaction, Position, SparklineSeries } from './types'

export const TX_LIMIT = 20

const QUIET = { suppressGlobalError: true }

export function useMoney() {
  const currency = useAuthStore((s) => s.user?.preferredCurrency || 'EUR')
  return useCallback((value: number | null | undefined) => formatCurrency(value, currency), [currency])
}

export function usePortfolioList() {
  return useQuery({
    queryKey: queryKeys.portfolios.list(),
    queryFn: () => apiClient.get('/portfolios', { silent: true }),
    staleTime: 60_000,
    meta: QUIET,
  })
}

export function useAssetList() {
  return useQuery({ queryKey: queryKeys.assets.list(), queryFn: () => apiClient.get('/assets'), staleTime: 60_000 })
}

export function usePortfolioPerformance(portfolioId: string | null, currency: string) {
  return useQuery({
    queryKey: [...queryKeys.portfolios.metrics(portfolioId), currency],
    queryFn: () => apiClient.get('/dashboard/portfolio/{portfolio_id}', { path: { portfolio_id: portfolioId ?? '' }, silent: true }),
    enabled: !!portfolioId,
    placeholderData: keepPreviousData,
    meta: QUIET,
  })
}

export function usePortfolioHistory(portfolioId: string | null, currency: string, enabled: boolean) {
  return useQuery({
    queryKey: [...queryKeys.portfolios.history(portfolioId), currency],
    queryFn: () =>
      apiClient.get('/dashboard/portfolio/{portfolio_id}/history', { path: { portfolio_id: portfolioId ?? '' }, silent: true }),
    enabled: !!portfolioId && enabled,
    placeholderData: keepPreviousData,
    meta: QUIET,
  })
}

export function useSparklines(portfolioId: string | null, enabled: boolean) {
  const { data } = useQuery({
    queryKey: queryKeys.portfolios.sparklines(portfolioId),
    queryFn: () =>
      apiClient.get('/dashboard/portfolio/{portfolio_id}/sparklines', {
        path: { portfolio_id: portfolioId ?? '' },
        query: { days: 30 },
        silent: true,
      }),
    enabled: !!portfolioId && enabled,
    staleTime: 5 * 60_000,
    meta: QUIET,
  })
  return useMemo(() => {
    if (!data) return undefined
    const map: Record<string, SparklineSeries> = {}
    for (const s of data) map[s.symbol] = { prices: s.prices, change_pct: s.change_pct }
    return map
  }, [data])
}

const latest = (tx: AssetTransaction) => new Date(tx.executed_at || tx.created_at).getTime()

export function useAssetTransactions(assets: Position[], open: boolean) {
  const queries = useQueries({
    queries: assets.map((asset) => ({
      queryKey: queryKeys.transactions.byAsset(asset.id),
      queryFn: async () => {
        const page = await apiClient.get('/transactions', { query: { asset_id: asset.id, limit: TX_LIMIT }, silent: true })
        return Array.isArray(page) ? page : page.items
      },
      enabled: open && assets.length > 0,
      staleTime: 30_000,
      meta: QUIET,
    })),
  })
  return {
    loading: queries.some((q) => q.isLoading),
    failed: queries.length > 0 && queries.every((q) => q.isError),
    transactions: queries
      .flatMap((q) => q.data ?? [])
      .sort((a, b) => latest(b) - latest(a))
      .slice(0, TX_LIMIT),
  }
}

function useFinancialMutation<T>(
  mutationFn: (variables: T) => Promise<unknown>,
  success: string,
  failure: string,
  onDone: () => void = () => {}
) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      onDone()
      toast({ title: success })
    },
    onError: () => {
      onDone()
      toast({ variant: 'destructive', title: 'Erreur', description: failure })
    },
  })
}

export const useDeleteAsset = (onDone: () => void) =>
  useFinancialMutation(
    (id: string) => apiClient.delete('/assets/{asset_id}', { path: { asset_id: id }, silent: true }),
    'Actif et transactions supprimés',
    "Impossible de supprimer l'actif",
    onDone
  )

export const useUpdateAssetExchange = () =>
  useFinancialMutation(
    ({ id, exchange }: { id: string; exchange: string | null }) =>
      apiClient.patch('/assets/{asset_id}', { path: { asset_id: id }, body: { exchange }, silent: true }),
    'Plateforme mise à jour',
    'Impossible de modifier la plateforme'
  )

export function useDeletePortfolio(onDeleted: () => void, onFailed: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete('/portfolios/{portfolio_id}', { path: { portfolio_id: id }, silent: true }),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] === 'portfolios' && query.queryKey.includes(id) })
      invalidateAllFinancialData(queryClient)
      onDeleted()
      toast({ title: 'Portefeuille supprimé' })
    },
    onError: () => {
      onFailed()
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer le portefeuille' })
    },
  })
}

export function useCreatePortfolio(onCreated: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) => apiClient.post('/portfolios', { body, silent: true }),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Portefeuille créé', description: 'Votre portefeuille a été créé avec succès.' })
      onCreated()
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de créer le portefeuille.' })
    },
  })
}

export function useCreateAsset(onCreated: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: AssetCreate) => apiClient.post('/assets', { body, silent: true }),
    onSuccess: () => {
      invalidateAllFinancialData(queryClient)
      toast({ title: 'Actif ajouté', description: "L'actif a été ajouté à votre portefeuille." })
      onCreated()
    },
    onError: (error) => {
      toast({ variant: 'destructive', title: 'Erreur', description: serverMessage(error) ?? "Impossible d'ajouter l'actif." })
    },
  })
}

export function useCashBalance(portfolioId: string, onSaved: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.portfolios.all })
  const save = useMutation({
    mutationFn: (body: { exchange: string; amount: number }) =>
      apiClient.put('/portfolios/{portfolio_id}/cash-balance', { path: { portfolio_id: portfolioId }, body, silent: true }),
    onSuccess: () => {
      refresh()
      toast({ title: 'Solde mis à jour' })
      onSaved()
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de mettre à jour le solde' })
    },
  })
  const remove = useMutation({
    mutationFn: (exchange: string) =>
      apiClient.delete('/portfolios/{portfolio_id}/cash-balance/{exchange}', {
        path: { portfolio_id: portfolioId, exchange },
        silent: true,
      }),
    onSuccess: () => {
      refresh()
      toast({ title: 'Solde supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer le solde' })
    },
  })
  return { save, remove }
}
