import { useState, useMemo } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { dashboardApi, crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import AllocationChart from '@/components/charts/AllocationChart'
import PerformanceChart from '@/components/charts/PerformanceChart'
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  Crosshair,
  PiggyBank,
  AlertTriangle,
  Bell,
  Calendar,
  Banknote,
  BarChart3,
  Loader2,
} from 'lucide-react'
import type { ProjectAudit, CrowdfundingDashboard } from '@/types/crowdfunding'

// ============== Interfaces ==============

interface ActiveAlert {
  id: string
  name: string
  symbol?: string
  condition: string
  threshold: number
  current_price?: number
}

interface UpcomingEvent {
  id: string
  title: string
  event_type: string
  event_date: string
  amount?: number
}

interface PnLBreakdown {
  realized_pnl: number
  unrealized_pnl: number
  total_pnl: number
  total_fees: number
  net_pnl: number
}

interface AdvancedMetrics {
  roi_annualized: number
  risk_metrics: Record<string, unknown>
  concentration: Record<string, unknown>
  stress_tests: unknown[]
  pnl_breakdown: PnLBreakdown
}

interface DashboardMetrics {
  total_value: number
  total_invested: number
  net_capital: number
  total_gain_loss: number
  total_gain_loss_percent: number
  net_gain_loss: number
  net_gain_loss_percent: number
  daily_change: number
  daily_change_percent: number
  period_change?: number
  period_change_percent?: number
  allocation: Array<{ type: string; value: number; percentage: number }>
  historical_data: Array<{ date: string; value: number; invested?: number; net_capital?: number }>
  active_alerts: ActiveAlert[]
  upcoming_events: UpcomingEvent[]
  advanced_metrics: AdvancedMetrics
  available_liquidity?: number
  period_days?: number
  period_label?: string
  last_updated: string
}

// ============== Constants ==============

const PERIOD_OPTIONS = [
  { label: '24h', value: 1 },
  { label: '7j', value: 7 },
  { label: '30j', value: 30 },
  { label: '90j', value: 90 },
  { label: '1an', value: 365 },
  { label: 'Tout', value: 0 },
]

// ============== Component ==============

export default function MasterDashboardPage() {
  const [selectedPeriod, setSelectedPeriod] = useState(30)
  const navigate = useNavigate()

  // Fetch crypto dashboard metrics
  const { data: metrics, isLoading: metricsLoading } = useQuery<DashboardMetrics>({
    queryKey: [...queryKeys.dashboard.metrics(selectedPeriod), 'EUR'],
    queryFn: () => dashboardApi.getMetrics(selectedPeriod),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  // Fetch crowdfunding dashboard
  const { data: cfDashboard, isLoading: cfLoading } = useQuery<CrowdfundingDashboard>({
    queryKey: queryKeys.crowdfunding.dashboard,
    queryFn: crowdfundingApi.getDashboard,
    staleTime: 60_000,
  })

  // Fetch recent audits for red flags
  const { data: audits } = useQuery<ProjectAudit[]>({
    queryKey: queryKeys.crowdfunding.audits,
    queryFn: crowdfundingApi.listAudits,
    staleTime: 120_000,
  })

  // ============== Computed values ==============

  const netWorth = useMemo(() => {
    const cryptoValue = metrics?.total_value ?? 0
    const cfValue = cfDashboard?.total_invested ?? 0
    return cryptoValue + cfValue
  }, [metrics, cfDashboard])

  const totalInvested = useMemo(() => {
    return (metrics?.total_invested ?? 0) + (cfDashboard?.total_invested ?? 0)
  }, [metrics, cfDashboard])

  const change = useMemo(() => {
    if (!metrics) return { amount: 0, percent: 0 }
    if (selectedPeriod === 1) {
      return { amount: metrics.daily_change, percent: metrics.daily_change_percent }
    }
    return {
      amount: metrics.period_change ?? metrics.daily_change,
      percent: metrics.period_change_percent ?? metrics.daily_change_percent,
    }
  }, [metrics, selectedPeriod])

  const pnl = useMemo(() => {
    const cryptoPnl = metrics?.advanced_metrics?.pnl_breakdown?.net_pnl ?? 0
    const cfInterest = (cfDashboard?.total_received ?? 0) - (cfDashboard?.total_invested ?? 0)
    return cryptoPnl + Math.max(0, cfInterest)
  }, [metrics, cfDashboard])

  // Blend CAGR: weighted by capital
  const blendedReturn = useMemo(() => {
    const cryptoCAGR = metrics?.advanced_metrics?.roi_annualized ?? 0
    const cryptoWeight = metrics?.total_value ?? 0
    const cfWeight = cfDashboard?.total_invested ?? 0
    const cfReturn = cfDashboard?.weighted_average_rate ?? 0
    const totalWeight = cryptoWeight + cfWeight
    if (totalWeight === 0) return 0
    return (cryptoCAGR * cryptoWeight + cfReturn * cfWeight) / totalWeight
  }, [metrics, cfDashboard])

  // Merge allocation: crypto allocation + crowdfunding segment
  const mergedAllocation = useMemo(() => {
    const cryptoAlloc = metrics?.allocation ?? []
    const cfTotal = cfDashboard?.total_invested ?? 0
    if (cfTotal <= 0) return cryptoAlloc

    const totalAll = cryptoAlloc.reduce((s, a) => s + a.value, 0) + cfTotal
    const result = cryptoAlloc.map((a) => ({
      ...a,
      percentage: totalAll > 0 ? (a.value / totalAll) * 100 : 0,
    }))
    result.push({
      type: 'crowdfunding',
      value: cfTotal,
      percentage: totalAll > 0 ? (cfTotal / totalAll) * 100 : 0,
    })
    return result
  }, [metrics, cfDashboard])

  // Points d'attention (max 3)
  const attentionItems = useMemo(() => {
    const items: Array<{ type: 'alert' | 'event' | 'redflag'; title: string; detail: string }> = []

    // Red flags from recent audits
    const flaggedAudits = (audits ?? []).filter((a) => a.red_flags.length > 0)
    if (flaggedAudits.length > 0) {
      const latest = flaggedAudits[0]
      items.push({
        type: 'redflag',
        title: `Red flag : ${latest.project_name || 'Audit'}`,
        detail: latest.red_flags[0],
      })
    }

    // Active alerts
    const alerts = metrics?.active_alerts ?? []
    for (const alert of alerts.slice(0, 2)) {
      items.push({
        type: 'alert',
        title: alert.name,
        detail: `${alert.symbol ?? ''} — ${alert.condition} ${alert.threshold}`,
      })
    }

    // Upcoming events (next 7 days)
    const now = new Date()
    const week = new Date(now.getTime() + 7 * 86400000)
    const upcomingEvents = (metrics?.upcoming_events ?? []).filter((e) => {
      const d = new Date(e.event_date)
      return d >= now && d <= week
    })
    for (const ev of upcomingEvents.slice(0, 1)) {
      items.push({
        type: 'event',
        title: ev.title,
        detail: new Date(ev.event_date).toLocaleDateString('fr-FR'),
      })
    }

    return items.slice(0, 3)
  }, [metrics, audits])

  const isLoading = metricsLoading || cfLoading
  const isPositive = change.amount >= 0

  if (isLoading && !metrics) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Patrimoine Global</h1>
          <p className="text-muted-foreground text-sm">
            Vue d'ensemble de tous vos investissements
          </p>
        </div>
        <div className="flex gap-1 bg-muted rounded-lg p-1">
          {PERIOD_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={selectedPeriod === opt.value ? 'default' : 'ghost'}
              size="sm"
              className="h-7 px-3 text-xs"
              onClick={() => setSelectedPeriod(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Net Worth Card */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4">
            <div>
              <p className="text-sm text-muted-foreground mb-1">Valeur nette totale</p>
              <p className="text-4xl font-bold tracking-tight tabular-nums">{formatCurrency(netWorth)}</p>
              <div className="flex items-center gap-2 mt-2">
                {isPositive ? (
                  <Badge variant="outline" className="text-green-600 border-green-200 bg-green-50 dark:bg-green-950/20">
                    <ArrowUpRight className="h-3 w-3 mr-1" />
                    {formatPercent(change.percent)} ({formatCurrency(change.amount)})
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-red-600 border-red-200 bg-red-50 dark:bg-red-950/20">
                    <ArrowDownRight className="h-3 w-3 mr-1" />
                    {formatPercent(change.percent)} ({formatCurrency(change.amount)})
                  </Badge>
                )}
                <span className="text-xs text-muted-foreground">
                  {PERIOD_OPTIONS.find((o) => o.value === selectedPeriod)?.label ?? ''}
                </span>
              </div>
            </div>
            <div className="text-right text-sm text-muted-foreground">
              {cfDashboard && (cfDashboard.active_count + cfDashboard.completed_count) > 0 && (
                <p>dont {formatCurrency(cfDashboard.total_invested)} en crowdfunding</p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* KPI Row */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <motion.div whileHover={{ scale: 1.02 }} transition={{ type: 'spring', stiffness: 300 }}>
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                <Wallet className="h-3.5 w-3.5" />
                Total Investi
              </div>
              <p className="text-xl font-bold tracking-tight tabular-nums">{formatCurrency(totalInvested)}</p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} transition={{ type: 'spring', stiffness: 300 }}>
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                {pnl >= 0 ? (
                  <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
                ) : (
                  <TrendingDown className="h-3.5 w-3.5 text-red-500" />
                )}
                P&L Net
              </div>
              <p className={`text-xl font-bold tracking-tight tabular-nums ${pnl >= 0 ? 'text-emerald-400 drop-shadow-[0_0_6px_rgba(16,185,129,0.4)]' : 'text-red-400 drop-shadow-[0_0_6px_rgba(239,68,68,0.4)]'}`}>
                {formatCurrency(pnl)}
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} transition={{ type: 'spring', stiffness: 300 }}>
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                <BarChart3 className="h-3.5 w-3.5" />
                Rendement annualisé
              </div>
              <p className={`text-xl font-bold tracking-tight tabular-nums ${blendedReturn >= 0 ? 'text-emerald-400 drop-shadow-[0_0_6px_rgba(16,185,129,0.4)]' : 'text-red-400 drop-shadow-[0_0_6px_rgba(239,68,68,0.4)]'}`}>
                {formatPercent(blendedReturn)}
              </p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div whileHover={{ scale: 1.02 }} transition={{ type: 'spring', stiffness: 300 }}>
          <Card>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center gap-2 text-muted-foreground text-xs mb-1">
                <Banknote className="h-3.5 w-3.5" />
                Liquidités
              </div>
              <p className="text-xl font-bold tracking-tight tabular-nums">
                {formatCurrency(metrics?.available_liquidity ?? 0)}
              </p>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Charts Row */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Allocation Pie */}
        <Card>
          <CardHeader>
            <CardTitle>Allocation Globale</CardTitle>
          </CardHeader>
          <CardContent>
            <AllocationChart data={mergedAllocation} />
          </CardContent>
        </Card>

        {/* Performance Line */}
        <Card>
          <CardHeader>
            <CardTitle>Performance du Capital</CardTitle>
          </CardHeader>
          <CardContent>
            {metrics?.historical_data && metrics.historical_data.length > 0 ? (
              <PerformanceChart
                data={metrics.historical_data}
                period={selectedPeriod || 365}
              />
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                Aucune donnée historique
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Attention + Quick Actions row */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Points d'Attention */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5" />
              Points d'Attention
            </CardTitle>
          </CardHeader>
          <CardContent>
            {attentionItems.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                Aucune alerte en cours
              </p>
            ) : (
              <div className="space-y-3">
                {attentionItems.map((item, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                    {item.type === 'redflag' && (
                      <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                    )}
                    {item.type === 'alert' && (
                      <Bell className="h-5 w-5 text-orange-500 shrink-0 mt-0.5" />
                    )}
                    {item.type === 'event' && (
                      <Calendar className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{item.title}</p>
                      <p className="text-xs text-muted-foreground truncate">{item.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <Card>
          <CardHeader>
            <CardTitle>Raccourcis</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button
              variant="outline"
              className="w-full justify-start gap-3 h-12"
              onClick={() => navigate('/crowdfunding/audit-lab')}
            >
              <ShieldCheck className="h-5 w-5 text-blue-500" />
              <div className="text-left">
                <p className="font-medium text-sm">Nouvel Audit</p>
                <p className="text-xs text-muted-foreground">Analyser un projet crowdfunding</p>
              </div>
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start gap-3 h-12"
              onClick={() => navigate('/intelligence?tab=predictions')}
            >
              <Crosshair className="h-5 w-5 text-green-500" />
              <div className="text-left">
                <p className="font-medium text-sm">Signaux Alpha</p>
                <p className="text-xs text-muted-foreground">Top opportunités crypto</p>
              </div>
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start gap-3 h-12"
              onClick={() => navigate('/strategy?tab=simulations')}
            >
              <PiggyBank className="h-5 w-5 text-purple-500" />
              <div className="text-left">
                <p className="font-medium text-sm">Simuler DCA</p>
                <p className="text-xs text-muted-foreground">Projeter vos dépôts de 300 €/mois</p>
              </div>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
