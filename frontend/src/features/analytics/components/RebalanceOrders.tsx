import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'
import type { RebalanceResponse } from '../types'

export default function RebalanceOrders({ result }: { result: RebalanceResponse }) {
  const actionableOrders = result.orders.filter((o) => o.action === 'buy' || o.action === 'sell')
  if (actionableOrders.length === 0) {
    return (
      <p className="text-xs text-muted-foreground text-center py-2">
        Aucun ordre nécessaire — votre allocation est déjà proche de la cible.
      </p>
    )
  }
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th scope="col" className="text-left p-2 font-medium">Actif</th>
              <th scope="col" className="text-center p-2 font-medium">Action</th>
              <th scope="col" className="text-right p-2 font-medium">Montant</th>
              <th scope="col" className="text-right p-2 font-medium">Poids actuel → cible</th>
            </tr>
          </thead>
          <tbody>
            {actionableOrders.map((order) => (
              <tr key={order.symbol} className="border-b last:border-b-0">
                <td className="p-2">
                  <div className="font-medium">{order.symbol}</div>
                  <div className="text-xs text-muted-foreground">{order.name}</div>
                </td>
                <td className="p-2 text-center">
                  <span className={`inline-flex items-center gap-1 text-xs font-medium ${order.action === 'buy' ? 'text-gain' : 'text-loss'}`}>
                    {order.action === 'buy' ? (
                      <ArrowUpRight className="h-3 w-3" />
                    ) : (
                      <ArrowDownRight className="h-3 w-3" />
                    )}
                    {order.action === 'buy' ? 'Acheter' : 'Vendre'}
                  </span>
                </td>
                <td className={`p-2 text-right font-mono ${order.action === 'buy' ? 'text-gain' : 'text-loss'}`}>
                  {order.action === 'buy' ? '+' : '−'}{formatCurrency(Math.abs(order.diff_value))}
                </td>
                <td className="p-2 text-right font-mono text-xs">
                  {order.current_weight.toFixed(1)}% → {order.target_weight.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground text-center">
        Ordres suggérés (optimisation Markowitz) — ne constitue pas un conseil en investissement.
      </p>
    </>
  )
}
