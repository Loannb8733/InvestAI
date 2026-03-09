import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency, formatPercent } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  PieChart,
  ArrowUpRight,
  ArrowDownRight,
  Banknote,
  Info,
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
  selectedPeriod: number
  availableLiquidity?: number
  privacyMode?: boolean
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
  selectedPeriod,
  availableLiquidity,
  privacyMode,
}: DashboardMetricsRowProps) {
  const periodLabel = selectedPeriod === 0 ? 'Tout' : selectedPeriod === 1 ? '24h' : selectedPeriod === 365 ? '1an' : `${selectedPeriod}j`
  const pc = (val: number) => privacyMode ? '••••••' : formatCurrency(val)
  const pp = (val: number) => privacyMode ? '••••' : formatPercent(val)
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Patrimoine Total</CardTitle>
          <Wallet className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{pc(totalValue)}</div>
          <p className="text-xs text-muted-foreground">
            {assetsCount} actifs{availableLiquidity != null && availableLiquidity > 0 && ` · dont ${pc(availableLiquidity)} de liquidité`}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">
            <TooltipProvider delayDuration={100}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="cursor-help inline-flex items-center gap-1">
                    Capital Net
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  <p className="text-sm">Capital net = Total investi − Total vendu. Représente le capital réellement engagé, après déduction des ventes.</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardTitle>
          <Banknote className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{pc(netCapital)}</div>
          <p className="text-xs text-muted-foreground">{pc(totalInvested)} investi au total</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <TooltipProvider delayDuration={100}>
            <Tooltip>
              <TooltipTrigger asChild>
                <CardTitle className="text-sm font-medium cursor-help inline-flex items-center gap-1">Plus-value Nette <Info className="h-3 w-3 text-muted-foreground" /></CardTitle>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs"><p className="text-sm">Patrimoine Total − Capital Net. Mesure la variation de richesse globale (inclut ventes passées).</p></TooltipContent>
            </Tooltip>
          </TooltipProvider>
          {isPositive ? <TrendingUp className="h-4 w-4 text-green-500" /> : <TrendingDown className="h-4 w-4 text-red-500" />}
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>{isPositive ? '\u25B2' : '\u25BC'} {pc(netGainLoss)}</div>
          <p className={`text-xs ${isPositive ? 'text-green-500' : 'text-red-500'}`}>{isPositive ? '\u25B2' : '\u25BC'} {pp(netGainLossPercent)}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Variation {periodLabel}</CardTitle>
          {isDailyPositive ? <ArrowUpRight className="h-4 w-4 text-green-500" /> : <ArrowDownRight className="h-4 w-4 text-red-500" />}
        </CardHeader>
        <CardContent>
          <div className={`text-2xl font-bold ${isDailyPositive ? 'text-green-500' : 'text-red-500'}`}>{isDailyPositive ? '\u25B2' : '\u25BC'} {pc(dailyChange)}</div>
          <p className={`text-xs ${isDailyPositive ? 'text-green-500' : 'text-red-500'}`}>{isDailyPositive ? '\u25B2' : '\u25BC'} {pp(dailyChangePercent)}</p>
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
