import { Coins, Download, Key, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { KeyActions } from '../keyActions'
import type { ApiKey } from '../types'

interface KeyActionButtonsProps {
  apiKey: ApiKey
  actions: KeyActions
  onDelete: (apiKey: ApiKey) => void
}

export default function KeyActionButtons({ apiKey, actions, onDelete }: KeyActionButtonsProps) {
  const testing = actions.testingId === apiKey.id
  const syncing = actions.syncingId === apiKey.id
  const importing = actions.importingId === apiKey.id
  const refreshingFx = actions.refreshingFxId === apiKey.id

  return (
    <>
      <div className="grid grid-cols-4 gap-2">
        <Button
          variant="outline"
          size="sm"
          className="flex flex-col h-auto py-2 gap-1"
          onClick={() => actions.test(apiKey.id)}
          disabled={testing}
        >
          {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Key className="h-4 w-4" />}
          <span className="text-xs">Tester</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="flex flex-col h-auto py-2 gap-1"
          onClick={() => actions.sync(apiKey.id)}
          disabled={syncing}
        >
          {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          <span className="text-xs">Sync</span>
        </Button>
        <Button
          variant="default"
          size="sm"
          className="flex flex-col h-auto py-2 gap-1"
          onClick={() => actions.importHistory(apiKey.id)}
          disabled={importing}
        >
          {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          <span className="text-xs">Import</span>
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="flex flex-col h-auto py-2 gap-1 text-destructive hover:text-destructive hover:bg-destructive/10"
          onClick={() => onDelete(apiKey)}
        >
          <Trash2 className="h-4 w-4" />
          <span className="text-xs">Suppr.</span>
        </Button>
      </div>

      <Button
        variant="outline"
        size="sm"
        className="mt-2 w-full gap-2 text-xs text-muted-foreground"
        title="Recalcule le taux de change historique (USD→EUR) du coût de revient sur vos transactions déjà importées, sans rien supprimer."
        onClick={() => actions.refreshFx(apiKey.id)}
        disabled={refreshingFx}
      >
        {refreshingFx ? <Loader2 className="h-4 w-4 animate-spin" /> : <Coins className="h-4 w-4" />}
        Recalculer les taux de change
      </Button>
    </>
  )
}
