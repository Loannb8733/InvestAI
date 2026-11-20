import { useBackgroundTasks } from './backgroundTasks'
import { useSyncKey, useTestKey, useUpdateKey } from './hooks'
import type { ApiKey, TestResult } from './types'

export interface KeyActions {
  testingId: string | null
  syncingId: string | null
  togglingId: string | null
  importingId: string | null
  refreshingFxId: string | null
  test: (id: string) => void
  sync: (id: string) => void
  toggle: (apiKey: ApiKey) => void
  importHistory: (id: string) => void
  refreshFx: (id: string) => void
}

interface KeyActionCallbacks {
  onTested: (result: TestResult) => void
  onSaved: () => void
  onTaskCompleted: () => void
}

export function useKeyActions({ onTested, onSaved, onTaskCompleted }: KeyActionCallbacks) {
  const test = useTestKey(onTested)
  const sync = useSyncKey()
  const update = useUpdateKey(onSaved)
  const tasks = useBackgroundTasks(onTaskCompleted)
  const toggling = update.isPending && update.variables?.data.is_active !== undefined

  const actions: KeyActions = {
    testingId: test.isPending ? (test.variables ?? null) : null,
    syncingId: sync.isPending ? (sync.variables ?? null) : null,
    togglingId: toggling ? (update.variables?.id ?? null) : null,
    importingId: tasks.importingId,
    refreshingFxId: tasks.refreshingFxId,
    test: (id) => test.mutate(id),
    sync: (id) => sync.mutate(id),
    toggle: (apiKey) => update.mutate({ id: apiKey.id, data: { is_active: !apiKey.is_active } }),
    importHistory: tasks.importHistory,
    refreshFx: tasks.refreshFx,
  }

  return { actions, update }
}
