import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ToastAction } from '@/components/ui/toast'
import { useToast } from '@/hooks/use-toast'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { apiClient } from '@/shared/api/client'
import { totalMissingEur } from './format'
import type { BalanceGap, GapCheck } from './types'

const GAP_THRESHOLD_EUR = 5

const fetchGaps = () => apiClient.get('/transactions/balance-gaps', { query: { threshold_eur: GAP_THRESHOLD_EUR } })

function untrackedRewards(count: number, gaps: BalanceGap[], onCredit: () => void) {
  const top = gaps
    .slice(0, 3)
    .map((gap) => `${gap.symbol} (${gap.missing_eur.toFixed(2)} €)`)
    .join(', ')
  const hasEarn = gaps.some((gap) => gap.source_hint === 'earn_pending')
  return {
    title: `${count} récompense(s) non tracée(s) détectée(s)`,
    description:
      `Total estimé: ${totalMissingEur(gaps).toFixed(2)} €. Top: ${top}.` + (hasEarn ? ' (probables intérêts Earn)' : ''),
    action: (
      <ToastAction altText="Crediter automatiquement les récompenses en AIRDROP" onClick={onCredit}>
        Crediter auto
      </ToastAction>
    ),
  }
}

export function useReconciliation() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [check, setCheck] = useState<GapCheck | null>(null)

  const verify = useMutation({
    mutationFn: fetchGaps,
    onSuccess: (result) => setCheck({ gaps: result.gaps, checkedAt: new Date() }),
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de vérifier les écarts de solde.' })
    },
  })

  const credit = useMutation({
    mutationFn: () =>
      apiClient.post('/transactions/balance-gaps/credit-all', { query: { threshold_eur: GAP_THRESHOLD_EUR } }),
    onSuccess: (result) => {
      toast({
        title: `${result.credited} récompense(s) créditée(s) en AIRDROP`,
        description:
          result.skipped > 0
            ? `${result.skipped} ignorée(s) (déjà créditées ou prix marché manquant).`
            : 'Vous pouvez les modifier depuis Transactions.',
      })
      invalidateAllFinancialData(queryClient)
      verify.mutate()
    },
    onError: (error: unknown) => {
      toast({
        variant: 'destructive',
        title: 'Erreur lors du crédit auto',
        description: error instanceof Error ? error.message : 'Inconnue',
      })
    },
  })

  const checkAfterTask = () => {
    fetchGaps()
      .then((result) => {
        setCheck({ gaps: result.gaps, checkedAt: new Date() })
        if (result.count > 0) toast(untrackedRewards(result.count, result.gaps, () => credit.mutate()))
      })
      .catch(() => undefined)
  }

  return { check, verify, credit, checkAfterTask }
}

export type Reconciliation = ReturnType<typeof useReconciliation>
