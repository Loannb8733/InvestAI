import { ArrowDownRight, ArrowUpRight, RefreshCw, Shield } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency } from '@/lib/utils'
import type { PlanOrderInput, RebalancingOrder } from '../types'

export interface MarketMode {
  isBearMode: boolean
  isBullMode: boolean
}

interface MptOrdersCardProps {
  orders: RebalancingOrder[]
  plannedSymbols: Set<string>
  onPlanOrder: (order: PlanOrderInput) => void
  isPlanningOrder: boolean
  mode: MarketMode
}

function actionLabel(action: string, { isBearMode, isBullMode }: MarketMode) {
  if (action === 'buy') return isBearMode ? 'Accumuler' : 'Acheter'
  if (action === 'hold') return 'Conserver'
  return isBullMode ? 'Prendre profits' : 'Vendre'
}

function ActionBadge({ action, mode }: { action: string; mode: MarketMode }) {
  return (
    <Badge
      variant={action === 'buy' ? 'default' : action === 'hold' ? 'outline' : 'destructive'}
      className={action === 'hold' ? 'border-warning text-warning dark:text-warning' : ''}
    >
      {action === 'buy' ? (
        <ArrowUpRight className="h-3 w-3 mr-1" />
      ) : action === 'hold' ? (
        <Shield className="h-3 w-3 mr-1" />
      ) : (
        <ArrowDownRight className="h-3 w-3 mr-1" />
      )}
      {actionLabel(action, mode)}
    </Badge>
  )
}

function OrderRow({ order, plannedSymbols, onPlanOrder, isPlanningOrder, mode }: Omit<MptOrdersCardProps, 'orders'> & { order: RebalancingOrder }) {
  const plannable = order.action === 'buy' || order.action === 'sell'
  return (
    <tr className="border-b last:border-b-0">
      <td className="p-2">
        <div className="font-medium">{order.symbol}</div>
        <div className="text-xs text-muted-foreground">{order.name}</div>
      </td>
      <td className="p-2 text-center">
        <ActionBadge action={order.action} mode={mode} />
      </td>
      <td className="p-2 text-right">{((order.current_weight ?? 0) * 100).toFixed(1)}%</td>
      <td className="p-2 text-right">{((order.target_weight ?? 0) * 100).toFixed(1)}%</td>
      <td className="p-2 text-right font-mono">
        <span className={order.action === 'buy' ? 'text-gain' : order.action === 'hold' ? 'text-warning' : 'text-loss'}>
          {order.action === 'buy' ? '+' : order.action === 'hold' ? '~' : '-'}{formatCurrency(Math.abs(order.amount_eur ?? 0))}
        </span>
      </td>
      <td className="p-2 text-xs text-muted-foreground max-w-[200px]">{order.reason}</td>
      <td className="p-2 text-right">
        {plannable &&
          (plannedSymbols.has(order.symbol) ? (
            <span className="text-xs text-gain">Planifié ✓</span>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs"
              disabled={isPlanningOrder}
              onClick={() =>
                onPlanOrder({
                  symbol: order.symbol,
                  side: order.action as 'buy' | 'sell',
                  amount_eur: Math.abs(order.amount_eur ?? 0),
                })
              }
            >
              Planifier
            </Button>
          ))}
      </td>
    </tr>
  )
}

export default function MptOrdersCard({ orders, ...rowProps }: MptOrdersCardProps) {
  return (
    <Card elevation="raised">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <RefreshCw className="h-5 w-5 text-accent" />
          MPT Smart Insights
        </CardTitle>
        <CardDescription>
          Ordres suggérés pour optimiser le ratio de Sharpe (MPT) — planifiables dans Signaux Alpha
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th scope="col" className="text-left p-2">Actif</th>
                <th scope="col" className="text-center p-2">Action</th>
                <th scope="col" className="text-right p-2">Poids actuel</th>
                <th scope="col" className="text-right p-2">Poids cible</th>
                <th scope="col" className="text-right p-2">Montant</th>
                <th scope="col" className="text-left p-2">Raison</th>
                <th scope="col" className="text-right p-2">
                  <span className="sr-only">Planifier</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order, idx) => (
                <OrderRow key={idx} order={order} {...rowProps} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
