import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import EmptyState from '@/components/ui/empty-state'
import { formatCurrency } from '@/lib/utils'
import { predictionsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { toast } from '@/hooks/use-toast'
import { AlertTriangle, CalendarClock, Check, Loader2, X } from 'lucide-react'

interface PlannedOrder {
  id: string
  symbol: string
  action: string
  order_eur: number
  alpha_score: number | null
  regime: string | null
  source: string
  status: string
  notes: string | null
  created_at: string | null
}

const ACTION_STYLES: Record<string, string> = {
  'ACHAT': 'bg-gain/10 text-gain border border-gain/30',
  'ACHAT FORT': 'bg-gain text-white',
  'DCA': 'bg-gain/10 text-gain border border-gain/30',
  'VENDRE': 'bg-loss text-white',
  'ALLÉGER': 'bg-warning/10 text-warning border border-warning/30',
  'PRENDRE PROFITS': 'bg-warning/10 text-warning border border-warning/30',
}

const SOURCE_LABELS: Record<string, string> = {
  frontend: 'Rééquilibrage',
  telegram: 'Telegram',
}

/**
 * File d'attente des ordres planifiés : chaque ordre pending peut être marqué
 * comme exécuté (fait manuellement sur l'exchange) ou annulé.
 */
export default function PlannedOrdersSection() {
  const queryClient = useQueryClient()

  const { data: orders, isLoading, isError } = useQuery<PlannedOrder[]>({
    queryKey: queryKeys.predictions.plannedOrders,
    queryFn: predictionsApi.getPlannedOrders,
    staleTime: 30 * 1000,
    meta: { suppressGlobalError: true },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'executed' | 'cancelled' }) =>
      predictionsApi.updatePlannedOrder(id, status),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.predictions.plannedOrders })
      toast({
        title: vars.status === 'executed' ? 'Ordre marqué comme exécuté' : 'Ordre annulé',
      })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: "Impossible de mettre à jour l'ordre." })
    },
  })

  const mutatingId = updateMutation.isPending ? updateMutation.variables?.id : null

  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-primary" />
          Ordres planifiés
        </CardTitle>
        <CardDescription>
          Ordres en attente issus du rééquilibrage et des signaux — marquez-les exécutés une fois
          passés sur votre exchange, ou annulez-les.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-6 w-20" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-8 w-40 ml-auto" />
              </div>
            ))}
          </div>
        ) : isError ? (
          <EmptyState
            variant="error"
            icon={AlertTriangle}
            title="Erreur lors du chargement des ordres planifiés"
          />
        ) : !orders || orders.length === 0 ? (
          <EmptyState
            icon={CalendarClock}
            title="Aucun ordre planifié"
            description="Planifiez des ordres depuis les suggestions de rééquilibrage (pilier Risque & Performance) ou la matrice de stratégie (pilier Marché & Signaux)."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th scope="col" className="text-left py-2 px-3 text-xs font-medium">Actif</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Action</th>
                  <th scope="col" className="text-right py-2 px-3 text-xs font-medium">Montant</th>
                  <th scope="col" className="text-center py-2 px-3 text-xs font-medium">Source</th>
                  <th scope="col" className="text-right py-2 px-3 text-xs font-medium">Créé le</th>
                  <th scope="col" className="text-right py-2 px-3 text-xs font-medium">
                    <span className="sr-only">Décision</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order) => {
                  const isMutating = mutatingId === order.id
                  return (
                    <tr key={order.id} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="py-3 px-3">
                        <div className="font-medium">{order.symbol}</div>
                        {order.notes && (
                          <div className="text-xs text-muted-foreground max-w-[240px] truncate" title={order.notes}>
                            {order.notes}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <Badge className={`text-xs ${ACTION_STYLES[order.action] || 'bg-gray-100 text-gray-700'}`}>
                          {order.action}
                        </Badge>
                        {order.alpha_score != null && (
                          <div className="text-[10px] text-muted-foreground mt-0.5">
                            Alpha {Number(order.alpha_score).toFixed(0)}
                            {order.regime ? ` · ${order.regime}` : ''}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-3 text-right font-mono tabular-nums">
                        {formatCurrency(order.order_eur)}
                      </td>
                      <td className="py-3 px-3 text-center">
                        <Badge variant="outline" className="text-xs">
                          {SOURCE_LABELS[order.source] || order.source}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-right text-xs text-muted-foreground">
                        {order.created_at
                          ? new Date(order.created_at).toLocaleDateString('fr-FR')
                          : '—'}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs"
                            disabled={updateMutation.isPending}
                            onClick={() => updateMutation.mutate({ id: order.id, status: 'executed' })}
                          >
                            {isMutating && updateMutation.variables?.status === 'executed' ? (
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                            ) : (
                              <Check className="h-3 w-3 mr-1" />
                            )}
                            Exécuté
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 text-xs"
                            disabled={updateMutation.isPending}
                            onClick={() => updateMutation.mutate({ id: order.id, status: 'cancelled' })}
                          >
                            {isMutating && updateMutation.variables?.status === 'cancelled' ? (
                              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                            ) : (
                              <X className="h-3 w-3 mr-1" />
                            )}
                            Annuler
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
