import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency, formatPercent } from '@/lib/utils'
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  PieChart,
  ArrowUpRight,
  ArrowDownRight,
  Banknote,
} from 'lucide-react'

interface DashboardMetricsRowProps {
  totalValue: number
  assetsCount: number
  netCapital: number
  totalInvested: number
  netGainLoss: number
  netGainLossPercent: number
  isPositive: boolean
  dailyChange: number
  dailyChangePercent: number
  isDailyPositive: boolean
  portfoliosCount: number
}

export default function DashboardMetricsRow({
  totalValue,
  assetsCount,
  netCapital,
  totalInvested,
  netGainLoss,
  netGainLossPercent,
  isPositive,
  dailyChange,
  dailyChangePercent,
  isDailyPositive,
  portfoliosCount,
}: DashboardMetricsRowProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Patrimoine Total</CardTitle>
          <Wallet className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(totalValue)}</div>
          <p className="text-xs text-muted-foreground">{assetsCount} actifs</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Capital Net</CardTitle>
          <Banknote className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{formatCurrency(netCapital)}</div>
          <p className="text-xs text-muted-foreground">{formatCurrency(totalInvested)} investi au total</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Plus-value Nette</CardTitle>
          {isPositive ? <TrendingUp className="h-4 w-4 text-green-500" /> : <TrendingDown className="h-4 w-4 text-red-500" />}
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>{isPositive ? '\u25B2' : '\u25BC'} {formatCurrency(netGainLoss)}</div>
          <p className={`text-xs ${isPositive ? 'text-green-500' : 'text-red-500'}`}>{isPositive ? '\u25B2' : '\u25BC'} {formatPercent(netGainLossPercent)}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Variation 24h</CardTitle>
          {isDailyPositive ? <ArrowUpRight className="h-4 w-4 text-green-500" /> : <ArrowDownRight className="h-4 w-4 text-red-500" />}
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${isDailyPositive ? 'text-green-500' : 'text-red-500'}`}>{isDailyPositive ? '\u25B2' : '\u25BC'} {formatCurrency(dailyChange)}</div>
          <p className={`text-xs ${isDailyPositive ? 'text-green-500' : 'text-red-500'}`}>{isDailyPositive ? '\u25B2' : '\u25BC'} {formatPercent(dailyChangePercent)}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Portefeuilles</CardTitle>
          <PieChart className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{portfoliosCount}</div>
          <p className="text-xs text-muted-foreground">portefeuille{portfoliosCount > 1 ? 's' : ''} actif{portfoliosCount > 1 ? 's' : ''}</p>
        </CardContent>
      </Card>
    </div>
  )
}
