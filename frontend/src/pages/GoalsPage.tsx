import { useState, useCallback, useEffect, useRef, useId, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Slider } from '@/components/ui/slider'
import EmptyState from '@/components/ui/empty-state'
import { formatCurrency } from '@/lib/utils'
import { goalsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/hooks/use-toast'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import {
  Plus,
  Target,
  Loader2,
  Trash2,
  RefreshCw,
  Calendar,
  TrendingUp,
  CheckCircle2,
  AlertTriangle,
  Shield,
  BarChart3,
  PiggyBank,
} from 'lucide-react'

// ── Types ──────────────────────────────────────────────────────

interface Goal {
  id: string
  goal_type: string
  name: string
  target_amount: number
  current_amount: number
  currency: string
  target_date: string | null
  deadline_date: string | null
  priority: string
  strategy_type: string
  status: string
  icon: string
  color: string
  notes: string | null
  is_resilient: boolean
  progress_percent: number
  days_remaining: number | null
  monthly_needed: number | null
  created_at: string
}

interface ProjectionPoint {
  month: number
  date_label: string
  projected_p50: number
  projected_p25: number
  projected_p75: number
  target_line: number
}

interface GoalProjection {
  goal_id: string
  current_amount: number
  target_amount: number
  months_remaining: number
  rmc: number
  rmc_with_returns: number
  probability_on_track: number
  probability_label: string
  alert_message: string | null
  regime_label: string
  strategy_type: string
  gold_shield_active: boolean
  eta_date: string | null
  eta_months: number
  gold_shield_advice: string | null
  curve: ProjectionPoint[]
}

// ── Helpers ────────────────────────────────────────────────────

const probBadge = (label: string) => {
  if (label === 'Forte')
    return <Badge className="bg-gain/15 text-gain border-gain/30">Probabilité : Forte</Badge>
  if (label === 'Moyenne')
    return <Badge className="bg-warning/15 text-warning border-warning/30">Probabilité : Moyenne</Badge>
  return <Badge className="bg-loss/15 text-loss border-loss/30">Probabilité : Faible</Badge>
}

const priorityBadge = (p: string) => {
  if (p === 'high') return <Badge variant="destructive" className="text-[10px] px-1.5">Haute</Badge>
  if (p === 'low') return <Badge variant="outline" className="text-[10px] px-1.5">Basse</Badge>
  return null
}

const strategyLabel = (s: string) => {
  if (s === 'aggressive') return 'Agressif'
  if (s === 'conservative') return 'Conservateur'
  return 'Modéré'
}

/** Accept either a raw color (hex) or an `oklch(var(--token))` string and resolve to rgb. */
function resolveColor(input: string, colorFn: (name: string) => string): string {
  const m = input.match(/var\((--[\w-]+)\)/)
  return m ? colorFn(m[1]) : input
}

// ── Projection Chart Component with DCA Slider ──────────────────

function ProjectionChart({ goalId, color }: { goalId: string; color: string }) {
  const [dcaAmount, setDcaAmount] = useState(0)
  const [debouncedDca, setDebouncedDca] = useState(0)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const userTouched = useRef(false)

  const { data, isLoading, isFetching } = useQuery<GoalProjection>({
    queryKey: ['goals', 'projection', goalId, debouncedDca],
    queryFn: () => goalsApi.projection(goalId, debouncedDca),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  })

  // Défaut du slider = mensualité requise calculée par le backend
  // (rmc_with_returns) — plus de « 43 € » magique déconnecté de l'objectif.
  useEffect(() => {
    if (!userTouched.current && data && data.rmc_with_returns > 0 && dcaAmount === 0) {
      const suggested = Math.max(1, Math.round(data.rmc_with_returns))
      setDcaAmount(suggested)
      setDebouncedDca(suggested)
    }
  }, [data, dcaAmount])

  const handleSliderChange = useCallback((value: number[]) => {
    userTouched.current = true
    setDcaAmount(value[0])
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => setDebouncedDca(value[0]), 300)
  }, [])

  useEffect(() => {
    return () => { if (debounceTimer.current) clearTimeout(debounceTimer.current) }
  }, [])

  const uid = useId().replace(/:/g, '')
  const { theme, color: tokenColor } = useNivoTheme()
  const lineColor = resolveColor(color, tokenColor)
  const targetColor = tokenColor('--muted-foreground')

  const curve = useMemo(() => data?.curve ?? [], [data?.curve])

  const series = useMemo<LineSeries[]>(
    () => [
      { id: 'projected_p50', data: curve.map((d) => ({ x: d.date_label, y: d.projected_p50 })) },
      { id: 'target_line', data: curve.map((d) => ({ x: d.date_label, y: d.target_line })) },
    ],
    [curve]
  )

  // ~6 evenly spaced x labels regardless of point count.
  const tickValues = useMemo(() => {
    if (curve.length === 0) return []
    const target = Math.min(6, curve.length)
    const step = Math.max(1, Math.floor(curve.length / target))
    return curve.filter((_, i) => i % step === 0).map((d) => d.date_label)
  }, [curve])

  if (isLoading && !data) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }
  if (!data || data.curve.length === 0) return null

  // Custom layer: p25→p75 confidence band, drawn with the chart's own scales.
  const ConfidenceBand = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
    const x = (i: number) => xScale(curve[i].date_label as never) as number
    const top = curve.map((d, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${yScale(d.projected_p75 as never)}`)
    const bottom = curve
      .map((d, i) => `L${x(i)},${yScale(d.projected_p25 as never)}`)
      .reverse()
    return <path d={`${top.join(' ')} ${bottom.join(' ')} Z`} fill={lineColor} fillOpacity={0.12} stroke="none" />
  }

  return (
    <div className="space-y-3">
      {/* DCA Slider — What-if */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label className="text-xs text-muted-foreground">DCA mensuel</Label>
          <span className="text-sm font-semibold">{formatCurrency(dcaAmount)}/mois</span>
        </div>
        <Slider
          value={[dcaAmount]}
          onValueChange={handleSliderChange}
          min={0}
          max={500}
          step={5}
          className="w-full"
        />
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>0 €</span>
          <span>500 €</span>
        </div>
      </div>

      {/* Probability + ETA + RMC row */}
      <div className="flex items-center gap-3 flex-wrap">
        {probBadge(data.probability_label)}
        {data.gold_shield_active && (
          <Badge className="bg-warning/15 text-warning border-warning/30 gap-1">
            <Shield className="h-3 w-3" />
            Gold Shield
          </Badge>
        )}
        {data.eta_date && (
          <Badge variant="outline" className="gap-1 text-[10px]">
            <Calendar className="h-3 w-3" />
            ETA : {data.eta_date}
          </Badge>
        )}
        <span className="text-xs text-muted-foreground">
          {isFetching ? '...' : `Régime : ${data.regime_label} · RMC : ${formatCurrency(data.rmc_with_returns)}/mois`}
        </span>
      </div>

      {/* Alert message */}
      {data.alert_message && (
        <div className="flex items-start gap-2 text-xs bg-warning/10 border border-warning/20 rounded-lg p-2.5">
          <AlertTriangle className="h-3.5 w-3.5 text-warning mt-0.5 shrink-0" />
          <span className="text-warning">{data.alert_message}</span>
        </div>
      )}

      {/* Gold Shield advice — garde-fou prob < 50% en Bear */}
      {data.gold_shield_advice && (
        <div className="flex items-start gap-2 text-xs bg-warning/10 border border-warning/20 rounded-lg p-2.5">
          <Shield className="h-3.5 w-3.5 text-warning mt-0.5 shrink-0" />
          <span className="text-warning">{data.gold_shield_advice}</span>
        </div>
      )}

      {/* Area Chart */}
      <div className="h-[220px]">
        <ResponsiveLine
          data={series}
          theme={theme}
          margin={{ top: 8, right: 12, bottom: 28, left: 48 }}
          xScale={{ type: 'point' }}
          yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
          curve="monotoneX"
          colors={(s) => (s.id === 'target_line' ? targetColor : lineColor)}
          lineWidth={2}
          enablePoints={false}
          enableGridX={false}
          enableArea
          areaOpacity={1}
          defs={[
            {
              id: `grad-${uid}`,
              type: 'linearGradient',
              colors: [
                { offset: 0, color: lineColor, opacity: 0.3 },
                { offset: 100, color: lineColor, opacity: 0.05 },
              ],
            },
            {
              id: `transparent-${uid}`,
              type: 'linearGradient',
              colors: [
                { offset: 0, color: lineColor, opacity: 0 },
                { offset: 100, color: lineColor, opacity: 0 },
              ],
            },
          ]}
          fill={[
            { match: { id: 'projected_p50' }, id: `grad-${uid}` },
            { match: { id: 'target_line' }, id: `transparent-${uid}` },
          ]}
          axisBottom={{ tickSize: 0, tickPadding: 8, tickValues }}
          axisLeft={{
            tickSize: 0,
            tickPadding: 6,
            format: (v) => ((v as number) >= 1000 ? `${((v as number) / 1000).toFixed(1)}k` : `${v}`),
          }}
          layers={[
            'grid',
            'markers',
            'areas',
            ConfidenceBand,
            'lines',
            'slices',
            'axes',
            'points',
            'mesh',
          ]}
          enableSlices="x"
          sliceTooltip={({ slice }) => {
            const x = slice.points[0]?.data.x as string
            const point = curve.find((d) => d.date_label === x)
            if (!point) return null
            const rows: Array<{ label: string; value: number; color: string }> = [
              { label: 'Projection médiane', value: point.projected_p50, color: lineColor },
              { label: 'P75 (optimiste)', value: point.projected_p75, color: lineColor },
              { label: 'P25 (pessimiste)', value: point.projected_p25, color: lineColor },
              { label: 'Cible', value: point.target_line, color: targetColor },
            ]
            return (
              <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                <p className="mb-1.5 text-xs text-muted-foreground">{x}</p>
                {rows.map((r) => (
                  <div key={r.label} className="flex items-center justify-between gap-4">
                    <span className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: r.color }} />
                      <span className="text-xs text-muted-foreground">{r.label}</span>
                    </span>
                    <span className="font-mono text-sm tabular-nums">{formatCurrency(r.value)}</span>
                  </div>
                ))}
              </div>
            )
          }}
          animate
          motionConfig="gentle"
        />
      </div>
    </div>
  )
}

// ── Scenario Comparison (300€/month) ──────────────────────────

const STRATEGY_PARAMS: Record<string, { label: string; returnPct: number; allocation: string; color: string }> = {
  conservative: { label: 'Conservateur', returnPct: 5, allocation: '80% Or/Stables · 20% BTC', color: 'oklch(var(--chart-5))' },
  moderate: { label: 'Modéré', returnPct: 8, allocation: '40% Or/Stables · 60% Alpha', color: 'oklch(var(--chart-2))' },
  aggressive: { label: 'Agressif', returnPct: 12, allocation: '10% Stables · 90% Alpha', color: 'oklch(var(--chart-1))' },
}

function monthsToTarget(current: number, target: number, monthlyDca: number, annualReturn: number): number {
  if (current >= target) return 0
  if (monthlyDca <= 0 && annualReturn <= 0) return Infinity
  const r = annualReturn / 12
  if (r <= 0) return Math.ceil((target - current) / monthlyDca)
  // FV = current*(1+r)^n + dca*((1+r)^n - 1)/r = target
  // Solve iteratively
  let balance = current
  for (let m = 1; m <= 600; m++) {
    balance = balance * (1 + r) + monthlyDca
    if (balance >= target) return m
  }
  return 600
}

function ScenarioCard({ goal }: { goal: Goal }) {
  const monthlyDca = 300
  const strategies = ['conservative', 'moderate', 'aggressive'] as const

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground font-medium">
        Scénarios avec {formatCurrency(monthlyDca)}/mois de DCA
      </p>
      <div className="grid grid-cols-3 gap-2">
        {strategies.map((s) => {
          const params = STRATEGY_PARAMS[s]
          const months = monthsToTarget(goal.current_amount, goal.target_amount, monthlyDca, params.returnPct / 100)
          const years = Math.floor(months / 12)
          const remainingMonths = months % 12
          const etaLabel = months >= 600 ? '>50 ans' : years > 0 ? `${years}a ${remainingMonths}m` : `${months}m`
          const isActive = goal.strategy_type === s

          return (
            <div
              key={s}
              className={`rounded-lg border p-2.5 text-center space-y-1 ${
                isActive ? 'border-primary bg-primary/5' : 'border-border/50 bg-muted/30'
              }`}
            >
              <p className="text-[10px] font-semibold" style={{ color: params.color }}>{params.label}</p>
              <p className="text-lg font-bold">{etaLabel}</p>
              <p className="text-[9px] text-muted-foreground leading-tight">{params.allocation}</p>
              <p className="text-[10px] text-muted-foreground">~{params.returnPct}%/an</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────

export default function GoalsPage() {
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Goal | null>(null)
  const [expandedGoal, setExpandedGoal] = useState<string | null>(null)
  const [syncingGoals, setSyncingGoals] = useState<Set<string>>(new Set())

  // Form state
  const [goalType, setGoalType] = useState('asset')
  const [name, setName] = useState('')
  const [targetAmount, setTargetAmount] = useState('')
  const [deadlineDate, setDeadlineDate] = useState('')
  const [priority, setPriority] = useState('medium')
  const [strategyType, setStrategyType] = useState('moderate')
  // Hex uniquement : le backend valide max_length=7 — l'ancien défaut
  // `oklch(var(--chart-2))` (21 caractères) faisait échouer la création en 422
  // si l'utilisateur ne touchait pas au color-picker.
  const [color, setColor] = useState('#34d399')

  const { data: goals = [], isLoading } = useQuery<Goal[]>({
    queryKey: queryKeys.goals.list,
    queryFn: goalsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: goalsApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.goals.all })
      toast({ title: 'Objectif créé' })
      setShowAdd(false)
      setGoalType('asset')
      setName('')
      setTargetAmount('')
      setDeadlineDate('')
      setPriority('medium')
      setStrategyType('moderate')
    },
    onError: (error: unknown) => {
      const axiosErr = error as { response?: { data?: { detail?: string } } }
      const detail = axiosErr?.response?.data?.detail || "Impossible de créer l'objectif"
      toast({ variant: 'destructive', title: 'Erreur', description: detail })
    },
  })

  const syncMutation = useMutation({
    mutationFn: (id: string) => goalsApi.sync(id),
    onMutate: (id) => {
      setSyncingGoals((prev) => new Set(prev).add(id))
    },
    onSettled: (_, __, id) => {
      setSyncingGoals((prev) => { const next = new Set(prev); next.delete(id); return next })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.goals.all })
      toast({ title: 'Objectif synchronisé avec le portefeuille' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: "Impossible de synchroniser l'objectif" })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => goalsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.goals.all })
      toast({ title: 'Objectif supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: "Impossible de supprimer l'objectif" })
    },
  })

  const handleCreate = () => {
    if (!name || !targetAmount) return
    createMutation.mutate({
      name,
      goal_type: goalType,
      target_amount: parseFloat(targetAmount),
      deadline_date: deadlineDate || undefined,
      priority,
      strategy_type: goalType === 'savings' ? 'conservative' : strategyType,
      color,
    })
  }

  const activeGoals = goals.filter((g) => g.status === 'active')
  const reachedGoals = goals.filter((g) => g.status === 'reached')

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-serif font-medium">Wealth Journey</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Objectifs financiers avec projections intelligentes
          </p>
        </div>
        <Dialog open={showAdd} onOpenChange={setShowAdd}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Nouvel objectif
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Nouvel objectif</DialogTitle>
              <DialogDescription>Définissez un objectif financier avec stratégie et échéance</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label htmlFor="goal-type">Type d'objectif</Label>
                <Select value={goalType} onValueChange={setGoalType}>
                  <SelectTrigger id="goal-type"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="asset">Investissement (actifs risqués)</SelectItem>
                    <SelectItem value="savings">Épargne de Sécurité (cash/stables)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="goal-name">Nom</Label>
                <Input id="goal-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={goalType === 'savings' ? "Ex: Fonds d'urgence 3 mois" : "Ex: 100k€ de patrimoine"} />
              </div>
              <div>
                <Label htmlFor="goal-target-amount">Montant cible (€)</Label>
                <Input id="goal-target-amount" type="number" value={targetAmount} onChange={(e) => setTargetAmount(e.target.value)} placeholder="100000" />
              </div>
              <div>
                <Label htmlFor="goal-deadline">Date limite</Label>
                <Input id="goal-deadline" type="date" value={deadlineDate} onChange={(e) => setDeadlineDate(e.target.value)} />
              </div>
              <div className={`grid gap-3 ${goalType === 'savings' ? 'grid-cols-1' : 'grid-cols-2'}`}>
                <div>
                  <Label htmlFor="goal-priority">Priorité</Label>
                  <Select value={priority} onValueChange={setPriority}>
                    <SelectTrigger id="goal-priority"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Basse</SelectItem>
                      <SelectItem value="medium">Moyenne</SelectItem>
                      <SelectItem value="high">Haute</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {goalType !== 'savings' && (
                  <div>
                    <Label htmlFor="goal-strategy">Stratégie</Label>
                    <Select value={strategyType} onValueChange={setStrategyType}>
                      <SelectTrigger id="goal-strategy"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="conservative">Conservateur</SelectItem>
                        <SelectItem value="moderate">Modéré</SelectItem>
                        <SelectItem value="aggressive">Agressif</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
              {goalType === 'savings' && (
                <p className="text-xs text-muted-foreground">
                  Les objectifs d'épargne utilisent une stratégie conservatrice et ne comptent que la liquidité (cash, stablecoins).
                </p>
              )}
              <div>
                <Label htmlFor="goal-color">Couleur</Label>
                <Input id="goal-color" type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-10 w-20" />
              </div>
              <Button onClick={handleCreate} disabled={createMutation.isPending} className="w-full">
                {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                Créer
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Empty state */}
      {goals.length === 0 ? (
        <EmptyState
          icon={Target}
          title="Ton parcours commence ici"
          description="Fixe un premier objectif — une maison, une retraite, un coussin de sécurité — et suis chaque pas qui t'en rapproche."
          action={
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Créer mon premier objectif
            </Button>
          }
        />
      ) : (
        <>
          {/* Active Goals — Progress Cards */}
          {activeGoals.length > 0 && (
            <div className="space-y-4">
              {activeGoals.map((goal) => {
                const isExpanded = expandedGoal === goal.id
                return (
                  <Card key={goal.id} elevation="raised" className="overflow-hidden">
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center justify-between text-base">
                        <span className="flex items-center gap-2">
                          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: goal.color }} />
                          {goal.goal_type === 'savings' && <PiggyBank className="h-4 w-4 text-warning" />}
                          {goal.name}
                          {goal.goal_type === 'savings' && (
                            <Badge variant="outline" className="text-[10px] px-1.5 border-warning/30 text-warning">Épargne</Badge>
                          )}
                          {goal.is_resilient && (
                            <Badge variant="outline" className="text-[10px] px-1.5 border-warning/30 text-warning gap-0.5">
                              <Shield className="h-2.5 w-2.5" />
                              Résilient
                            </Badge>
                          )}
                          {priorityBadge(goal.priority)}
                          <span className="text-xs font-normal text-muted-foreground">
                            {strategyLabel(goal.strategy_type)}
                          </span>
                        </span>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            onClick={() => setExpandedGoal(isExpanded ? null : goal.id)}
                          >
                            <BarChart3 className="h-3 w-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0"
                            onClick={() => syncMutation.mutate(goal.id)}
                          >
                            <RefreshCw className={`h-3 w-3 ${syncingGoals.has(goal.id) ? 'animate-spin' : ''}`} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-destructive"
                            onClick={() => setDeleteTarget(goal)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </div>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {/* Progress bar */}
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="font-medium">{formatCurrency(goal.current_amount)}</span>
                          <span className="text-muted-foreground">{formatCurrency(goal.target_amount)}</span>
                        </div>
                        <div className="h-3 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${Math.min(goal.progress_percent, 100)}%`,
                              backgroundColor: goal.color,
                            }}
                          />
                        </div>
                        <div className="flex justify-between mt-1">
                          <p className="text-xs text-muted-foreground">{goal.progress_percent}%</p>
                        </div>
                      </div>

                      {/* Metrics row */}
                      <div className="flex gap-4 text-xs text-muted-foreground">
                        {goal.days_remaining !== null && (
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {goal.days_remaining}j restants
                          </span>
                        )}
                        {goal.monthly_needed !== null && (
                          <span className="flex items-center gap-1">
                            <TrendingUp className="h-3 w-3" />
                            {formatCurrency(goal.monthly_needed)}/mois nécessaire
                          </span>
                        )}
                      </div>

                      {/* Expandable projection chart + scenarios */}
                      {isExpanded && (
                        <div className="pt-2 border-t border-border/50 space-y-4">
                          <ScenarioCard goal={goal} />
                          <ProjectionChart goalId={goal.id} color={goal.color} />
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}

          {/* Reached Goals */}
          {reachedGoals.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
                <CheckCircle2 className="h-5 w-5 text-gain" />
                Objectifs atteints
              </h2>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {reachedGoals.map((goal) => (
                  <Card key={goal.id} elevation="raised" className="opacity-75">
                    <CardContent className="pt-6">
                      <div className="flex items-center gap-3">
                        <div className="h-3 w-3 rounded-full bg-gain" />
                        <div>
                          <p className="font-medium">{goal.name}</p>
                          <p className="text-sm text-gain">{formatCurrency(goal.target_amount)} atteint</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cet objectif ?</AlertDialogTitle>
            <AlertDialogDescription>
              Vous êtes sur le point de supprimer l'objectif{' '}
              <strong>{deleteTarget?.name}</strong>. Cette action est irréversible.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteTarget) {
                  deleteMutation.mutate(deleteTarget.id)
                  setDeleteTarget(null)
                }
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
