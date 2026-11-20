import { Clock, Link2, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/ui/empty-state'
import type { KeyActions } from '../keyActions'
import type { ApiKey } from '../types'
import ApiKeyCard from './ApiKeyCard'

interface ConnectionListProps {
  apiKeys: ApiKey[]
  nameOf: (exchangeId: string) => string
  actions: KeyActions
  onConnect: () => void
  onRename: (apiKey: ApiKey) => void
  onDelete: (apiKey: ApiKey) => void
}

function positionOf(apiKey: ApiKey, apiKeys: ApiKey[]): number | null {
  const sameExchange = apiKeys.filter((other) => other.exchange === apiKey.exchange)
  return sameExchange.length > 1 ? sameExchange.findIndex((other) => other.id === apiKey.id) + 1 : null
}

export default function ConnectionList({ apiKeys, nameOf, actions, onConnect, onRename, onDelete }: ConnectionListProps) {
  if (apiKeys.length === 0) {
    return (
      <EmptyState
        icon={Link2}
        title="Aucun exchange connecté"
        description="Connectez vos exchanges pour importer automatiquement vos positions crypto."
        action={
          <Button onClick={onConnect}>
            <Plus className="h-4 w-4 mr-2" />
            Connecter un exchange
          </Button>
        }
      />
    )
  }

  return (
    <>
      <div className="flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        <Clock className="h-3.5 w-3.5 mt-0.5 shrink-0" />
        <span>
          Synchronisation automatique : toutes les heures (serveur). La sync manuelle reste
          disponible pour forcer une mise à jour immédiate.
        </span>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {apiKeys.map((apiKey) => (
          <ApiKeyCard
            key={apiKey.id}
            apiKey={apiKey}
            name={nameOf(apiKey.exchange)}
            position={positionOf(apiKey, apiKeys)}
            actions={actions}
            onRename={onRename}
            onDelete={onDelete}
          />
        ))}
      </div>
    </>
  )
}
