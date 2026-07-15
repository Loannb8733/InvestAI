import { Fragment, useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
  TrendingUp,
  Target,
  Calculator,
  Flame,
  LineChart,
  DollarSign,
  Percent,
  CheckCircle,
  Clock,
  BarChart3,
  Info,
  Save,
  Trash2,
  Bookmark,
  ArrowLeftRight,
} from 'lucide-react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'

// FIRE probabiliste : hypothèses réellement appliquées, échouées par le backend
// (taux en décimal : 0.04 = 4 %). defaults_from trace la provenance des défauts.
interface FIREAssumptions {
  current_value: number
  monthly_contribution: number
  annual_expenses: number
  withdrawal_rate: number
  annual_return_mean: number
  annual_volatility: number
  inflation: number
  index_contributions: boolean
  years_horizon: number
  n_paths: number
  defaults_from: Record<string, string> | null
}

interface FIREProbResult {
  prob_by_year: Array<{ year: number; prob: number }>
  prob_at_horizon: number
  fire_year_p10: number | null
  fire_year_p50: number | null
  fire_year_p90: number | null
  final_value_p10: number
  final_value_p50: number
  final_value_p90: number
  fire_number_today: number
  survival_prob_30y: number
  median_path: Array<{ year: number; portfolio_value: number; fire_number: number }>
  n_paths: number
  currency: string
  assumptions: FIREAssumptions
}

interface ProjectionResult {
  projections: Array<{
    year: number
    nominal_value: number
    real_value: number
    contributions: number
    returns: number
  }>
  final_value: number
  total_contributions: number
  total_returns: number
  real_final_value: number
}

interface DCAResult {
  total_invested: number
  final_value: number
  average_cost: number
  total_units: number
  return_percent: number
  // Distribution multi-chemins (500 trajectoires simulées côté backend)
  dca_p10: number
  dca_p50: number
  dca_p90: number
  lumpsum_p10: number
  lumpsum_p50: number
  lumpsum_p90: number
  prob_dca_beats_ls: number
  n_paths: number
  projections: Array<{
    period: number
    price: number
    amount_invested: number
    units_bought: number
    total_units: number
    total_invested: number
    current_value: number
    current_value_p10: number
    current_value_p90: number
    lump_sum_value: number
  }>
}

interface MonteCarloData {
  percentiles: Record<string, number>
  expected_return: number
  prob_positive: number
  prob_loss_10: number
  prob_ruin: number
  simulations: number
  horizon_days: number
}

const INFLATION_BY_CURRENCY: Record<string, { rate: number; label: string }> = {
  EUR: { rate: 2.0, label: '2.0% (zone euro)' },
  USD: { rate: 2.5, label: '2.5% (US)' },
  GBP: { rate: 2.0, label: '2.0% (UK)' },
  CHF: { rate: 0.5, label: '0.5% (Suisse)' },
  JPY: { rate: 1.0, label: '1.0% (Japon)' },
  CAD: { rate: 2.0, label: '2.0% (Canada)' },
  AUD: { rate: 2.5, label: '2.5% (Australie)' },
}

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
  const { theme, color } = useNivoTheme()
  const [activeTab, setActiveTab] = useState('fire')

  // Fetch live portfolio value
  const { data: dashboard } = useQuery({
    queryKey: ['dashboard', 0],
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

  // Champs pré-remplis depuis le profil investisseur (badge dans l'UI)
  const fireProfileDefaults = useMemo(() => {
    const from = fireResult?.assumptions.defaults_from
    if (!from) return []
    return Object.entries(from)
      .filter(([, source]) => source.includes('profil investisseur'))
      .map(([field]) => field)
  }, [fireResult])

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

  const { data: savedScenariosData, isLoading: scenariosLoading } = useQuery<SavedScenario[]>({
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
  const mcChartData = mcResult
    ? [
        { label: 'P5 (pessimiste)', value: mcResult.percentiles.p5, fill: 'oklch(var(--chart-4))' },
        { label: 'P25', value: mcResult.percentiles.p25, fill: 'oklch(var(--chart-1))' },
        { label: 'P50 (médian)', value: mcResult.percentiles.p50, fill: 'oklch(var(--chart-5))' },
        { label: 'P75', value: mcResult.percentiles.p75, fill: 'oklch(var(--chart-3))' },
        { label: 'P95 (optimiste)', value: mcResult.percentiles.p95, fill: 'oklch(var(--chart-3))' },
      ]
    : []

  // Comparaison DCA vs Lump Sum : les deux stratégies sont désormais simulées
  // côté backend SUR LES MÊMES trajectoires stochastiques (médiane + p10-p90).
  // Le calcul lump-sum déterministe local (composé certain) a été supprimé :
  // il comparait un chemin aléatoire à une courbe sans risque.
  const dcaChartData = dcaResult?.projections

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-serif font-medium">Simulations</h1>
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
        <TabsContent value="fire" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card elevation="raised">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Flame className="h-5 w-5 text-warning" />
                  Calculateur FIRE probabiliste
                  {fireProfileDefaults.length > 0 && (
                    <Badge variant="accent">Pré-rempli depuis votre profil investisseur</Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  Financial Independence, Retire Early — au lieu d'un chiffre unique, une simulation
                  Monte Carlo estime vos chances d'atteindre l'indépendance financière année par année.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="fire-current-value">Valeur actuelle du portefeuille</Label>
                    <div className="relative">
                      <Input
                        id="fire-current-value"
                        type="number"
                        value={fireParams.current_portfolio_value}
                        onChange={(e) =>
                          setFireParams({ ...fireParams, current_portfolio_value: parseFloat(e.target.value) || 0 })
                        }
                      />
                      {livePortfolioValue > 0 &&
                        fireParams.current_portfolio_value !== Math.round(livePortfolioValue * 100) / 100 && (
                          <button
                            type="button"
                            onClick={() =>
                              setFireParams({
                                ...fireParams,
                                current_portfolio_value: Math.round(livePortfolioValue * 100) / 100,
                              })
                            }
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-accent hover:text-accent"
                          >
                            Réinitialiser
                          </button>
                        )}
                    </div>
                    {livePortfolioValue > 0 && (
                      <p className="text-xs text-muted-foreground">
                        Valeur live : {formatCurrency(livePortfolioValue)}
                      </p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fire-monthly-contribution">Épargne mensuelle</Label>
                    <Input
                      id="fire-monthly-contribution"
                      type="number"
                      min={0}
                      placeholder="auto : profil investisseur"
                      value={fireParams.monthly_contribution ?? ''}
                      onChange={(e) =>
                        setFireParams({
                          ...fireParams,
                          monthly_contribution:
                            e.target.value === '' ? null : parseFloat(e.target.value) || 0,
                        })
                      }
                    />
                    <p className="text-xs text-muted-foreground">
                      Vide = DCA mensuel de votre profil investisseur
                    </p>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="fire-monthly-expenses">Dépenses mensuelles prévues à la retraite</Label>
                  <Input
                    id="fire-monthly-expenses"
                    type="number"
                    value={fireParams.monthly_expenses}
                    onChange={(e) =>
                      setFireParams({ ...fireParams, monthly_expenses: parseFloat(e.target.value) || 0 })
                    }
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="fire-expected-return">Rendement annuel attendu (%)</Label>
                    <Input
                      id="fire-expected-return"
                      type="number"
                      step="0.1"
                      min={-5}
                      max={20}
                      placeholder="auto : profil investisseur"
                      value={fireParams.expected_annual_return ?? ''}
                      onChange={(e) =>
                        setFireParams({
                          ...fireParams,
                          expected_annual_return:
                            e.target.value === '' ? null : parseFloat(e.target.value) || 0,
                        })
                      }
                    />
                    <p className="text-xs text-muted-foreground">Vide = selon votre profil de risque</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fire-volatility">Volatilité annuelle (%)</Label>
                    <Input
                      id="fire-volatility"
                      type="number"
                      step="0.5"
                      min={1}
                      max={80}
                      placeholder="auto : profil investisseur"
                      value={fireParams.annual_volatility ?? ''}
                      onChange={(e) =>
                        setFireParams({
                          ...fireParams,
                          annual_volatility:
                            e.target.value === '' ? null : parseFloat(e.target.value) || 0,
                        })
                      }
                    />
                    <p className="text-xs text-muted-foreground">Écart-type des rendements annuels</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="fire-inflation">Inflation (%)</Label>
                    <div className="flex gap-2">
                      <Input
                        id="fire-inflation"
                        type="number"
                        step="0.1"
                        value={fireParams.inflation_rate}
                        onChange={(e) =>
                          setFireParams({ ...fireParams, inflation_rate: parseFloat(e.target.value) || 0 })
                        }
                        className="flex-1"
                      />
                      <Select
                        onValueChange={(currency) => {
                          const info = INFLATION_BY_CURRENCY[currency]
                          if (info) setFireParams({ ...fireParams, inflation_rate: info.rate })
                        }}
                      >
                        <SelectTrigger className="w-24">
                          <SelectValue placeholder={userCurrency} />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(INFLATION_BY_CURRENCY).map(([code, info]) => (
                            <SelectItem key={code} value={code}>
                              {code} ({info.rate}%)
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <p className="text-xs text-muted-foreground">Taux auto-suggéré pour {userCurrency}</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fire-withdrawal-rate">Taux de retrait (%)</Label>
                    <Input
                      id="fire-withdrawal-rate"
                      type="number"
                      step="0.1"
                      min={2}
                      max={8}
                      value={fireParams.withdrawal_rate}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, withdrawal_rate: parseFloat(e.target.value) || 0 })
                      }
                    />
                    <p className="text-xs text-muted-foreground">Entre 2 % et 8 % (règle des 4 %)</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="fire-years-horizon">Horizon (années)</Label>
                    <Input
                      id="fire-years-horizon"
                      type="number"
                      min={1}
                      max={50}
                      value={fireParams.years_horizon}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, years_horizon: parseInt(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fire-index-contributions" className="block">
                      Indexation de l'épargne
                    </Label>
                    <label
                      htmlFor="fire-index-contributions"
                      className="flex h-9 cursor-pointer items-center gap-2 rounded-md border border-input px-3 text-sm"
                    >
                      <Checkbox
                        id="fire-index-contributions"
                        checked={fireParams.index_contributions}
                        onCheckedChange={(checked) =>
                          setFireParams({ ...fireParams, index_contributions: checked === true })
                        }
                      />
                      Indexer mon épargne sur l'inflation
                    </label>
                    <p className="text-xs text-muted-foreground">
                      L'objectif FIRE, lui, est toujours indexé
                    </p>
                  </div>
                </div>

                <Button
                  className="w-full"
                  onClick={() => fireMutation.mutate(fireParams)}
                  disabled={fireMutation.isPending || fireParams.monthly_expenses <= 0}
                >
                  {fireMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Calculator className="mr-2 h-4 w-4" />
                  )}
                  Simuler (1 000 trajectoires)
                </Button>

                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setSaveKind('fire')}
                  disabled={!fireResult}
                >
                  <Save className="mr-2 h-4 w-4" />
                  Sauvegarder ce scénario
                </Button>
              </CardContent>
            </Card>

            {fireResult && (
              <Card elevation="raised">
                <CardHeader>
                  <CardTitle>Résultats FIRE</CardTitle>
                  <CardDescription>
                    Simulation sur {fireResult.n_paths.toLocaleString('fr-FR')} trajectoires — le passé
                    ne préjuge pas des performances futures.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Headline probabiliste */}
                  <div className="text-center p-5 rounded-lg bg-warning/10">
                    <Flame className="h-8 w-8 mx-auto text-warning mb-2" />
                    <p className="text-3xl font-serif font-medium">
                      {(fireResult.prob_at_horizon * 100).toFixed(0)} % de chances d'être FIRE
                    </p>
                    <p className="text-sm text-muted-foreground">
                      d'ici {fireResult.prob_by_year[fireResult.prob_by_year.length - 1]?.year}
                    </p>
                  </div>

                  <div className="text-center p-4 rounded-lg bg-accent/10">
                    <Clock className="h-6 w-6 mx-auto text-accent mb-1" />
                    <p className="text-sm text-muted-foreground">Année FIRE médiane</p>
                    <p className="text-2xl font-serif font-medium">
                      {fireResult.fire_year_p50 ?? 'au-delà de l’horizon'}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      optimiste {fireResult.fire_year_p10 ?? '—'} · prudent{' '}
                      {fireResult.fire_year_p90 ?? 'au-delà de l’horizon'}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <Target className="h-6 w-6 mx-auto text-accent mb-1" />
                      <p className="text-sm text-muted-foreground">Nombre FIRE (aujourd'hui)</p>
                      <p className="text-xl font-serif font-medium">
                        {formatCurrency(fireResult.fire_number_today)}
                      </p>
                      <p className="text-xs text-muted-foreground">indexé sur l'inflation ensuite</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-gain/10">
                      <DollarSign className="h-6 w-6 mx-auto text-gain mb-1" />
                      <p className="text-sm text-muted-foreground">Valeur finale médiane</p>
                      <p className="text-xl font-serif font-medium">
                        {formatCurrency(fireResult.final_value_p50)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        p10-p90 : {formatCurrency(fireResult.final_value_p10)} –{' '}
                        {formatCurrency(fireResult.final_value_p90)}
                      </p>
                    </div>
                  </div>

                  {/* Survie post-FIRE (test Trinity) */}
                  <div
                    className={`p-4 rounded-lg ${fireResult.survival_prob_30y < 0.8 ? 'bg-loss/10' : 'bg-gain/10'}`}
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium flex items-center gap-1.5">
                        <Percent className="h-4 w-4" />
                        Survie post-FIRE : {(fireResult.survival_prob_30y * 100).toFixed(1)} % sur 30
                        ans de retraits
                      </p>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Simulation séparée façon Trinity study : départ au nombre FIRE, retraits de vos
                      dépenses indexées sur l'inflation pendant 30 ans, sans aucune épargne. C'est le
                      pourcentage de trajectoires où le capital n'est jamais épuisé.
                    </p>
                  </div>

                  {fireResult.prob_by_year[0]?.prob === 1 && (
                    <div className="flex items-center gap-2 p-4 rounded-lg bg-gain/20 text-gain">
                      <CheckCircle className="h-5 w-5" />
                      <span className="font-medium">
                        Félicitations ! Votre portefeuille atteint déjà le nombre FIRE.
                      </span>
                    </div>
                  )}

                  {(() => {
                    const progress = Math.min(
                      (fireResult.assumptions.current_value / fireResult.fire_number_today) * 100,
                      100,
                    )
                    return (
                      <div className="space-y-2">
                        <div className="flex justify-between text-sm">
                          <span>Progression vers le nombre FIRE</span>
                          <span>{progress.toFixed(1)}%</span>
                        </div>
                        <div className="h-3 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gain transition-all"
                            style={{ width: `${progress}%` }}
                          />
                        </div>
                      </div>
                    )
                  })()}
                </CardContent>
              </Card>
            )}
          </div>

          {/* Courbe de probabilité cumulée */}
          {fireResult && (
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>Probabilité d'être FIRE, année par année</CardTitle>
                <CardDescription>
                  Probabilité CUMULÉE d'avoir atteint le nombre FIRE (une fois atteint, l'état est
                  acquis) — {fireResult.n_paths.toLocaleString('fr-FR')} trajectoires simulées.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const cProb = color('--chart-1')
                  const probData = fireResult.prob_by_year
                  const series: LineSeries[] = [
                    {
                      id: 'prob',
                      data: probData.map((d) => ({ x: String(d.year), y: d.prob * 100 })),
                    },
                  ]
                  return (
                    <div className="h-72">
                      <ResponsiveLine
                        data={series}
                        theme={theme}
                        margin={{ top: 12, right: 16, bottom: 28, left: 44 }}
                        xScale={{ type: 'point' }}
                        yScale={{ type: 'linear', min: 0, max: 100 }}
                        curve="monotoneX"
                        colors={[cProb]}
                        lineWidth={2}
                        enablePoints={false}
                        enableGridX={false}
                        enableArea
                        areaOpacity={0.25}
                        axisBottom={{
                          tickSize: 0,
                          tickPadding: 8,
                          tickValues: probData
                            .filter((_, i) => i % Math.max(Math.ceil(probData.length / 10), 1) === 0)
                            .map((d) => String(d.year)),
                        }}
                        axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${v}%` }}
                        enableSlices="x"
                        sliceTooltip={({ slice }) => {
                          const year = slice.points[0]?.data.x as string
                          const point = probData.find((d) => String(d.year) === year)
                          if (!point) return null
                          return (
                            <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                              <p className="mb-1 text-xs text-muted-foreground">En {year}</p>
                              <span className="font-mono text-sm tabular-nums">
                                {(point.prob * 100).toFixed(1)} %
                              </span>
                              <span className="ml-1 text-xs text-muted-foreground">
                                de chances d'avoir atteint le FIRE
                              </span>
                            </div>
                          )
                        }}
                        animate
                        motionConfig="gentle"
                      />
                    </div>
                  )
                })()}
              </CardContent>
            </Card>
          )}

          {/* Trajectoire médiane vs objectif FIRE */}
          {fireResult && (
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>Trajectoire médiane vs objectif FIRE</CardTitle>
                <CardDescription>
                  Valeur médiane du portefeuille (50 % des trajectoires font mieux, 50 % moins bien)
                  face au nombre FIRE indexé sur l'inflation.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const cPortfolio = color('--chart-1')
                  const cFire = color('--chart-4')
                  const fireData = fireResult.median_path
                  const series: LineSeries[] = [
                    {
                      id: 'portfolio_value',
                      data: fireData.map((d) => ({ x: String(d.year), y: d.portfolio_value })),
                    },
                  ]
                  // Dashed FIRE-objective reference line on the same value axis.
                  const FireLineLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
                    const sx = xScale as (v: string) => number
                    const sy = yScale as (v: number) => number
                    const path = fireData
                      .map((d, i) => `${i === 0 ? 'M' : 'L'}${sx(String(d.year))},${sy(d.fire_number)}`)
                      .join(' ')
                    return <path d={path} fill="none" stroke={cFire} strokeWidth={2} strokeDasharray="5 5" />
                  }
                  return (
                    <div className="h-80">
                      <ResponsiveLine
                        data={series}
                        theme={theme}
                        margin={{ top: 12, right: 16, bottom: 28, left: 56 }}
                        xScale={{ type: 'point' }}
                        yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
                        curve="monotoneX"
                        colors={[cPortfolio]}
                        lineWidth={2}
                        enablePoints={false}
                        enableGridX={false}
                        enableArea
                        areaOpacity={0.3}
                        axisBottom={{
                          tickSize: 0,
                          tickPadding: 8,
                          tickValues: fireData
                            .filter((_, i) => i % Math.max(Math.ceil(fireData.length / 10), 1) === 0)
                            .map((d) => String(d.year)),
                        }}
                        axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${((v as number) / 1000).toFixed(0)}k` }}
                        layers={['grid', 'axes', 'areas', FireLineLayer, 'lines', 'slices']}
                        enableSlices="x"
                        sliceTooltip={({ slice }) => {
                          const year = slice.points[0]?.data.x as string
                          const point = fireData.find((d) => String(d.year) === year)
                          if (!point) return null
                          return (
                            <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                              <p className="mb-1.5 text-xs text-muted-foreground">Année {year}</p>
                              <div className="flex items-center justify-between gap-4">
                                <span className="flex items-center gap-2">
                                  <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: cPortfolio }} />
                                  <span className="text-xs text-muted-foreground">Portefeuille (médiane)</span>
                                </span>
                                <span className="font-mono text-sm tabular-nums">{formatCurrency(point.portfolio_value)}</span>
                              </div>
                              <div className="flex items-center justify-between gap-4">
                                <span className="flex items-center gap-2">
                                  <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: cFire }} />
                                  <span className="text-xs text-muted-foreground">Objectif FIRE</span>
                                </span>
                                <span className="font-mono text-sm tabular-nums">{formatCurrency(point.fire_number)}</span>
                              </div>
                            </div>
                          )
                        }}
                        legends={[
                          {
                            anchor: 'top-right',
                            direction: 'row',
                            translateY: -12,
                            itemWidth: 140,
                            itemHeight: 18,
                            symbolSize: 10,
                            symbolShape: 'circle',
                            itemTextColor: color('--muted-foreground'),
                            data: [
                              { id: 'portfolio_value', label: 'Portefeuille (médiane)', color: cPortfolio },
                              { id: 'fire_number', label: 'Objectif FIRE', color: cFire },
                            ],
                          },
                        ]}
                        animate
                        motionConfig="gentle"
                      />
                    </div>
                  )
                })()}
              </CardContent>
            </Card>
          )}

          {/* Hypothèses appliquées (exigence d'audit : hypothèses visibles) */}
          {fireResult && (
            <Card elevation="raised">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Info className="h-5 w-5 text-accent" />
                  Hypothèses de la simulation
                </CardTitle>
                <CardDescription>
                  Toutes les hypothèses réellement appliquées par le moteur — modifiez les champs
                  ci-dessus pour tester votre propre scénario.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const a = fireResult.assumptions
                  const from = a.defaults_from ?? {}
                  const rows: Array<{ key: string; label: string; value: string }> = [
                    { key: 'current_value', label: 'Valeur de départ', value: formatCurrency(a.current_value) },
                    { key: 'monthly_contribution', label: 'Épargne mensuelle', value: formatCurrency(a.monthly_contribution) },
                    { key: 'annual_expenses', label: 'Dépenses annuelles (retraite)', value: formatCurrency(a.annual_expenses) },
                    { key: 'withdrawal_rate', label: 'Taux de retrait', value: `${(a.withdrawal_rate * 100).toFixed(1)} %` },
                    { key: 'annual_return_mean', label: 'Rendement annuel moyen', value: `${(a.annual_return_mean * 100).toFixed(1)} %` },
                    { key: 'annual_volatility', label: 'Volatilité annuelle', value: `${(a.annual_volatility * 100).toFixed(1)} %` },
                    { key: 'inflation', label: 'Inflation', value: `${(a.inflation * 100).toFixed(1)} %` },
                    { key: 'index_contributions', label: 'Épargne indexée sur l’inflation', value: a.index_contributions ? 'Oui' : 'Non' },
                    { key: 'years_horizon', label: 'Horizon', value: `${a.years_horizon} ans` },
                    { key: 'n_paths', label: 'Trajectoires simulées', value: a.n_paths.toLocaleString('fr-FR') },
                  ]
                  return (
                    <>
                      <dl className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
                        {rows.map((row) => (
                          <div key={row.key} className="flex items-baseline justify-between gap-4 border-b border-border/50 py-1.5">
                            <dt className="text-sm text-muted-foreground">
                              {row.label}
                              {from[row.key] && (
                                <span className="ml-1.5 text-xs text-accent">({from[row.key]})</span>
                              )}
                            </dt>
                            <dd className="font-mono text-sm tabular-nums">{row.value}</dd>
                          </div>
                        ))}
                      </dl>
                      <p className="mt-4 text-xs text-muted-foreground">
                        Rendements mensuels log-normaux indépendants (moyenne et volatilité
                        constantes). Simulation sur {fireResult.n_paths.toLocaleString('fr-FR')}{' '}
                        trajectoires : ce sont des probabilités sous hypothèses, pas des promesses —
                        le passé ne préjuge pas des performances futures.
                      </p>
                    </>
                  )
                })()}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Portfolio Projection */}
        <TabsContent value="projection" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card elevation="raised">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <LineChart className="h-5 w-5 text-accent" />
                  Projection de portefeuille
                </CardTitle>
                <CardDescription>
                  Projetez la croissance de votre portefeuille dans le temps.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="projection-years">Horizon (années)</Label>
                    <Input
                      id="projection-years"
                      type="number"
                      value={projectionParams.years}
                      onChange={(e) =>
                        setProjectionParams({ ...projectionParams, years: parseInt(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="projection-expected-return">Rendement annuel (%)</Label>
                    <Input
                      id="projection-expected-return"
                      type="number"
                      step="0.1"
                      value={projectionParams.expected_return}
                      onChange={(e) =>
                        setProjectionParams({ ...projectionParams, expected_return: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="projection-expense-ratio">Frais annuels / TER (%)</Label>
                    <Input
                      id="projection-expense-ratio"
                      type="number"
                      step="0.05"
                      value={projectionParams.expense_ratio}
                      onChange={(e) =>
                        setProjectionParams({ ...projectionParams, expense_ratio: parseFloat(e.target.value) || 0 })
                      }
                    />
                    <p className="text-xs text-muted-foreground">Déduit du rendement brut</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="projection-monthly-contribution">Contribution mensuelle</Label>
                    <Input
                      id="projection-monthly-contribution"
                      type="number"
                      value={projectionParams.monthly_contribution}
                      onChange={(e) =>
                        setProjectionParams({
                          ...projectionParams,
                          monthly_contribution: parseFloat(e.target.value) || 0,
                        })
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="projection-inflation">Inflation (%)</Label>
                  <div className="flex gap-2">
                    <Input
                      id="projection-inflation"
                      type="number"
                      step="0.1"
                      value={projectionParams.inflation_rate}
                      onChange={(e) =>
                        setProjectionParams({ ...projectionParams, inflation_rate: parseFloat(e.target.value) || 0 })
                      }
                      className="flex-1"
                    />
                    <Select
                      onValueChange={(currency) => {
                        const info = INFLATION_BY_CURRENCY[currency]
                        if (info) setProjectionParams({ ...projectionParams, inflation_rate: info.rate })
                      }}
                    >
                      <SelectTrigger className="w-24">
                        <SelectValue placeholder={userCurrency} />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(INFLATION_BY_CURRENCY).map(([code, info]) => (
                          <SelectItem key={code} value={code}>
                            {code} ({info.rate}%)
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <p className="text-xs text-muted-foreground">Taux auto-suggéré pour {userCurrency}</p>
                </div>

                <Button
                  className="w-full"
                  onClick={() => projectionMutation.mutate(projectionParams)}
                  disabled={projectionMutation.isPending}
                >
                  {projectionMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <TrendingUp className="mr-2 h-4 w-4" />
                  )}
                  Projeter
                </Button>

                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setSaveKind('projection')}
                  disabled={!projectionResult}
                >
                  <Save className="mr-2 h-4 w-4" />
                  Sauvegarder ce scénario
                </Button>
              </CardContent>
            </Card>

            {projectionResult && (
              <Card elevation="raised">
                <CardHeader>
                  <CardTitle>Résultats de la projection</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <p className="text-sm text-muted-foreground">Valeur finale</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(projectionResult.final_value)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-gain/10">
                      <p className="text-sm text-muted-foreground">Valeur réelle (inflation)</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(projectionResult.real_final_value)}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <p className="text-sm text-muted-foreground">Contributions totales</p>
                      <p className="text-xl font-bold">{formatCurrency(projectionResult.total_contributions)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-warning/10">
                      <p className="text-sm text-muted-foreground">Gains totaux</p>
                      <p className="text-xl font-bold text-gain">
                        +{formatCurrency(projectionResult.total_returns)}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {projectionResult && (
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>Évolution du portefeuille</CardTitle>
              </CardHeader>
              <CardContent>
                {(() => {
                  const cNominal = color('--chart-5')
                  const cReal = color('--chart-3')
                  const cContrib = color('--chart-2')
                  const projData = projectionResult.projections
                  const series: LineSeries[] = [
                    { id: 'nominal_value', data: projData.map((d) => ({ x: String(d.year), y: d.nominal_value })) },
                    { id: 'real_value', data: projData.map((d) => ({ x: String(d.year), y: d.real_value })) },
                  ]
                  const seriesColors: Record<string, string> = {
                    nominal_value: cNominal,
                    real_value: cReal,
                  }
                  // Dashed contributions reference line on the same value axis.
                  const ContribLineLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
                    const sx = xScale as (v: string) => number
                    const sy = yScale as (v: number) => number
                    const path = projData
                      .map((d, i) => `${i === 0 ? 'M' : 'L'}${sx(String(d.year))},${sy(d.contributions)}`)
                      .join(' ')
                    return <path d={path} fill="none" stroke={cContrib} strokeWidth={2} strokeDasharray="5 5" />
                  }
                  return (
                    <div className="h-80">
                      <ResponsiveLine
                        data={series}
                        theme={theme}
                        margin={{ top: 12, right: 16, bottom: 28, left: 56 }}
                        xScale={{ type: 'point' }}
                        yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
                        curve="monotoneX"
                        colors={(s) => seriesColors[s.id as string]}
                        lineWidth={2}
                        enablePoints={false}
                        enableGridX={false}
                        enableArea
                        areaOpacity={0.3}
                        defs={[
                          {
                            id: 'proj-nominal',
                            type: 'linearGradient',
                            colors: [
                              { offset: 0, color: cNominal, opacity: 0.3 },
                              { offset: 100, color: cNominal, opacity: 0 },
                            ],
                          },
                          {
                            id: 'proj-real',
                            type: 'linearGradient',
                            colors: [
                              { offset: 0, color: cReal, opacity: 0.3 },
                              { offset: 100, color: cReal, opacity: 0 },
                            ],
                          },
                        ]}
                        fill={[
                          { match: { id: 'nominal_value' }, id: 'proj-nominal' },
                          { match: { id: 'real_value' }, id: 'proj-real' },
                        ]}
                        axisBottom={{ tickSize: 0, tickPadding: 8 }}
                        axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${((v as number) / 1000).toFixed(0)}k` }}
                        layers={['grid', 'axes', 'areas', ContribLineLayer, 'lines', 'slices']}
                        enableSlices="x"
                        sliceTooltip={({ slice }) => {
                          const year = slice.points[0]?.data.x as string
                          const point = projData.find((d) => String(d.year) === year)
                          if (!point) return null
                          const rows = [
                            { label: 'Valeur nominale', value: point.nominal_value, color: cNominal },
                            { label: 'Valeur réelle', value: point.real_value, color: cReal },
                            { label: 'Contributions', value: point.contributions, color: cContrib },
                          ]
                          return (
                            <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                              <p className="mb-1.5 text-xs text-muted-foreground">Année {year}</p>
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
                        legends={[
                          {
                            anchor: 'top-right',
                            direction: 'row',
                            translateY: -12,
                            itemWidth: 110,
                            itemHeight: 18,
                            symbolSize: 10,
                            symbolShape: 'circle',
                            itemTextColor: color('--muted-foreground'),
                            data: [
                              { id: 'nominal_value', label: 'Valeur nominale', color: cNominal },
                              { id: 'real_value', label: 'Valeur réelle', color: cReal },
                              { id: 'contributions', label: 'Contributions', color: cContrib },
                            ],
                          },
                        ]}
                        animate
                        motionConfig="gentle"
                      />
                    </div>
                  )
                })()}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Monte Carlo */}
        <TabsContent value="montecarlo" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card elevation="raised">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-accent" />
                  Simulation Monte Carlo
                </CardTitle>
                <CardDescription>
                  5 000 simulations stochastiques basées sur la volatilité historique de votre portefeuille.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="mc-horizon">Horizon (jours)</Label>
                  <Select
                    value={String(mcParams.horizon)}
                    onValueChange={(v) => setMcParams({ ...mcParams, horizon: parseInt(v) })}
                  >
                    <SelectTrigger id="mc-horizon">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="30">30 jours</SelectItem>
                      <SelectItem value="90">90 jours (3 mois)</SelectItem>
                      <SelectItem value="180">180 jours (6 mois)</SelectItem>
                      <SelectItem value="365">365 jours (1 an)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="mc-withdrawal-rate">Taux de retrait annuel (%)</Label>
                    <Input
                      id="mc-withdrawal-rate"
                      type="number"
                      step="0.5"
                      value={mcParams.annual_withdrawal_rate}
                      onChange={(e) =>
                        setMcParams({ ...mcParams, annual_withdrawal_rate: parseFloat(e.target.value) || 0 })
                      }
                    />
                    <p className="text-xs text-muted-foreground">0 = buy & hold</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="mc-ter">TER / Frais annuels (%)</Label>
                    <Input
                      id="mc-ter"
                      type="number"
                      step="0.05"
                      value={mcParams.ter_percentage}
                      onChange={(e) =>
                        setMcParams({ ...mcParams, ter_percentage: parseFloat(e.target.value) || 0 })
                      }
                    />
                    <p className="text-xs text-muted-foreground">Déduit à chaque itération</p>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="mc-monthly-withdrawal">Retrait mensuel (€/mois)</Label>
                  <Input
                    id="mc-monthly-withdrawal"
                    type="number"
                    step="50"
                    min="0"
                    value={mcParams.monthly_withdrawal}
                    onChange={(e) =>
                      setMcParams({ ...mcParams, monthly_withdrawal: parseFloat(e.target.value) || 0 })
                    }
                  />
                  <p className="text-xs text-muted-foreground">
                    Montant fixe retiré chaque mois. 0 = aucun retrait fixe. S'il est renseigné, il
                    remplace le taux de retrait annuel.
                  </p>
                </div>

                <div className="flex items-start gap-2 p-3 rounded-lg bg-accent/5 text-sm text-muted-foreground">
                  <Info className="h-4 w-4 mt-0.5 shrink-0 text-accent" />
                  <span>
                    Les rendements sont corrélés (Cholesky) avec shrinkage de volatilité pour les horizons longs.
                    Les retraits et frais sont appliqués proportionnellement chaque jour.
                  </span>
                </div>

                <Button
                  className="w-full"
                  onClick={() => mcMutation.mutate(mcParams)}
                  disabled={mcMutation.isPending}
                >
                  {mcMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <BarChart3 className="mr-2 h-4 w-4" />
                  )}
                  Simuler (5 000 chemins)
                </Button>

                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setSaveKind('montecarlo')}
                  disabled={!mcResult}
                >
                  <Save className="mr-2 h-4 w-4" />
                  Sauvegarder ce scénario
                </Button>
              </CardContent>
            </Card>

            {mcResult && (
              <Card elevation="raised">
                <CardHeader>
                  <CardTitle>Résultats Monte Carlo</CardTitle>
                  <CardDescription>
                    {mcResult.simulations.toLocaleString()} simulations sur {mcResult.horizon_days} jours
                    {mcApplied && mcApplied.monthly_withdrawal > 0 && (
                      <> — avec retraits de {formatCurrency(mcApplied.monthly_withdrawal)}/mois</>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <p className="text-sm text-muted-foreground">Rendement attendu</p>
                      <p
                        className={`text-2xl font-serif font-medium ${mcResult.expected_return >= 0 ? 'text-gain' : 'text-loss'}`}
                      >
                        {mcResult.expected_return >= 0 ? '+' : ''}
                        {mcResult.expected_return.toFixed(2)}%
                      </p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-gain/10">
                      <p className="text-sm text-muted-foreground">Prob. gain</p>
                      <p className="text-2xl font-serif font-medium">{mcResult.prob_positive.toFixed(1)}%</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-loss/10">
                      <p className="text-sm text-muted-foreground">Prob. perte &gt;10%</p>
                      <p className="text-2xl font-serif font-medium text-loss">{mcResult.prob_loss_10.toFixed(1)}%</p>
                    </div>
                    <div
                      className={`text-center p-4 rounded-lg ${mcResult.prob_ruin > 20 ? 'bg-loss/20' : 'bg-warning/10'}`}
                    >
                      <p className="text-sm text-muted-foreground">Prob. ruine</p>
                      <p className={`text-2xl font-serif font-medium ${mcResult.prob_ruin > 20 ? 'text-loss' : ''}`}>
                        {mcResult.prob_ruin.toFixed(1)}%
                      </p>
                    </div>
                  </div>

                  {mcResult.prob_ruin > 20 && (
                    <div className="flex items-center gap-2 p-3 rounded-lg bg-loss/20 text-loss text-sm">
                      <Flame className="h-4 w-4" />
                      <span>
                        Probabilité de ruine élevée ! Envisagez de réduire le taux de retrait ou de diversifier.
                      </span>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {/* Monte Carlo Fan Chart */}
          {mcResult && (
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>Fuseau de probabilité Monte Carlo</CardTitle>
                <CardDescription>Distribution des rendements : P5 (pessimiste) à P95 (optimiste)</CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  // Colors per percentile band, resolved from OKLCH tokens (Nivo can't parse oklch()).
                  const fanColors = [
                    color('--chart-4'),
                    color('--chart-1'),
                    color('--chart-5'),
                    color('--chart-3'),
                    color('--chart-3'),
                  ]
                  // Nivo line has no horizontal layout: categories sit on the x (point) axis,
                  // percentile value on the y (linear) axis — colored dots per percentile.
                  const series: LineSeries[] = [
                    { id: 'mc', data: mcChartData.map((d) => ({ x: d.label, y: d.value })) },
                  ]
                  const DotsLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
                    const sx = xScale as (v: string) => number
                    const sy = yScale as (v: number) => number
                    return (
                      <>
                        {mcChartData.map((d, i) => (
                          <circle
                            key={d.label}
                            cx={sx(d.label)}
                            cy={sy(d.value)}
                            r={8}
                            fill={fanColors[i]}
                            stroke={color('--popover')}
                            strokeWidth={2}
                          />
                        ))}
                      </>
                    )
                  }
                  return (
                    <div className="h-72">
                      <ResponsiveLine
                        data={series}
                        theme={theme}
                        margin={{ left: 56, right: 24, top: 10, bottom: 60 }}
                        xScale={{ type: 'point' }}
                        yScale={{ type: 'linear', min: 'auto', max: 'auto' }}
                        enablePoints={false}
                        enableGridX={false}
                        colors={['transparent']}
                        axisBottom={{ tickSize: 0, tickPadding: 8, tickRotation: -20 }}
                        axisLeft={{ tickSize: 0, tickPadding: 8, format: (v) => `${(v as number) > 0 ? '+' : ''}${v}%` }}
                        layers={['grid', 'axes', 'lines', DotsLayer, 'mesh']}
                        tooltip={({ point }) => {
                          const v = point.data.y as number
                          return (
                            <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                              <p className="text-xs text-muted-foreground">{point.data.x as string}</p>
                              <span className="font-mono text-sm tabular-nums">
                                {v > 0 ? '+' : ''}
                                {v.toFixed(2)}%
                              </span>
                            </div>
                          )
                        }}
                        animate
                        motionConfig="gentle"
                      />
                    </div>
                  )
                })()}

                {/* Visual bar representation */}
                <div className="mt-4 space-y-2">
                  {mcChartData.map((d) => (
                    <div key={d.label} className="flex items-center gap-3">
                      <span className="text-xs text-muted-foreground w-28 text-right">{d.label}</span>
                      <div className="flex-1 h-6 bg-muted rounded-full overflow-hidden relative">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(Math.max((d.value + 100) / 2, 0), 100)}%`,
                            backgroundColor: d.fill,
                            opacity: 0.7,
                          }}
                        />
                      </div>
                      <span
                        className={`text-sm font-medium w-16 text-right ${d.value >= 0 ? 'text-gain' : 'text-loss'}`}
                      >
                        {d.value >= 0 ? '+' : ''}
                        {d.value.toFixed(1)}%
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* DCA Simulator */}
        <TabsContent value="dca" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card elevation="raised">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calculator className="h-5 w-5 text-accent" />
                  Simulateur DCA
                </CardTitle>
                <CardDescription>
                  Dollar Cost Averaging - Comparez investissement programmé vs lump sum
                  sur 500 trajectoires de marché simulées (résultats en médiane et fourchette p10-p90).
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="dca-total-amount">Montant total à investir</Label>
                  <Input
                    id="dca-total-amount"
                    type="number"
                    value={dcaParams.total_amount}
                    onChange={(e) =>
                      setDcaParams({ ...dcaParams, total_amount: parseFloat(e.target.value) || 0 })
                    }
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="dca-frequency">Fréquence</Label>
                    <Select
                      value={dcaParams.frequency}
                      onValueChange={(v) => setDcaParams({ ...dcaParams, frequency: v })}
                    >
                      <SelectTrigger id="dca-frequency">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="weekly">Hebdomadaire</SelectItem>
                        <SelectItem value="monthly">Mensuel</SelectItem>
                        <SelectItem value="quarterly">Trimestriel</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="dca-duration">Durée (mois)</Label>
                    <Input
                      id="dca-duration"
                      type="number"
                      value={dcaParams.duration_months}
                      onChange={(e) =>
                        setDcaParams({ ...dcaParams, duration_months: parseInt(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="dca-volatility">Volatilité attendue (%)</Label>
                    <Input
                      id="dca-volatility"
                      type="number"
                      step="0.1"
                      value={dcaParams.expected_volatility}
                      onChange={(e) =>
                        setDcaParams({ ...dcaParams, expected_volatility: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="dca-expected-return">Rendement attendu (%)</Label>
                    <Input
                      id="dca-expected-return"
                      type="number"
                      step="0.1"
                      value={dcaParams.expected_return}
                      onChange={(e) =>
                        setDcaParams({ ...dcaParams, expected_return: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>

                <Button
                  className="w-full"
                  onClick={() => dcaMutation.mutate(dcaParams)}
                  disabled={dcaMutation.isPending}
                >
                  {dcaMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Calculator className="mr-2 h-4 w-4" />
                  )}
                  Simuler (500 trajectoires)
                </Button>

                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => setSaveKind('dca')}
                  disabled={!dcaResult}
                >
                  <Save className="mr-2 h-4 w-4" />
                  Sauvegarder ce scénario
                </Button>

                <div className="flex items-start gap-2 p-3 rounded-lg bg-accent/5 text-xs text-muted-foreground">
                  <Info className="h-4 w-4 mt-0.5 shrink-0 text-accent" />
                  <span>
                    Cette simulation est hypothétique (rendement et volatilité supposés).
                    Pour un test sur données historiques réelles :{' '}
                    <Link to="/intelligence" className="text-accent underline underline-offset-2">
                      Backtest DCA (Analyses IA &rsaquo; Signaux Alpha)
                    </Link>
                    .
                  </span>
                </div>
              </CardContent>
            </Card>

            {dcaResult && (
              <Card elevation="raised">
                <CardHeader>
                  <CardTitle>Résultats DCA</CardTitle>
                  <CardDescription>
                    Simulation sur {dcaResult.n_paths} trajectoires — médianes et fourchettes p10-p90.
                    Aucun chiffre n'est garanti.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <p className="text-sm text-muted-foreground">Total investi</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(dcaResult.total_invested)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-gain/10">
                      <p className="text-sm text-muted-foreground">Médiane DCA (valeur finale)</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(dcaResult.dca_p50)}</p>
                      <p className="text-xs text-muted-foreground">
                        p10-p90 : {formatCurrency(dcaResult.dca_p10)} – {formatCurrency(dcaResult.dca_p90)}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <p className="text-sm text-muted-foreground">Médiane Lump Sum</p>
                      <p className="text-xl font-bold">{formatCurrency(dcaResult.lumpsum_p50)}</p>
                      <p className="text-xs text-muted-foreground">
                        p10-p90 : {formatCurrency(dcaResult.lumpsum_p10)} – {formatCurrency(dcaResult.lumpsum_p90)}
                      </p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-warning/10">
                      <p className="text-sm text-muted-foreground">Rendement DCA (médiane)</p>
                      <p
                        className={`text-xl font-bold ${dcaResult.return_percent >= 0 ? 'text-gain' : 'text-loss'}`}
                      >
                        {dcaResult.return_percent >= 0 ? '+' : ''}
                        {dcaResult.return_percent.toFixed(2)}%
                      </p>
                    </div>
                  </div>

                  {/* DCA vs Lump Sum : probabilité sur les mêmes trajectoires */}
                  <div className="p-4 rounded-lg bg-muted space-y-2">
                    <p className="text-sm font-medium">Médiane DCA vs Médiane Lump Sum</p>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">
                        Dans {dcaResult.prob_dca_beats_ls.toFixed(0)} % des scénarios simulés
                      </span>
                      <span className="font-medium">le DCA fait mieux que le Lump Sum</span>
                    </div>
                    <div className="h-2 bg-background rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent transition-all"
                        style={{ width: `${Math.min(Math.max(dcaResult.prob_dca_beats_ls, 0), 100)}%` }}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Les deux stratégies sont évaluées sur les mêmes {dcaResult.n_paths} trajectoires de
                      rendements — la comparaison est donc à risque identique.
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {dcaChartData && dcaChartData.length > 0 && (
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>DCA vs Lump Sum</CardTitle>
                <CardDescription>
                  Trajectoires médianes sur {dcaResult?.n_paths ?? 500} scénarios simulés —
                  bande p10-p90 pour le DCA
                </CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const cDca = color('--chart-2')
                  const cLump = color('--chart-1')
                  const cInvested = color('--muted-foreground')
                  const dcaData = dcaChartData
                  // Solid median DCA value as the real Nivo line; the p10-p90 band and
                  // the two dashed references (median Lump Sum, invested capital) via custom layers.
                  const series: LineSeries[] = [
                    { id: 'current_value', data: dcaData.map((d) => ({ x: String(d.period), y: d.current_value })) },
                  ]
                  const BandLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
                    const sx = xScale as (v: string) => number
                    const sy = yScale as (v: number) => number
                    // Polygon: p90 forward, then p10 backward
                    const upper = dcaData.map(
                      (d, i) => `${i === 0 ? 'M' : 'L'}${sx(String(d.period))},${sy(d.current_value_p90)}`
                    )
                    const lower = [...dcaData]
                      .reverse()
                      .map((d) => `L${sx(String(d.period))},${sy(d.current_value_p10)}`)
                    return <path d={`${upper.join(' ')} ${lower.join(' ')} Z`} fill={cDca} opacity={0.15} stroke="none" />
                  }
                  const DashedLinesLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
                    const sx = xScale as (v: string) => number
                    const sy = yScale as (v: number) => number
                    const path = (key: 'lump_sum_value' | 'total_invested') =>
                      dcaData
                        .map((d, i) => `${i === 0 ? 'M' : 'L'}${sx(String(d.period))},${sy(d[key])}`)
                        .join(' ')
                    return (
                      <>
                        <path d={path('lump_sum_value')} fill="none" stroke={cLump} strokeWidth={2} strokeDasharray="5 5" />
                        <path d={path('total_invested')} fill="none" stroke={cInvested} strokeWidth={1.5} strokeDasharray="3 3" />
                      </>
                    )
                  }
                  return (
                    <div className="h-80">
                      <ResponsiveLine
                        data={series}
                        theme={theme}
                        margin={{ top: 12, right: 16, bottom: 28, left: 56 }}
                        xScale={{ type: 'point' }}
                        yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
                        curve="monotoneX"
                        colors={[cDca]}
                        lineWidth={2}
                        enablePoints={false}
                        enableGridX={false}
                        axisBottom={{ tickSize: 0, tickPadding: 8 }}
                        axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${((v as number) / 1000).toFixed(0)}k` }}
                        layers={['grid', 'axes', BandLayer, DashedLinesLayer, 'lines', 'slices']}
                        enableSlices="x"
                        sliceTooltip={({ slice }) => {
                          const period = slice.points[0]?.data.x as string
                          const point = dcaData.find((d) => String(d.period) === period)
                          if (!point) return null
                          const rows = [
                            { label: 'DCA (médiane)', value: point.current_value, color: cDca },
                            { label: 'DCA p10-p90', value: null, color: cDca },
                            { label: 'Lump Sum (médiane)', value: point.lump_sum_value, color: cLump },
                            { label: 'Capital investi', value: point.total_invested, color: cInvested },
                          ]
                          return (
                            <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                              <p className="mb-1.5 text-xs text-muted-foreground">Période {period}</p>
                              {rows.map((r) => (
                                <div key={r.label} className="flex items-center justify-between gap-4">
                                  <span className="flex items-center gap-2">
                                    <span className="h-2 w-2 rounded-[2px]" style={{ backgroundColor: r.color }} />
                                    <span className="text-xs text-muted-foreground">{r.label}</span>
                                  </span>
                                  <span className="font-mono text-sm tabular-nums">
                                    {r.value !== null
                                      ? formatCurrency(r.value)
                                      : `${formatCurrency(point.current_value_p10)} – ${formatCurrency(point.current_value_p90)}`}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )
                        }}
                        legends={[
                          {
                            anchor: 'top-right',
                            direction: 'row',
                            translateY: -12,
                            itemWidth: 130,
                            itemHeight: 18,
                            symbolSize: 10,
                            symbolShape: 'circle',
                            itemTextColor: color('--muted-foreground'),
                            data: [
                              { id: 'current_value', label: 'DCA (médiane)', color: cDca },
                              { id: 'lump_sum_value', label: 'Lump Sum (médiane)', color: cLump },
                              { id: 'total_invested', label: 'Capital investi', color: cInvested },
                            ],
                          },
                        ]}
                        animate
                        motionConfig="gentle"
                      />
                    </div>
                  )
                })()}
              </CardContent>
            </Card>
          )}
        </TabsContent>
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
          {scenariosLoading ? (
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
