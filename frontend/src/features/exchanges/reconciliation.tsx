import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ToastAction } from '@/components/ui/toast'
import { useToast } from '@/hooks/use-toast'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { counted, formatCurrency } from '@/lib/utils'
import { apiClient } from '@/shared/api/client'
import { totalMissingEur } from './format'
import { failureToast } from './hooks'
import type { BalanceGap, GapCheck } from './types'

const GAP_THRESHOLD_EUR = 5

const fetchGaps = () =>
  apiClient.get('/transactions/balance-gaps', { query: { threshold_eur: GAP_THRESHOLD_EUR }, silent: true })

function untrackedRewards(count: number, gaps: BalanceGap[], onCredit: () => void) {
  const top = gaps
    .slice(0, 3)
    .map((gap) => `${gap.symbol} (${formatCurrency(gap.missing_eur)})`)
    .join(', ')
  const hasEarn = gaps.some((gap) => gap.source_hint === 'earn_pending')
  return {
    title: counted(count, 'récompense non tracée détectée', 'récompenses non tracées détectées'),
    description:
      `Total estimé : ${formatCurrency(totalMissingEur(gaps))}. Top : ${top}.` + (hasEarn ? ' (probables intérêts Earn)' : ''),
    action: (
      <ToastAction altText="Créditer automatiquement les récompenses en AIRDROP" onClick={onCredit}>
        Créditer auto
      </ToastAction>
    ),
  }
}

export function useReconciliation() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [check, setCheck] = useState<GapCheck | null>(null)
  const gapFailure = failureToast(toast, 'Erreur', 'Impossible de vérifier les écarts de solde.')

  const verify = useMutation({
    mutationFn: fetchGaps,
    onSuccess: (result) => setCheck({ gaps: result.gaps, checkedAt: new Date() }),
    onError: gapFailure,
  })

  const credit = useMutation({
    mutationFn: () =>
      apiClient.post('/transactions/balance-gaps/credit-all', { query: { threshold_eur: GAP_THRESHOLD_EUR }, silent: true }),
    onSuccess: (result) => {
      toast({
        title: `${counted(result.credited, 'récompense créditée', 'récompenses créditées')} en AIRDROP`,
        description:
          result.skipped > 0
            ? `${counted(result.skipped, 'ignorée', 'ignorées')} (déjà créditées ou prix marché manquant).`
            : 'Vous pouvez les modifier depuis Transactions.',
      })
      invalidateAllFinancialData(queryClient)
      verify.mutate()
    },
    onError: failureToast(toast, 'Erreur lors du crédit auto', 'Impossible de créditer les récompenses.'),
  })

  const checkAfterTask = () => {
    fetchGaps()
      .then((result) => {
        setCheck({ gaps: result.gaps, checkedAt: new Date() })
        if (result.count > 0) toast(untrackedRewards(result.count, result.gaps, () => credit.mutate()))
      })
      .catch(gapFailure)
  }

  return { check, verify, credit, checkAfterTask }
}

export type Reconciliation = ReturnType<typeof useReconciliation>
