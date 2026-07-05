import { useState, useMemo, lazy, Suspense } from 'react'
import { useAuthStore } from '@/stores/authStore'
import type { PnLBreakdown } from '@/types'
import { usePageVisibility } from '@/hooks/usePageVisibility'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { dashboardApi, crowdfundingApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import AllocationChart from '@/components/charts/AllocationChart'
// Pilote Direction A — graphe d'évolution patrimoniale en TradingView
// Lightweight Charts (canvas, ~45 Ko). Lazy-load : pas SSR-safe, hors chunk principal.
const PortfolioAreaChart = lazy(() => import('@/components/charts/PortfolioAreaChart'))
import AnimatedNumber from '@/components/ui/animated-number'
import EmptyState from '@/components/ui/empty-state'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { SkeletonStatCard } from '@/components/ui/skeleton'
import { motion, AnimatePresence } from 'framer-motion'
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

// ============== Framer Motion variants ==============

const kpiVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring' as const, duration: 0.5, bounce: 0.1 },
  },
}

const staggerContainer = {
  visible: { transition: { staggerChildren: 0.08 } },
}

// ============== Component ==============

export default function MasterDashboardPage() {
  const [selectedPeriod, setSelectedPeriod] = useState(30)
  const pageVisible = usePageVisibility()
  const navigate = useNavigate()
  const currency = useAuthStore((s) => s.user?.preferredCurrency || 'EUR')

  // Fetch crypto dashboard metrics
  const {
    data: metrics,
    isLoading: metricsLoading,
    isError: metricsError,
    refetch: refetchMetrics,
  } = useQuery<DashboardMetrics>({
    queryKey: [...queryKeys.dashboard.metrics(selectedPeriod), currency],
    queryFn: () => dashboardApi.getMetrics(selectedPeriod),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    refetchInterval: pageVisible ? 60_000 : false,
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
      amount: metrics.period_change ?? 0,
      percent: metrics.period_change_percent ?? 0,
    }
  }, [metrics, selectedPeriod])

  // Résumé narratif — « le récit avant le tableau »
  const narrative = useMemo(() => {
    if (!metrics) return ''
    const periodLabel: Record<number, string> = {
      1: 'Sur les dernières 24 heures',
      7: 'Sur les 7 derniers jours',
      30: 'Sur les 30 derniers jours',
      90: 'Sur les 90 derniers jours',
      365: 'Sur la dernière année',
      0: 'Depuis le début',
    }
    const when = periodLabel[selectedPeriod] ?? 'Sur la période'
    const verb = change.amount >= 0 ? 'progressé' : 'reculé'
    const amount = formatCurrency(Math.abs(change.amount))
    const pct = `${Math.abs(change.percent).toFixed(2)} %`
    return `${when}, ton patrimoine a ${verb} de ${amount} (${pct}).`
  }, [metrics, change, selectedPeriod])

  const pnl = useMemo(() => {
    const cryptoPnl = metrics?.advanced_metrics?.pnl_breakdown?.net_pnl ?? 0
    const cfInterest = (cfDashboard?.total_received ?? 0) - (cfDashboard?.total_invested ?? 0)
    return cryptoPnl + cfInterest
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

  // ============== Loading skeleton ==============

  if (isLoading && !metrics) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-10 w-48 bg-card rounded-xl" />
        <div className="h-48 bg-card rounded-2xl" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <SkeletonStatCard key={i} />
          ))}
        </div>
      </div>
    )
  }

  // ============== Error state ==============
  // Never render the net-worth surface at €0 on a failed fetch — that reads as
  // "your wealth is zero" and destroys trust. Show an explicit error + retry.
  if (metricsError && !metrics) {
    return (
      <EmptyState
        variant="error"
        className="mx-auto mt-10 max-w-lg"
        title="Impossible de charger votre patrimoine"
        description="Une erreur réseau est survenue. Vos données sont en sécurité — réessayez."
        action={<Button onClick={() => refetchMetrics()}>Réessayer</Button>}
      />
    )
  }

  // ============== Render ==============

  return (
    <motion.div
      className="space-y-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl font-medium tracking-tight">Patrimoine global</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Où en est ton histoire patrimoniale aujourd'hui.
          </p>
        </div>
        <motion.div className="flex gap-1 bg-muted rounded-lg p-1">
          {PERIOD_OPTIONS.map((opt) => (
            <motion.div key={opt.value} whileTap={{ scale: 0.95 }}>
              <Button
                variant={selectedPeriod === opt.value ? 'default' : 'ghost'}
                size="sm"
                className="h-7 px-3 text-xs"
                onClick={() => setSelectedPeriod(opt.value)}
              >
                {opt.label}
              </Button>
            </motion.div>
          ))}
        </motion.div>
      </div>

      {/* Hero — Net Worth Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', duration: 0.6, bounce: 0.1 }}
        className="relative overflow-hidden rounded-lg border border-border bg-card p-6 md:p-8 elev-2"
      >
        <div className="relative flex flex-col sm:flex-row items-start sm:items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground tracking-widest uppercase mb-3">
              Patrimoine total
            </p>
            <AnimatedNumber
              value={netWorth}
              formatter={formatCurrency}
              className="block font-serif font-medium tabular-nums text-5xl md:text-6xl tracking-tight leading-none text-foreground"
            />
            <AnimatePresence mode="wait">
              <motion.div
                key={selectedPeriod}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 8 }}
                transition={{ duration: 0.2 }}
                className="mt-4"
              >
                <Badge
                  variant="outline"
                  className={
                    isPositive
                      ? 'text-gain border-gain/30 bg-gain/10'
                      : 'text-loss border-loss/30 bg-loss/10'
                  }
                >
                  {isPositive ? (
                    <ArrowUpRight className="h-3 w-3 mr-1" />
                  ) : (
                    <ArrowDownRight className="h-3 w-3 mr-1" />
                  )}
                  <span className="tabular">{formatPercent(change.percent)}</span>
                  <span className="ml-1 opacity-60">({formatCurrency(change.amount)})</span>
                </Badge>
              </motion.div>
            </AnimatePresence>

            {/* Résumé narratif — le récit avant le tableau */}
            {narrative && (
              <p className="mt-4 max-w-prose text-sm leading-relaxed text-muted-foreground">
                {narrative}
              </p>
            )}
          </div>

          {cfDashboard && cfDashboard.active_count + cfDashboard.completed_count > 0 && (
            <div className="text-right text-sm text-muted-foreground shrink-0">
              <p className="text-xs uppercase tracking-widest mb-1 opacity-50">dont crowdfunding</p>
              <p className="tabular font-medium text-foreground">{formatCurrency(cfDashboard.total_invested)}</p>
            </div>
          )}
        </div>
      </motion.div>

      {/* KPI Row */}
      <SpotlightGroup>
      <motion.div
        className="grid gap-3 grid-cols-2 lg:grid-cols-4"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {/* Total Investi */}
        <motion.div variants={kpiVariants}>
          <div className="spot-card elev-1 rounded-lg border border-border bg-card p-4 hover:bg-muted/40 transition-colors cursor-default">
            <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
              <Wallet className="h-3.5 w-3.5" />
              <span className="uppercase tracking-wide">Total investi</span>
            </div>
            <AnimatedNumber
              value={totalInvested}
              formatter={formatCurrency}
              className="text-xl font-semibold tabular tracking-tight"
            />
          </div>
        </motion.div>

        {/* P&L Net */}
        <motion.div variants={kpiVariants}>
          <div className="spot-card elev-1 rounded-lg border border-border bg-card p-4 hover:bg-muted/40 transition-colors cursor-default">
            <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
              {pnl >= 0 ? (
                <TrendingUp className="h-3.5 w-3.5 text-gain" />
              ) : (
                <TrendingDown className="h-3.5 w-3.5 text-loss" />
              )}
              <span className="uppercase tracking-wide">P&L Net</span>
            </div>
            <AnimatedNumber
              value={pnl}
              formatter={formatCurrency}
              className={`text-xl font-semibold tabular tracking-tight ${
                pnl >= 0 ? 'text-gain' : 'text-loss'
              }`}
            />
          </div>
        </motion.div>

        {/* Rendement annualisé */}
        <motion.div variants={kpiVariants}>
          <div className="spot-card elev-1 rounded-lg border border-border bg-card p-4 hover:bg-muted/40 transition-colors cursor-default">
            <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
              <BarChart3 className="h-3.5 w-3.5" />
              <span className="uppercase tracking-wide">Rendement annualisé</span>
            </div>
            <AnimatedNumber
              value={blendedReturn}
              formatter={formatPercent}
              className={`text-xl font-semibold tabular tracking-tight ${
                blendedReturn >= 0 ? 'text-gain' : 'text-loss'
              }`}
            />
          </div>
        </motion.div>

        {/* Liquidités */}
        <motion.div variants={kpiVariants}>
          <div className="spot-card elev-1 rounded-lg border border-border bg-card p-4 hover:bg-muted/40 transition-colors cursor-default">
            <div className="flex items-center gap-2 text-muted-foreground text-xs mb-2">
              <Banknote className="h-3.5 w-3.5" />
              <span className="uppercase tracking-wide">Liquidités</span>
            </div>
            <AnimatedNumber
              value={metrics?.available_liquidity ?? 0}
              formatter={formatCurrency}
              className="text-xl font-semibold tabular tracking-tight"
            />
          </div>
        </motion.div>
      </motion.div>
      </SpotlightGroup>

      {/* Charts Row */}
      <motion.div
        className="grid gap-6 lg:grid-cols-2"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {/* Allocation Pie */}
        <motion.div variants={kpiVariants}>
          <Card elevation="raised">
            <CardHeader>
              <CardTitle>Allocation Globale</CardTitle>
            </CardHeader>
            <CardContent>
              <AllocationChart data={mergedAllocation} />
            </CardContent>
          </Card>
        </motion.div>

        {/* Performance Line */}
        <motion.div variants={kpiVariants}>
          <Card elevation="raised">
            <CardHeader>
              <CardTitle>Performance du Capital</CardTitle>
            </CardHeader>
            <CardContent>
              {metrics?.historical_data && metrics.historical_data.length > 0 ? (
                <Suspense
                  fallback={
                    <div className="h-[300px] flex items-center justify-center text-muted-foreground text-sm">
                      Chargement du graphique…
                    </div>
                  }
                >
                  <PortfolioAreaChart
                    data={metrics.historical_data}
                    period={selectedPeriod || 365}
                  />
                </Suspense>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-muted-foreground text-sm">
                  Aucune donnée historique
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>

      {/* Attention + Quick Actions row */}
      <motion.div
        className="grid gap-6 lg:grid-cols-2"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {/* Points d'Attention */}
        <motion.div variants={kpiVariants}>
          <Card elevation="raised">
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
                    <motion.div
                      // Identity key (not index) so re-orders/inserts don't
                      // re-mount neighbouring rows mid-animation and rebind
                      // motion state to the wrong item.
                      key={`${item.type}:${item.title}:${item.detail}`}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.07, type: 'spring', duration: 0.4, bounce: 0.1 }}
                      className="flex items-start gap-3 p-3 rounded-lg bg-muted/50 border border-border/30"
                    >
                      {item.type === 'redflag' && (
                        <AlertTriangle className="h-4 w-4 text-loss shrink-0 mt-0.5" strokeWidth={1.5} />
                      )}
                      {item.type === 'alert' && (
                        <Bell className="h-4 w-4 text-warning shrink-0 mt-0.5" strokeWidth={1.5} />
                      )}
                      {item.type === 'event' && (
                        <Calendar className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" strokeWidth={1.5} />
                      )}
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{item.title}</p>
                        <p className="text-xs text-muted-foreground truncate">{item.detail}</p>
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>

        {/* Quick Actions */}
        <motion.div variants={kpiVariants}>
          <Card elevation="raised">
            <CardHeader>
              <CardTitle>Raccourcis</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <motion.div whileTap={{ scale: 0.98 }}>
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3 h-12 border-border/50 hover:border-border"
                  onClick={() => navigate('/crowdfunding/audit-lab')}
                >
                  <ShieldCheck className="h-5 w-5 text-accent" strokeWidth={1.5} />
                  <div className="text-left">
                    <p className="font-medium text-sm">Nouvel Audit</p>
                    <p className="text-xs text-muted-foreground">Analyser un projet crowdfunding</p>
                  </div>
                </Button>
              </motion.div>
              <motion.div whileTap={{ scale: 0.98 }}>
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3 h-12 border-border/50 hover:border-border"
                  onClick={() => navigate('/intelligence?tab=predictions')}
                >
                  <Crosshair className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
                  <div className="text-left">
                    <p className="font-medium text-sm">Signaux Alpha</p>
                    <p className="text-xs text-muted-foreground">Top opportunités crypto</p>
                  </div>
                </Button>
              </motion.div>
              <motion.div whileTap={{ scale: 0.98 }}>
                <Button
                  variant="outline"
                  className="w-full justify-start gap-3 h-12 border-border/50 hover:border-border"
                  onClick={() => navigate('/strategy?tab=simulations')}
                >
                  <PiggyBank className="h-5 w-5 text-muted-foreground" strokeWidth={1.5} />
                  <div className="text-left">
                    <p className="font-medium text-sm">Simuler DCA</p>
                    <p className="text-xs text-muted-foreground">Projeter vos dépôts de 300 €/mois</p>
                  </div>
                </Button>
              </motion.div>
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>
    </motion.div>
  )
}
