import { AlertCircle, Calendar, Loader2, Pencil, Power, RefreshCw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatDate, formatDateTime } from '@/lib/utils'
import { shortError, syncFreshness } from '../format'
import type { KeyActions } from '../keyActions'
import type { ApiKey } from '../types'
import ExchangeLogo from './ExchangeLogo'
import KeyActionButtons from './KeyActionButtons'

interface ApiKeyCardProps {
  apiKey: ApiKey
  name: string
  position: number | null
  actions: KeyActions
  onRename: (apiKey: ApiKey) => void
  onDelete: (apiKey: ApiKey) => void
}

export default function ApiKeyCard({ apiKey, name, position, actions, onRename, onDelete }: ApiKeyCardProps) {
  const toggling = actions.togglingId === apiKey.id
  const freshness = apiKey.last_sync_at ? syncFreshness(apiKey.last_sync_at) : null

  return (
    <Card elevation="raised" className="relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-1 ${apiKey.is_active ? 'bg-gain' : 'bg-loss'}`} />

      <CardHeader className="pb-3 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <ExchangeLogo exchange={apiKey.exchange} size={48} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <CardTitle className="text-lg truncate">{name}</CardTitle>
                {position !== null && (
                  <Badge variant="secondary" className="text-xs">
                    #{position}
                  </Badge>
                )}
              </div>
              {apiKey.label ? (
                <p className="text-sm text-muted-foreground truncate">{apiKey.label}</p>
              ) : (
                <p className="text-sm text-muted-foreground italic">Sans label</p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0">
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground"
                title="Renommer cette connexion"
                onClick={() => onRename(apiKey)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <button
                type="button"
                title={
                  apiKey.is_active ? 'Cliquer pour désactiver cette connexion' : 'Cliquer pour réactiver cette connexion'
                }
                onClick={() => actions.toggle(apiKey)}
                disabled={toggling}
                className="disabled:opacity-50"
              >
                <Badge variant={apiKey.is_active ? 'default' : 'destructive'} className="cursor-pointer gap-1">
                  {toggling ? <Loader2 className="h-3 w-3 animate-spin" /> : <Power className="h-3 w-3" />}
                  {apiKey.is_active ? 'Actif' : 'Inactif'}
                </Badge>
              </button>
            </div>
            {!apiKey.is_active && <span className="text-[10px] text-muted-foreground">exclue de la sync auto</span>}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-2 text-xs">
          <div className="flex items-center gap-1 text-muted-foreground bg-muted px-2 py-1 rounded-md">
            <Calendar className="h-3 w-3" />
            <span>Créé le {formatDate(apiKey.created_at)}</span>
          </div>
          {apiKey.last_sync_at && (
            <>
              <div className="flex items-center gap-1 text-muted-foreground bg-muted px-2 py-1 rounded-md">
                <RefreshCw className="h-3 w-3" />
                <span>Sync {formatDateTime(apiKey.last_sync_at)}</span>
              </div>
              {freshness && (
                <Badge variant="outline" className={`text-xs font-medium ${freshness.className}`}>
                  {freshness.label}
                </Badge>
              )}
            </>
          )}
        </div>

        {apiKey.last_error && (
          <div className="flex items-start gap-2 text-sm text-loss bg-loss/10 p-2 rounded-md" title={apiKey.last_error}>
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <span className="line-clamp-2">
              Dernière sync en échec :{' '}
              {shortError(apiKey.last_error)}
            </span>
          </div>
        )}

        <KeyActionButtons apiKey={apiKey} actions={actions} onDelete={onDelete} />
      </CardContent>
    </Card>
  )
}
