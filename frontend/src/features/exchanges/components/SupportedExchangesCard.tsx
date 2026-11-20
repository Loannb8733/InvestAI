import { ChevronRight, Info } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import QueryErrorState from '@/components/ui/query-error-state'
import type { ApiKey, Exchange } from '../types'
import ExchangeLogo from './ExchangeLogo'

interface SupportedExchangesCardProps {
  exchanges: Exchange[] | undefined
  apiKeys: ApiKey[]
  failed: boolean
  retrying: boolean
  onRetry: () => void
  onGuide: (exchangeId: string) => void
}

export default function SupportedExchangesCard({
  exchanges,
  apiKeys,
  failed,
  retrying,
  onRetry,
  onGuide,
}: SupportedExchangesCardProps) {
  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle>Exchanges supportés</CardTitle>
        <CardDescription>Cliquez sur un exchange pour voir le guide de création de clé API.</CardDescription>
      </CardHeader>
      <CardContent>
        {failed ? (
          <QueryErrorState
            error={undefined}
            onRetry={onRetry}
            busy={retrying}
            title="Liste des plateformes indisponible"
            description="Vos clés déjà enregistrées restent utilisables. Réessayez pour pouvoir en ajouter une nouvelle."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {exchanges?.map((exchange) => {
              const connectedCount = apiKeys.filter((apiKey) => apiKey.exchange === exchange.id).length
              return (
                <button
                  key={exchange.id}
                  type="button"
                  onClick={() => onGuide(exchange.id)}
                  className="flex items-start gap-3 p-4 rounded-lg border bg-muted/30 hover:bg-muted/50 hover:border-primary/30 transition-colors text-left group cursor-pointer"
                >
                  <ExchangeLogo exchange={exchange.id} size={40} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium">{exchange.name}</h3>
                      {connectedCount > 0 && (
                        <Badge variant="outline" className="text-xs">
                          {connectedCount} connecté{connectedCount > 1 ? 's' : ''}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground mt-1">{exchange.description}</p>
                    <p className="text-xs text-primary mt-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Info className="h-3 w-3" />
                      Voir le guide de connexion
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                </button>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
