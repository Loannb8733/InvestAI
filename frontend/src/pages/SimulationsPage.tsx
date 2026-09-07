import { Fragment, useState, useEffect, useMemo, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { Badge, type BadgeProps } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import QueryErrorState from '@/components/ui/query-error-state'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useToast } from '@/hooks/use-toast'
import { simulationsApi, dashboardApi, analyticsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import { useAuthStore } from '@/stores/authStore'
import { formatCurrency as formatCurrencyBase } from '@/lib/utils'
import {
  Loader2,
  Calculator,
  Flame,
  LineChart,
  BarChart3,
  Save,
  Trash2,
  Bookmark,
  ArrowLeftRight,
} from 'lucide-react'
import FireTab from '@/components/simulations/FireTab'
import DcaTab from '@/components/simulations/DcaTab'
import MonteCarloTab from '@/components/simulations/MonteCarloTab'
import ProjectionTab from '@/components/simulations/ProjectionTab'

import { INFLATION_BY_CURRENCY } from '@/components/simulations/inflation'
import type {
  FIREProbResult,
  ProjectionResult,
  DCAResult,
  MonteCarloData,
} from '@/types/simulations'


// ============ Scénarios sauvegardés ============

type ScenarioKind = 'fire' | 'projection' | 'montecarlo' | 'dca'

interface SavedScenario {
  id: string
  name: string
  description: string | null
  simulation_type: string
  parameters: {
    kind?: string
    inputs?: Record<string, unknown>
    results?: Record<string, unknown>
  }
  results: Record<string, unknown> | null
  created_at: string
}

// L'enum backend SimulationType n'a pas de valeur « montecarlo » : les scénarios
// Monte Carlo sont persistés en simulation_type "projection" et discriminés côté
// front via parameters.kind (le champ parameters est un Dict[str, Any] libre).
const BACKEND_TYPE_BY_KIND: Record<ScenarioKind, string> = {
  fire: 'fire',
  projection: 'projection',
  montecarlo: 'projection',
  dca: 'dca',
}

const SCENARIO_KIND_META: Record<ScenarioKind, { label: string; badge: BadgeProps['variant'] }> = {
  fire: { label: 'FIRE', badge: 'warning' },
  projection: { label: 'Projection', badge: 'accent' },
  montecarlo: { label: 'Monte Carlo', badge: 'secondary' },
  dca: { label: 'DCA', badge: 'gain' },
}

const FREQUENCY_LABELS: Record<string, string> = {
  weekly: 'Hebdomadaire',
  monthly: 'Mensuel',
  quarterly: 'Trimestriel',
}

type FieldFormat =
  | 'currency'
  | 'percent'
  | 'number'
  | 'years'
  | 'months'
  | 'days'
  | 'bool'
  | 'frequency'
  | 'raw'

interface ScenarioField {
  key: string
  label: string
  format: FieldFormat
}

const SCENARIO_FIELDS: Record<ScenarioKind, { params: ScenarioField[]; results: ScenarioField[] }> = {
  fire: {
    params: [
      { key: 'current_value', label: 'Valeur de départ', format: 'currency' },
      { key: 'monthly_contribution', label: 'Épargne mensuelle', format: 'currency' },
      { key: 'annual_expenses', label: 'Dépenses annuelles (retraite)', format: 'currency' },
      { key: 'expected_annual_return', label: 'Rendement annuel', format: 'percent' },
      { key: 'annual_volatility', label: 'Volatilité annuelle', format: 'percent' },
      { key: 'inflation_rate', label: 'Inflation', format: 'percent' },
      { key: 'withdrawal_rate', label: 'Taux de retrait', format: 'percent' },
      { key: 'index_contributions', label: 'Épargne indexée sur l’inflation', format: 'bool' },
      { key: 'years_horizon', label: 'Horizon', format: 'years' },
      { key: 'n_paths', label: 'Trajectoires simulées', format: 'number' },
      // Anciens scénarios (projection déterministe) — affichés si présents
      { key: 'current_portfolio_value', label: 'Valeur du portefeuille (ancien)', format: 'currency' },
      { key: 'monthly_expenses', label: 'Dépenses mensuelles (ancien)', format: 'currency' },
    ],
    results: [
      { key: 'prob_at_horizon', label: 'Prob. FIRE à l’horizon', format: 'percent' },
      { key: 'fire_year_p50', label: 'Année FIRE médiane', format: 'raw' },
      { key: 'fire_year_p10', label: 'Année FIRE optimiste (p10)', format: 'raw' },
      { key: 'fire_year_p90', label: 'Année FIRE prudente (p90)', format: 'raw' },
      { key: 'fire_number_today', label: 'Nombre FIRE (aujourd’hui)', format: 'currency' },
      { key: 'survival_prob_30y', label: 'Survie post-FIRE (30 ans)', format: 'percent' },
      { key: 'final_value_p50', label: 'Valeur finale médiane', format: 'currency' },
      // Anciens scénarios (projection déterministe) — affichés si présents
      { key: 'fire_number', label: 'Nombre FIRE (ancien)', format: 'currency' },
      { key: 'years_to_fire', label: 'Années restantes (ancien)', format: 'years' },
    ],
  },
  projection: {
    params: [
      { key: 'years', label: 'Horizon', format: 'years' },
      { key: 'expected_return', label: 'Rendement annuel', format: 'percent' },
      { key: 'expense_ratio', label: 'Frais annuels / TER', format: 'percent' },
      { key: 'monthly_contribution', label: 'Contribution mensuelle', format: 'currency' },
      { key: 'inflation_rate', label: 'Inflation', format: 'percent' },
    ],
    results: [
      { key: 'final_value', label: 'Valeur finale', format: 'currency' },
      { key: 'real_final_value', label: 'Valeur réelle (inflation)', format: 'currency' },
      { key: 'total_contributions', label: 'Contributions totales', format: 'currency' },
      { key: 'total_returns', label: 'Gains totaux', format: 'currency' },
    ],
  },
  montecarlo: {
    params: [
      { key: 'horizon', label: 'Horizon', format: 'days' },
      { key: 'annual_withdrawal_rate', label: 'Taux de retrait annuel', format: 'percent' },
      { key: 'ter_percentage', label: 'TER / Frais annuels', format: 'percent' },
      { key: 'monthly_withdrawal', label: 'Retrait mensuel', format: 'currency' },
    ],
    results: [
      { key: 'expected_return', label: 'Rendement attendu', format: 'percent' },
      { key: 'prob_positive', label: 'Prob. gain', format: 'percent' },
      { key: 'prob_loss_10', label: 'Prob. perte >10 %', format: 'percent' },
      { key: 'prob_ruin', label: 'Prob. ruine', format: 'percent' },
      { key: 'p5', label: 'P5 (pessimiste)', format: 'percent' },
      { key: 'p50', label: 'P50 (médian)', format: 'percent' },
      { key: 'p95', label: 'P95 (optimiste)', format: 'percent' },
    ],
  },
  dca: {
    params: [
      { key: 'total_amount', label: 'Montant total', format: 'currency' },
      { key: 'frequency', label: 'Fréquence', format: 'frequency' },
      { key: 'duration_months', label: 'Durée', format: 'months' },
      { key: 'expected_volatility', label: 'Volatilité attendue', format: 'percent' },
      { key: 'expected_return', label: 'Rendement attendu', format: 'percent' },
    ],
    results: [
      { key: 'total_invested', label: 'Total investi', format: 'currency' },
      { key: 'dca_p50', label: 'Médiane DCA', format: 'currency' },
      { key: 'dca_p10', label: 'DCA p10', format: 'currency' },
      { key: 'dca_p90', label: 'DCA p90', format: 'currency' },
      { key: 'lumpsum_p50', label: 'Médiane Lump Sum', format: 'currency' },
      { key: 'return_percent', label: 'Rendement DCA (médiane)', format: 'percent' },
      { key: 'prob_dca_beats_ls', label: 'Prob. DCA > Lump Sum', format: 'percent' },
    ],
  },
}

function scenarioKindOf(sim: SavedScenario): ScenarioKind {
  const k = sim.parameters?.kind
  if (k === 'fire' || k === 'projection' || k === 'montecarlo' || k === 'dca') return k
  if (sim.simulation_type === 'fire' || sim.simulation_type === 'projection' || sim.simulation_type === 'dca') {
    return sim.simulation_type
  }
  return 'projection'
}

const formatScenarioDate = (iso: string) =>
  new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })

export default function SimulationsPage() {
  const { toast } = useToast()
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState('fire')

  // Fetch live portfolio value
  const { data: dashboard } = useQuery({
    queryKey: queryKeys.dashboard.metrics(0),
    queryFn: () => dashboardApi.getMetrics(0),
  })

  const livePortfolioValue = dashboard?.total_value ?? 0
  const userCurrency = user?.preferredCurrency || 'EUR'

  // Delegate to the shared formatter so amounts keep their cents and stay
  // consistent with the rest of the app (the local version forced 0 decimals).
  const formatCurrency = (value: number) => formatCurrencyBase(value, userCurrency)

  // Auto-suggest inflation based on user currency
  const suggestedInflation = INFLATION_BY_CURRENCY[userCurrency]?.rate ?? 2.0

  // FIRE probabiliste — taux affichés en % (convertis en décimal à l'envoi).
  // null = laisser le backend pré-remplir depuis le profil investisseur.
  const [fireParams, setFireParams] = useState({
    current_portfolio_value: 0,
    monthly_contribution: null as number | null,
    monthly_expenses: 3000,
    expected_annual_return: null as number | null,
    annual_volatility: null as number | null,
    inflation_rate: suggestedInflation,
    withdrawal_rate: 4,
    index_contributions: true,
    years_horizon: 30,
  })
  const [fireResult, setFireResult] = useState<FIREProbResult | null>(null)

  // Projection state
  const [projectionParams, setProjectionParams] = useState({
    years: 10,
    expected_return: 7,
    expense_ratio: 0.25,
    monthly_contribution: 500,
    inflation_rate: suggestedInflation,
  })
  const [projectionResult, setProjectionResult] = useState<ProjectionResult | null>(null)

  // Monte Carlo state for projection tab
  const [mcParams, setMcParams] = useState({
    horizon: 365,
    annual_withdrawal_rate: 0,
    ter_percentage: 0.25,
    monthly_withdrawal: 0,
  })
  const [mcResult, setMcResult] = useState<MonteCarloData | null>(null)
  // Snapshot des paramètres réellement utilisés pour le dernier calcul MC
  // (les inputs peuvent changer après coup sans relancer la simulation).
  const [mcApplied, setMcApplied] = useState<typeof mcParams | null>(null)

  // DCA state
  const [dcaParams, setDcaParams] = useState({
    total_amount: 10000,
    frequency: 'monthly',
    duration_months: 12,
    expected_volatility: 20,
    expected_return: 7,
  })
  const [dcaResult, setDcaResult] = useState<DCAResult | null>(null)
  const prefillDone = useRef(false)

  // Pre-fill portfolio value once when dashboard data first loads
  useEffect(() => {
    if (!prefillDone.current && livePortfolioValue > 0) {
      prefillDone.current = true
      setFireParams((prev) =>
        prev.current_portfolio_value === 0
          ? { ...prev, current_portfolio_value: Math.round(livePortfolioValue * 100) / 100 }
          : prev
      )
    }
  }, [livePortfolioValue])

  // FIRE probabiliste : les champs null sont OMIS pour laisser le backend
  // appliquer les défauts du profil investisseur (echo dans defaults_from).
  const fireMutation = useMutation({
    mutationFn: (p: typeof fireParams): Promise<FIREProbResult> =>
      simulationsApi.fireProbabilistic({
        current_value: p.current_portfolio_value > 0 ? p.current_portfolio_value : undefined,
        monthly_contribution: p.monthly_contribution ?? undefined,
        annual_expenses: p.monthly_expenses * 12,
        withdrawal_rate: p.withdrawal_rate / 100,
        annual_return_mean:
          p.expected_annual_return !== null ? p.expected_annual_return / 100 : undefined,
        annual_volatility: p.annual_volatility !== null ? p.annual_volatility / 100 : undefined,
        inflation: p.inflation_rate / 100,
        index_contributions: p.index_contributions,
        years_horizon: p.years_horizon,
      }),
    onSuccess: (data) => {
      setFireResult(data)
      // Reflète dans les inputs les hypothèses réellement appliquées
      // (dont celles pré-remplies depuis le profil investisseur).
      const a = data.assumptions
      setFireParams((prev) => ({
        ...prev,
        current_portfolio_value: a.current_value,
        monthly_contribution: a.monthly_contribution,
        expected_annual_return: Math.round(a.annual_return_mean * 10000) / 100,
        annual_volatility: Math.round(a.annual_volatility * 10000) / 100,
      }))
      toast({ title: 'Simulation FIRE calculée' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de calculer le FIRE.' })
    },
  })


  // Projection mutation
  const projectionMutation = useMutation({
    mutationFn: simulationsApi.projectPortfolio,
    onSuccess: (data) => {
      setProjectionResult(data)
      toast({ title: 'Projection calculée' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de calculer la projection.' })
    },
  })

  // Monte Carlo mutation
  const mcMutation = useMutation({
    mutationFn: (params: typeof mcParams) =>
      analyticsApi.getMonteCarlo(
        params.horizon,
        undefined,
        params.annual_withdrawal_rate || undefined,
        params.ter_percentage || undefined,
        params.monthly_withdrawal || undefined,
      ),
    onSuccess: (data, variables) => {
      setMcResult(data)
      setMcApplied(variables)
      toast({ title: 'Simulation Monte Carlo calculée' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de calculer le Monte Carlo.' })
    },
  })

  // DCA mutation
  const dcaMutation = useMutation({
    mutationFn: simulationsApi.simulateDCA,
    onSuccess: (data) => {
      setDcaResult(data)
      toast({ title: 'Simulation DCA calculée' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de simuler le DCA.' })
    },
  })

  // ============ Scénarios enregistrés ============

  const queryClient = useQueryClient()
  const [saveKind, setSaveKind] = useState<ScenarioKind | null>(null)
  const [scenarioName, setScenarioName] = useState('')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [deleteTarget, setDeleteTarget] = useState<SavedScenario | null>(null)

  const { data: savedScenariosData, isLoading: scenariosLoading, error: scenariosError, refetch: refetchScenarios } = useQuery<SavedScenario[]>({
    queryKey: queryKeys.simulations.list,
    queryFn: () => simulationsApi.list(),
  })
  const savedScenarios = useMemo(() => savedScenariosData ?? [], [savedScenariosData])

  const saveMutation = useMutation({
    mutationFn: simulationsApi.save,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.simulations.all })
      setSaveKind(null)
      setScenarioName('')
      toast({ title: 'Scénario enregistré' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: "Impossible d'enregistrer le scénario." })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: simulationsApi.delete,
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.simulations.all })
      setSelectedIds((prev) => prev.filter((s) => s !== id))
      setDeleteTarget(null)
      toast({ title: 'Scénario supprimé' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de supprimer le scénario.' })
    },
  })

  // Construit le payload de sauvegarde : paramètres + résultats clés (scalaires
  // uniquement, pas les séries de projection) embarqués dans `parameters`.
  const buildScenarioPayload = (kind: ScenarioKind, name: string) => {
    let inputs: Record<string, unknown> | null = null
    let results: Record<string, unknown> | null = null

    if (kind === 'fire' && fireResult) {
      // Les hypothèses réellement appliquées (assumptions) font foi — pas les
      // inputs UI, qui peuvent avoir changé depuis le calcul. Taux stockés en %.
      const a = fireResult.assumptions
      inputs = {
        current_value: a.current_value,
        monthly_contribution: a.monthly_contribution,
        annual_expenses: a.annual_expenses,
        expected_annual_return: Math.round(a.annual_return_mean * 10000) / 100,
        annual_volatility: Math.round(a.annual_volatility * 10000) / 100,
        inflation_rate: Math.round(a.inflation * 10000) / 100,
        withdrawal_rate: Math.round(a.withdrawal_rate * 10000) / 100,
        index_contributions: a.index_contributions,
        years_horizon: a.years_horizon,
        n_paths: a.n_paths,
      }
      results = {
        prob_at_horizon: Math.round(fireResult.prob_at_horizon * 1000) / 10,
        fire_year_p10: fireResult.fire_year_p10,
        fire_year_p50: fireResult.fire_year_p50,
        fire_year_p90: fireResult.fire_year_p90,
        fire_number_today: fireResult.fire_number_today,
        survival_prob_30y: Math.round(fireResult.survival_prob_30y * 1000) / 10,
        final_value_p50: fireResult.final_value_p50,
      }
    } else if (kind === 'projection' && projectionResult) {
      inputs = { ...projectionParams }
      results = {
        final_value: projectionResult.final_value,
        real_final_value: projectionResult.real_final_value,
        total_contributions: projectionResult.total_contributions,
        total_returns: projectionResult.total_returns,
      }
    } else if (kind === 'montecarlo' && mcResult) {
      inputs = { ...(mcApplied ?? mcParams) }
      results = {
        expected_return: mcResult.expected_return,
        prob_positive: mcResult.prob_positive,
        prob_loss_10: mcResult.prob_loss_10,
        prob_ruin: mcResult.prob_ruin,
        p5: mcResult.percentiles.p5,
        p50: mcResult.percentiles.p50,
        p95: mcResult.percentiles.p95,
        simulations: mcResult.simulations,
        horizon_days: mcResult.horizon_days,
      }
    } else if (kind === 'dca' && dcaResult) {
      inputs = { ...dcaParams }
      results = {
        total_invested: dcaResult.total_invested,
        dca_p10: dcaResult.dca_p10,
        dca_p50: dcaResult.dca_p50,
        dca_p90: dcaResult.dca_p90,
        lumpsum_p10: dcaResult.lumpsum_p10,
        lumpsum_p50: dcaResult.lumpsum_p50,
        lumpsum_p90: dcaResult.lumpsum_p90,
        return_percent: dcaResult.return_percent,
        prob_dca_beats_ls: dcaResult.prob_dca_beats_ls,
        n_paths: dcaResult.n_paths,
      }
    }

    if (!inputs || !results) return null
    return {
      name,
      simulation_type: BACKEND_TYPE_BY_KIND[kind],
      parameters: { kind, inputs, results },
    }
  }

  const handleSaveScenario = () => {
    if (!saveKind) return
    const name = scenarioName.trim()
    if (!name) return
    const payload = buildScenarioPayload(saveKind, name)
    if (!payload) {
      toast({
        variant: 'destructive',
        title: 'Erreur',
        description: "Lancez d'abord un calcul avant de sauvegarder.",
      })
      return
    }
    saveMutation.mutate(payload)
  }

  const toggleScenarioSelection = (id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((s) => s !== id)
      if (prev.length >= 2) return prev
      return [...prev, id]
    })
  }

  const firstSelectedKind = useMemo(() => {
    if (selectedIds.length === 0) return null
    const first = savedScenarios.find((s) => s.id === selectedIds[0])
    return first ? scenarioKindOf(first) : null
  }, [selectedIds, savedScenarios])

  const comparison = useMemo(() => {
    if (selectedIds.length !== 2) return null
    const a = savedScenarios.find((s) => s.id === selectedIds[0])
    const b = savedScenarios.find((s) => s.id === selectedIds[1])
    if (!a || !b) return null
    const kind = scenarioKindOf(a)
    if (kind !== scenarioKindOf(b)) return null
    return { a, b, kind }
  }, [selectedIds, savedScenarios])

  const formatFieldValue = (value: unknown, format: FieldFormat): string => {
    if (value === null || value === undefined || value === '') return '—'
    switch (format) {
      case 'currency':
        return formatCurrency(Number(value))
      case 'percent':
        return `${Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %`
      case 'years':
        return `${value} an${Number(value) > 1 ? 's' : ''}`
      case 'months':
        return `${value} mois`
      case 'days':
        return `${value} jours`
      case 'bool':
        return value ? 'Oui' : 'Non'
      case 'frequency':
        return FREQUENCY_LABELS[String(value)] ?? String(value)
      case 'raw':
        return String(value)
      default:
        return Number(value).toLocaleString('fr-FR')
    }
  }

  // Build Monte Carlo fan data for chart

  // Comparaison DCA vs Lump Sum : les deux stratégies sont désormais simulées
  // côté backend SUR LES MÊMES trajectoires stochastiques (médiane + p10-p90).
  // Le calcul lump-sum déterministe local (composé certain) a été supprimé :
  // il comparait un chemin aléatoire à une courbe sans risque.

  return (
    <div className="space-y-6">
      <div>
        {/* h2 : cette page n'est montée que comme onglet de StrategyPage, dont
            le <h1> porte le titre. Deux <h1> sur une page cassent la hiérarchie
            que suivent les lecteurs d'écran (UX-02). */}
        <h2 className="text-3xl font-serif font-medium">Simulations</h2>
        <p className="text-muted-foreground">
          Calculateur FIRE probabiliste, projections Monte Carlo et simulations DCA.
          {livePortfolioValue > 0 && (
            <span className="ml-2 text-foreground font-medium">
              Portefeuille actuel : {formatCurrency(livePortfolioValue)}
            </span>
          )}
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="fire" className="flex items-center gap-2">
            <Flame className="h-4 w-4" />
            FIRE
          </TabsTrigger>
          <TabsTrigger value="projection" className="flex items-center gap-2">
            <LineChart className="h-4 w-4" />
            Projection
          </TabsTrigger>
          <TabsTrigger value="montecarlo" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Monte Carlo
          </TabsTrigger>
          <TabsTrigger value="dca" className="flex items-center gap-2">
            <Calculator className="h-4 w-4" />
            DCA
          </TabsTrigger>
        </TabsList>

        {/* FIRE Calculator */}
        <FireTab
          params={fireParams}
          setParams={setFireParams}
          resultat={fireResult}
          mutation={fireMutation}
          valeurPortefeuille={livePortfolioValue}
          formatCurrency={formatCurrency}
          userCurrency={userCurrency}
          onSauvegarder={() => setSaveKind('fire')}
        />

        {/* Portfolio Projection */}
        <ProjectionTab
          params={projectionParams}
          setParams={setProjectionParams}
          resultat={projectionResult}
          mutation={projectionMutation}
          formatCurrency={formatCurrency}
          userCurrency={userCurrency}
          onSauvegarder={() => setSaveKind('projection')}
        />

        {/* Monte Carlo */}
        <MonteCarloTab
          params={mcParams}
          setParams={setMcParams}
          resultat={mcResult}
          applique={mcApplied}
          mutation={mcMutation}
          formatCurrency={formatCurrency}
          onSauvegarder={() => setSaveKind('montecarlo')}
        />

        {/* DCA Simulator */}
        <DcaTab
          params={dcaParams}
          setParams={setDcaParams}
          resultat={dcaResult}
          mutation={dcaMutation}
          formatCurrency={formatCurrency}
          onSauvegarder={() => setSaveKind('dca')}
        />
      </Tabs>

      {/* ============ Scénarios enregistrés ============ */}
      <Card elevation="raised">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bookmark className="h-5 w-5 text-accent" />
            Scénarios enregistrés
          </CardTitle>
          <CardDescription>
            Sauvegardez vos calculs pour les retrouver plus tard, puis sélectionnez 2 scénarios du
            même type pour les comparer côte à côte.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {scenariosError ? (
            /* Avant le chargement et le vide : une requête en échec ne doit pas
               se lire comme « aucun scénario enregistré ». */
            <QueryErrorState
              error={scenariosError}
              onRetry={refetchScenarios}
              title="Impossible de charger les scénarios"
            />
          ) : scenariosLoading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Chargement des scénarios…
            </div>
          ) : savedScenarios.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              Aucun scénario enregistré pour le moment. Lancez un calcul puis cliquez sur
              «&nbsp;Sauvegarder ce scénario&nbsp;».
            </div>
          ) : (
            <div className="space-y-2">
              {savedScenarios.map((sim) => {
                const kind = scenarioKindOf(sim)
                const meta = SCENARIO_KIND_META[kind]
                const isSelected = selectedIds.includes(sim.id)
                const selectionDisabled =
                  !isSelected &&
                  (selectedIds.length >= 2 ||
                    (firstSelectedKind !== null && firstSelectedKind !== kind))
                return (
                  <div
                    key={sim.id}
                    className={`flex items-center gap-3 rounded-lg border p-3 transition-colors ${
                      isSelected ? 'border-accent/40 bg-accent/5' : 'border-border'
                    }`}
                  >
                    <Checkbox
                      checked={isSelected}
                      disabled={selectionDisabled}
                      onCheckedChange={() => toggleScenarioSelection(sim.id)}
                      aria-label={`Comparer « ${sim.name} »`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{sim.name}</p>
                      <p className="text-xs text-muted-foreground">
                        Enregistré le {formatScenarioDate(sim.created_at)}
                      </p>
                    </div>
                    <Badge variant={meta.badge}>{meta.label}</Badge>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleteTarget(sim)}
                      aria-label={`Supprimer « ${sim.name} »`}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </div>
                )
              })}
              {selectedIds.length === 1 && (
                <p className="pt-1 text-xs text-muted-foreground">
                  Sélectionnez un second scénario{' '}
                  {firstSelectedKind ? `de type ${SCENARIO_KIND_META[firstSelectedKind].label} ` : ''}
                  pour lancer la comparaison.
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Comparaison côte à côte */}
      {comparison && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ArrowLeftRight className="h-5 w-5 text-accent" />
              Comparaison de scénarios
              <Badge variant={SCENARIO_KIND_META[comparison.kind].badge}>
                {SCENARIO_KIND_META[comparison.kind].label}
              </Badge>
            </CardTitle>
            <CardDescription>
              Paramètres et résultats clés côte à côte — les valeurs qui diffèrent sont surlignées.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-64" />
                  <TableHead>{comparison.a.name}</TableHead>
                  <TableHead>{comparison.b.name}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(['params', 'results'] as const).map((section) => (
                  <Fragment key={section}>
                    <TableRow className="bg-muted/50 hover:bg-muted/50">
                      <TableCell colSpan={3} className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {section === 'params' ? 'Paramètres' : 'Résultats'}
                      </TableCell>
                    </TableRow>
                    {SCENARIO_FIELDS[comparison.kind][section].map((field) => {
                      const source = section === 'params' ? 'inputs' : 'results'
                      const va = comparison.a.parameters?.[source]?.[field.key]
                      const vb = comparison.b.parameters?.[source]?.[field.key]
                      if (va === undefined && vb === undefined) return null
                      const differs = JSON.stringify(va ?? null) !== JSON.stringify(vb ?? null)
                      const cellClass = differs ? 'bg-warning/10 font-medium' : ''
                      return (
                        <TableRow key={field.key}>
                          <TableCell className="text-muted-foreground">{field.label}</TableCell>
                          <TableCell className={`font-mono tabular-nums ${cellClass}`}>
                            {formatFieldValue(va, field.format)}
                          </TableCell>
                          <TableCell className={`font-mono tabular-nums ${cellClass}`}>
                            {formatFieldValue(vb, field.format)}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Dialog de sauvegarde */}
      <Dialog
        open={saveKind !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSaveKind(null)
            setScenarioName('')
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sauvegarder ce scénario</DialogTitle>
            <DialogDescription>
              Le scénario {saveKind ? SCENARIO_KIND_META[saveKind].label : ''} sera enregistré avec
              ses paramètres et ses résultats clés.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="scenario-name">Nom du scénario</Label>
            <Input
              id="scenario-name"
              value={scenarioName}
              onChange={(e) => setScenarioName(e.target.value)}
              placeholder="Ex. : Retraite à 45 ans"
              autoFocus
              maxLength={200}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveScenario()
              }}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setSaveKind(null)
                setScenarioName('')
              }}
            >
              Annuler
            </Button>
            <Button
              onClick={handleSaveScenario}
              disabled={!scenarioName.trim() || saveMutation.isPending}
            >
              {saveMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmation de suppression */}
      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer ce scénario ?</AlertDialogTitle>
            <AlertDialogDescription>
              «&nbsp;{deleteTarget?.name}&nbsp;» sera définitivement supprimé. Cette action est
              irréversible.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
