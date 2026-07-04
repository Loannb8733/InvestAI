import { formatCurrency, formatPercent } from '@/lib/utils'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  PieChart,
  ArrowUpRight,
  ArrowDownRight,
  Banknote,
} from 'lucide-react'

/**
 * Rangée de métriques du dashboard — vitrine du design system.
 *
 * 5 StatCards (tilt 3D + ticker animé + badge de variation) sous un
 * SpotlightGroup : le halo suit le pointeur d'une carte à l'autre.
 * Le contrat de données et le mode privé sont ceux de l'ancienne version.
 */

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
  loading?: boolean
}

const fmtDelta = (n: number) => `${n >= 0 ? '+' : ''}${formatPercent(n)}`

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
  loading = false,
}: DashboardMetricsRowProps) {
  const periodLabel =
    selectedPeriod === 0 ? 'tout' : selectedPeriod === 1 ? '24h' : selectedPeriod === 365 ? '1an' : `${selectedPeriod}j`
  const pc = (val: number) => (privacyMode ? '••••••' : formatCurrency(val))

  return (
    <SpotlightGroup className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      <StatCard
        className="spot-card"
        label="Patrimoine Total"
        icon={Wallet}
        value={totalValue}
        format={formatCurrency}
        privacy={privacyMode}
        loading={loading}
        hint={
          <>
            {assetsCount} actifs
            {availableLiquidity != null && availableLiquidity > 0 && (
              <> · dont {pc(availableLiquidity)} de liquidité</>
            )}
          </>
        }
      />
      <StatCard
        className="spot-card"
        label="Capital Net"
        tooltip="Capital net = Total investi − Total vendu. Représente le capital réellement engagé, après déduction des ventes."
        icon={Banknote}
        value={netCapital}
        format={formatCurrency}
        privacy={privacyMode}
        loading={loading}
        hint={<>{pc(totalInvested)} investi au total</>}
      />
      <StatCard
        className="spot-card"
        label="Plus-value Nette"
        tooltip="Patrimoine Total − Capital Net. Mesure la variation de richesse globale (inclut ventes passées)."
        icon={isPositive ? TrendingUp : TrendingDown}
        value={netGainLoss}
        format={formatCurrency}
        delta={netGainLossPercent}
        formatDelta={fmtDelta}
        tone="auto"
        privacy={privacyMode}
        loading={loading}
      />
      <StatCard
        className="spot-card"
        label={`Variation ${periodLabel}`}
        icon={isDailyPositive ? ArrowUpRight : ArrowDownRight}
        value={dailyChange}
        format={formatCurrency}
        delta={dailyChangePercent}
        deltaLabel={periodLabel}
        formatDelta={fmtDelta}
        tone="auto"
        privacy={privacyMode}
        loading={loading}
      />
      <StatCard
        className="spot-card"
        label="Portefeuilles"
        icon={PieChart}
        value={portfoliosCount}
        format={(n) => Math.round(n).toString()}
        loading={loading}
        hint={
          <>
            portefeuille{portfoliosCount > 1 ? 's' : ''} actif{portfoliosCount > 1 ? 's' : ''}
          </>
        }
      />
    </SpotlightGroup>
  )
}
