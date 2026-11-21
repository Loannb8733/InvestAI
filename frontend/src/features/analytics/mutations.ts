import { useMutation } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { apiClient } from '@/shared/api/client'
import { ANALYTICS_TIMEOUT_MS } from './queries'
import type { PlanOrderInput } from './types'

export function useRebalance() {
  return useMutation({
    mutationFn: (targetWeights: Record<string, number>) =>
      apiClient.post('/analytics/rebalance', { body: targetWeights, timeout: ANALYTICS_TIMEOUT_MS }),
  })
}

export function usePlanOrder(onPlanned: (symbol: string) => void) {
  const { toast } = useToast()
  return useMutation({
    mutationFn: (order: PlanOrderInput) =>
      apiClient.post('/predictions/planned-orders', {
        body: { ...order, notes: 'Rééquilibrage MPT (Smart Insights)', source: 'frontend' },
      }),
    onSuccess: (_data, order) => {
      onPlanned(order.symbol)
      toast({ title: 'Ordre planifié', description: `${order.symbol} — visible dans Signaux Alpha.` })
    },
    onError: () => toast({ title: "Impossible de planifier l'ordre", variant: 'destructive' }),
  })
}
