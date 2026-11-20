import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/hooks/use-toast'
import { invalidateAllFinancialData } from '@/lib/invalidate-queries'
import { queryKeys } from '@/lib/queryKeys'
import { apiClient } from '@/shared/api/client'
import { failureToast } from './hooks'

const POLL_INTERVAL_MS = 5000
const POLL_LIMIT_MS = 600000

interface FollowedTask {
  successTitle: string
  errorTitle: string
  describe: (synced: number) => string
  onEnd: () => void
}

interface Timers {
  interval: ReturnType<typeof setInterval>
  timeout: ReturnType<typeof setTimeout>
}

function useTaskPolling(onCompleted: () => void) {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const timersRef = useRef(new Map<string, Timers>())

  useEffect(() => {
    const timers = timersRef.current
    return () => {
      timers.forEach(({ interval, timeout }) => {
        clearInterval(interval)
        clearTimeout(timeout)
      })
      timers.clear()
    }
  }, [])

  return (taskId: string, task: FollowedTask) => {
    const end = () => {
      const timers = timersRef.current.get(taskId)
      if (timers) {
        clearInterval(timers.interval)
        clearTimeout(timers.timeout)
        timersRef.current.delete(taskId)
      }
      task.onEnd()
    }

    const interval = setInterval(async () => {
      try {
        const status = await apiClient.get('/api-keys/import-status/{task_id}', { path: { task_id: taskId } })
        if (status.status === 'completed') {
          end()
          queryClient.invalidateQueries({ queryKey: queryKeys.apiKeys.all })
          invalidateAllFinancialData(queryClient)
          toast({ title: task.successTitle, description: task.describe(status.synced ?? 0) })
          onCompleted()
        } else if (status.status === 'failed') {
          end()
          toast({ variant: 'destructive', title: task.errorTitle, description: status.error || "L'opération a échoué." })
        }
      } catch {
        end()
        toast({ variant: 'destructive', title: 'Erreur', description: "Impossible de vérifier le statut de l'opération." })
      }
    }, POLL_INTERVAL_MS)

    const timeout = setTimeout(end, POLL_LIMIT_MS)
    timersRef.current.set(taskId, { interval, timeout })
  }
}

export function useBackgroundTasks(onCompleted: () => void) {
  const { toast } = useToast()
  const follow = useTaskPolling(onCompleted)
  const [importingId, setImportingId] = useState<string | null>(null)
  const [refreshingFxId, setRefreshingFxId] = useState<string | null>(null)

  const importMutation = useMutation({
    mutationFn: (id: string) => apiClient.post('/api-keys/{api_key_id}/import-async', { path: { api_key_id: id } }),
    onSuccess: (result) => {
      toast({ title: 'Import lancé', description: "L'import tourne en arrière-plan. Cela peut prendre quelques minutes." })
      follow(result.task_id, {
        successTitle: 'Import réussi',
        errorTitle: "Erreur d'import",
        describe: (synced) => (synced > 0 ? `${synced} transaction(s) synchronisée(s)` : 'Aucune nouvelle transaction'),
        onEnd: () => setImportingId(null),
      })
    },
    onError: (error) => {
      failureToast(toast, "Erreur d'import", "Impossible de lancer l'import.")(error)
      setImportingId(null)
    },
  })

  const fxMutation = useMutation({
    mutationFn: (id: string) => apiClient.post('/api-keys/{api_key_id}/refresh-fx', { path: { api_key_id: id } }),
    onSuccess: (result) => {
      toast({ title: 'Recalcul lancé', description: 'Les taux de change historiques sont recalculés en arrière-plan.' })
      follow(result.task_id, {
        successTitle: 'Recalcul terminé',
        errorTitle: 'Erreur de recalcul',
        describe: (synced) => (synced > 0 ? `${synced} transaction(s) corrigée(s)` : 'Aucune correction nécessaire'),
        onEnd: () => setRefreshingFxId(null),
      })
    },
    onError: (error) => {
      failureToast(toast, 'Erreur de recalcul', 'Impossible de lancer le recalcul.')(error)
      setRefreshingFxId(null)
    },
  })

  return {
    importingId,
    refreshingFxId,
    importHistory: (id: string) => {
      setImportingId(id)
      importMutation.mutate(id)
    },
    refreshFx: (id: string) => {
      setRefreshingFxId(id)
      fxMutation.mutate(id)
    },
  }
}
