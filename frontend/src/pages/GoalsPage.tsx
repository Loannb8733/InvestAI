import { useState, useCallback } from 'react'
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
import { formatCurrency } from '@/lib/utils'
import { goalsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/hooks/use-toast'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
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
    return <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">Probabilité : Forte</Badge>
  if (label === 'Moyenne')
    return <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/30">Probabilité : Moyenne</Badge>
  return <Badge className="bg-red-500/15 text-red-400 border-red-500/30">Probabilité : Faible</Badge>
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

// ── Projection Chart Component with DCA Slider ──────────────────

function ProjectionChart({ goalId, color }: { goalId: string; color: string }) {
  const [dcaAmount, setDcaAmount] = useState(43)

  const { data, isLoading, isFetching } = useQuery<GoalProjection>({
    queryKey: ['goals', 'projection', goalId, dcaAmount],
    queryFn: () => goalsApi.projection(goalId, dcaAmount),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  })

  const handleSliderChange = useCallback((value: number[]) => {
    setDcaAmount(value[0])
  }, [])

  if (isLoading && !data) {
    return (
      <div className="flex items-center justify-center h-48">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    )
  }
  if (!data || data.curve.length === 0) return null

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
          <Badge className="bg-yellow-500/15 text-yellow-400 border-yellow-500/30 gap-1">
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
        <div className="flex items-start gap-2 text-xs bg-amber-500/10 border border-amber-500/20 rounded-lg p-2.5">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400 mt-0.5 shrink-0" />
          <span className="text-amber-300">{data.alert_message}</span>
        </div>
      )}

      {/* Gold Shield advice — garde-fou prob < 50% en Bear */}
      {data.gold_shield_advice && (
        <div className="flex items-start gap-2 text-xs bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-2.5">
          <Shield className="h-3.5 w-3.5 text-yellow-400 mt-0.5 shrink-0" />
          <span className="text-yellow-300">{data.gold_shield_advice}</span>
        </div>
      )}

      {/* Area Chart */}
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data.curve} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`grad-${goalId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" className="stroke-muted/30" />
          <XAxis
            dataKey="date_label"
            tick={{ fontSize: 10 }}
            className="fill-muted-foreground"
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 10 }}
            className="fill-muted-foreground"
            tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${v}`}
          />
          <Tooltip
            contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 8, fontSize: 12 }}
            formatter={(value: number) => [formatCurrency(value), '']}
            labelStyle={{ color: 'hsl(var(--muted-foreground))' }}
          />
          <Area
            type="monotone"
            dataKey="projected_p75"
            stroke="none"
            fill={`url(#grad-${goalId})`}
            name="P75 (optimiste)"
          />
          <Area
            type="monotone"
            dataKey="projected_p25"
            stroke="none"
            fill="hsl(var(--card))"
            name="P25 (pessimiste)"
          />
          <Line
            type="monotone"
            dataKey="projected_p50"
            stroke={color}
            strokeWidth={2}
            dot={false}
            name="Projection médiane"
          />
          <Line
            type="monotone"
            dataKey="target_line"
            stroke="hsl(var(--muted-foreground))"
            strokeWidth={1}
            strokeDasharray="5 5"
            dot={false}
            name="Cible"
          />
          <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Scenario Comparison (300€/month) ──────────────────────────

const STRATEGY_PARAMS: Record<string, { label: string; returnPct: number; allocation: string; color: string }> = {
  conservative: { label: 'Conservateur', returnPct: 5, allocation: '80% Or/Stables · 20% BTC', color: '#3b82f6' },
  moderate: { label: 'Modéré', returnPct: 8, allocation: '40% Or/Stables · 60% Alpha', color: '#8b5cf6' },
  aggressive: { label: 'Agressif', returnPct: 12, allocation: '10% Stables · 90% Alpha', color: '#f59e0b' },
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

  // Form state
  const [goalType, setGoalType] = useState('asset')
  const [name, setName] = useState('')
  const [targetAmount, setTargetAmount] = useState('')
  const [deadlineDate, setDeadlineDate] = useState('')
  const [priority, setPriority] = useState('medium')
  const [strategyType, setStrategyType] = useState('moderate')
  const [color, setColor] = useState('#6366f1')

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
          <h1 className="text-3xl font-bold">Wealth Journey</h1>
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
                <Label>Type d'objectif</Label>
                <Select value={goalType} onValueChange={setGoalType}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="asset">Investissement (actifs risqués)</SelectItem>
                    <SelectItem value="savings">Épargne de Sécurité (cash/stables)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Nom</Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={goalType === 'savings' ? "Ex: Fonds d'urgence 3 mois" : "Ex: 100k€ de patrimoine"} />
              </div>
              <div>
                <Label>Montant cible (€)</Label>
                <Input type="number" value={targetAmount} onChange={(e) => setTargetAmount(e.target.value)} placeholder="100000" />
              </div>
              <div>
                <Label>Date limite</Label>
                <Input type="date" value={deadlineDate} onChange={(e) => setDeadlineDate(e.target.value)} />
              </div>
              <div className={`grid gap-3 ${goalType === 'savings' ? 'grid-cols-1' : 'grid-cols-2'}`}>
                <div>
                  <Label>Priorité</Label>
                  <Select value={priority} onValueChange={setPriority}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Basse</SelectItem>
                      <SelectItem value="medium">Moyenne</SelectItem>
                      <SelectItem value="high">Haute</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {goalType !== 'savings' && (
                  <div>
                    <Label>Stratégie</Label>
                    <Select value={strategyType} onValueChange={setStrategyType}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
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
                <Label>Couleur</Label>
                <Input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-10 w-20" />
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
        <Card>
          <CardContent className="py-12 text-center">
            <Target className="h-16 w-16 mx-auto text-muted-foreground mb-4" />
            <h2 className="text-xl font-semibold">Aucun objectif</h2>
            <p className="text-muted-foreground mt-2">
              Créez votre premier objectif financier pour suivre votre progression.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Active Goals — Progress Cards */}
          {activeGoals.length > 0 && (
            <div className="space-y-4">
              {activeGoals.map((goal) => {
                const isExpanded = expandedGoal === goal.id
                return (
                  <Card key={goal.id} className="overflow-hidden">
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center justify-between text-base">
                        <span className="flex items-center gap-2">
                          <div className="h-3 w-3 rounded-full" style={{ backgroundColor: goal.color }} />
                          {goal.goal_type === 'savings' && <PiggyBank className="h-4 w-4 text-amber-400" />}
                          {goal.name}
                          {goal.goal_type === 'savings' && (
                            <Badge variant="outline" className="text-[10px] px-1.5 border-amber-500/30 text-amber-400">Épargne</Badge>
                          )}
                          {goal.is_resilient && (
                            <Badge variant="outline" className="text-[10px] px-1.5 border-yellow-500/30 text-yellow-400 gap-0.5">
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
                            <RefreshCw className={`h-3 w-3 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
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
                <CheckCircle2 className="h-5 w-5 text-green-500" />
                Objectifs atteints
              </h2>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {reachedGoals.map((goal) => (
                  <Card key={goal.id} className="opacity-75">
                    <CardContent className="pt-6">
                      <div className="flex items-center gap-3">
                        <div className="h-3 w-3 rounded-full bg-green-500" />
                        <div>
                          <p className="font-medium">{goal.name}</p>
                          <p className="text-sm text-green-500">{formatCurrency(goal.target_amount)} atteint</p>
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
