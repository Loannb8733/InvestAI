import { useState, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
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
import { useToast } from '@/hooks/use-toast'
import { simulationsApi, dashboardApi, analyticsApi } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'
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
} from 'lucide-react'
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  ComposedChart,
} from 'recharts'

interface FIREResult {
  fire_number: number
  years_to_fire: number | null
  monthly_passive_income: number
  projected_values: Array<{
    year: number
    portfolio_value: number
    fire_number: number
    is_fire: boolean
    progress_percent: number
  }>
  is_fire_achieved: boolean
  current_progress_percent: number
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
  projections: Array<{
    period: number
    price: number
    amount_invested: number
    units_bought: number
    total_units: number
    total_invested: number
    current_value: number
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

export default function SimulationsPage() {
  const { toast } = useToast()
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState('fire')

  // Fetch live portfolio value
  const { data: dashboard } = useQuery({
    queryKey: ['dashboard', 0],
    queryFn: () => dashboardApi.getMetrics(0),
  })

  const livePortfolioValue = dashboard?.total_value ?? 0
  const userCurrency = user?.preferredCurrency || 'EUR'

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: userCurrency,
      maximumFractionDigits: 0,
    }).format(value)
  }

  // Auto-suggest inflation based on user currency
  const suggestedInflation = INFLATION_BY_CURRENCY[userCurrency]?.rate ?? 2.0

  // FIRE Calculator state
  const [fireParams, setFireParams] = useState({
    current_portfolio_value: 0,
    monthly_contribution: 1000,
    monthly_expenses: 3000,
    expected_annual_return: 7,
    expense_ratio: 0.25,
    inflation_rate: suggestedInflation,
    withdrawal_rate: 4,
    target_years: 30,
  })
  const [fireResult, setFireResult] = useState<FIREResult | null>(null)

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
  })
  const [mcResult, setMcResult] = useState<MonteCarloData | null>(null)

  // DCA state
  const [dcaParams, setDcaParams] = useState({
    total_amount: 10000,
    frequency: 'monthly',
    duration_months: 12,
    expected_volatility: 20,
    expected_return: 7,
  })
  const [dcaResult, setDcaResult] = useState<DCAResult | null>(null)

  // Pre-fill portfolio value when dashboard loads
  useEffect(() => {
    if (livePortfolioValue > 0 && fireParams.current_portfolio_value === 0) {
      setFireParams((prev) => ({ ...prev, current_portfolio_value: Math.round(livePortfolioValue * 100) / 100 }))
    }
  }, [livePortfolioValue, fireParams.current_portfolio_value])

  // FIRE mutation
  const fireMutation = useMutation({
    mutationFn: simulationsApi.calculateFIRE,
    onSuccess: (data) => {
      setFireResult(data)
      toast({ title: 'Calcul FIRE effectué' })
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
    mutationFn: () =>
      analyticsApi.getMonteCarlo(
        mcParams.horizon,
        undefined,
        mcParams.annual_withdrawal_rate || undefined,
        mcParams.ter_percentage || undefined,
      ),
    onSuccess: (data) => {
      setMcResult(data)
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

  // Build Monte Carlo fan data for chart
  const mcChartData = mcResult
    ? [
        { label: 'P5 (pessimiste)', value: mcResult.percentiles.p5, fill: '#ef4444' },
        { label: 'P25', value: mcResult.percentiles.p25, fill: '#f97316' },
        { label: 'P50 (médian)', value: mcResult.percentiles.p50, fill: '#3b82f6' },
        { label: 'P75', value: mcResult.percentiles.p75, fill: '#22c55e' },
        { label: 'P95 (optimiste)', value: mcResult.percentiles.p95, fill: '#10b981' },
      ]
    : []

  // DCA lump sum comparison data
  const dcaLumpSumData = dcaResult?.projections.map((p) => {
    // Lump sum: invest total_amount at period 0, grows with expected return
    const monthlyReturn = (dcaParams.expected_return / 100) / 12
    const lumpSumValue = dcaParams.total_amount * Math.pow(1 + monthlyReturn, p.period)
    return {
      ...p,
      lump_sum_value: Math.round(lumpSumValue * 100) / 100,
    }
  })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Simulations</h1>
        <p className="text-muted-foreground">
          Calculateur FIRE, projections Monte Carlo et simulations DCA.
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
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Flame className="h-5 w-5 text-orange-500" />
                  Calculateur FIRE
                </CardTitle>
                <CardDescription>
                  Financial Independence, Retire Early - Calculez votre objectif d'indépendance financière.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Valeur actuelle du portefeuille</Label>
                    <div className="relative">
                      <Input
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
                            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-blue-500 hover:text-blue-700"
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
                    <Label>Contribution mensuelle</Label>
                    <Input
                      type="number"
                      value={fireParams.monthly_contribution}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, monthly_contribution: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Dépenses mensuelles prévues à la retraite</Label>
                  <Input
                    type="number"
                    value={fireParams.monthly_expenses}
                    onChange={(e) =>
                      setFireParams({ ...fireParams, monthly_expenses: parseFloat(e.target.value) || 0 })
                    }
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Rendement annuel attendu (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={fireParams.expected_annual_return}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, expected_annual_return: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Frais annuels / TER (%)</Label>
                    <Input
                      type="number"
                      step="0.05"
                      value={fireParams.expense_ratio}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, expense_ratio: parseFloat(e.target.value) || 0 })
                      }
                    />
                    <p className="text-xs text-muted-foreground">Déduit du rendement brut</p>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Inflation (%)</Label>
                    <div className="flex gap-2">
                      <Input
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
                    <Label>Taux de retrait (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={fireParams.withdrawal_rate}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, withdrawal_rate: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Horizon (années)</Label>
                  <Input
                    type="number"
                    value={fireParams.target_years}
                    onChange={(e) =>
                      setFireParams({ ...fireParams, target_years: parseInt(e.target.value) || 0 })
                    }
                  />
                </div>

                <Button
                  className="w-full"
                  onClick={() => fireMutation.mutate(fireParams)}
                  disabled={fireMutation.isPending}
                >
                  {fireMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Calculator className="mr-2 h-4 w-4" />
                  )}
                  Calculer
                </Button>
              </CardContent>
            </Card>

            {fireResult && (
              <Card>
                <CardHeader>
                  <CardTitle>Résultats FIRE</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-orange-500/10">
                      <Target className="h-8 w-8 mx-auto text-orange-500 mb-2" />
                      <p className="text-sm text-muted-foreground">Nombre FIRE</p>
                      <p className="text-2xl font-bold">{formatCurrency(fireResult.fire_number)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-blue-500/10">
                      <Clock className="h-8 w-8 mx-auto text-blue-500 mb-2" />
                      <p className="text-sm text-muted-foreground">Années restantes</p>
                      <p className="text-2xl font-bold">
                        {fireResult.years_to_fire !== null ? `${fireResult.years_to_fire} ans` : 'N/A'}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-green-500/10">
                      <DollarSign className="h-8 w-8 mx-auto text-green-500 mb-2" />
                      <p className="text-sm text-muted-foreground">Revenu passif mensuel</p>
                      <p className="text-2xl font-bold">{formatCurrency(fireResult.monthly_passive_income)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-purple-500/10">
                      <Percent className="h-8 w-8 mx-auto text-purple-500 mb-2" />
                      <p className="text-sm text-muted-foreground">Progression</p>
                      <p className="text-2xl font-bold">{fireResult.current_progress_percent.toFixed(1)}%</p>
                    </div>
                  </div>

                  {fireResult.is_fire_achieved && (
                    <div className="flex items-center gap-2 p-4 rounded-lg bg-green-500/20 text-green-700">
                      <CheckCircle className="h-5 w-5" />
                      <span className="font-medium">Félicitations ! Vous avez atteint le FIRE !</span>
                    </div>
                  )}

                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span>Progression vers le FIRE</span>
                      <span>{Math.min(fireResult.current_progress_percent, 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-3 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-orange-500 to-red-500 transition-all"
                        style={{ width: `${Math.min(fireResult.current_progress_percent, 100)}%` }}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* FIRE Chart */}
          {fireResult && (
            <Card>
              <CardHeader>
                <CardTitle>Projection FIRE</CardTitle>
                <CardDescription>
                  Croissance du capital vs objectif FIRE sur {fireParams.target_years} ans
                  (TER {fireParams.expense_ratio}% déduit, inflation {fireParams.inflation_rate}%)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={fireResult.projected_values}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(value: number) => formatCurrency(value)}
                        labelFormatter={(label) => `Année ${label}`}
                      />
                      <Legend />
                      <Area
                        type="monotone"
                        dataKey="portfolio_value"
                        name="Portefeuille"
                        stroke="#f97316"
                        fill="#f97316"
                        fillOpacity={0.3}
                      />
                      <Line
                        type="monotone"
                        dataKey="fire_number"
                        name="Objectif FIRE"
                        stroke="#ef4444"
                        strokeDasharray="5 5"
                        strokeWidth={2}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Portfolio Projection */}
        <TabsContent value="projection" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <LineChart className="h-5 w-5 text-blue-500" />
                  Projection de portefeuille
                </CardTitle>
                <CardDescription>
                  Projetez la croissance de votre portefeuille dans le temps.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Horizon (années)</Label>
                    <Input
                      type="number"
                      value={projectionParams.years}
                      onChange={(e) =>
                        setProjectionParams({ ...projectionParams, years: parseInt(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Rendement annuel (%)</Label>
                    <Input
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
                    <Label>Frais annuels / TER (%)</Label>
                    <Input
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
                    <Label>Contribution mensuelle</Label>
                    <Input
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
                  <Label>Inflation (%)</Label>
                  <div className="flex gap-2">
                    <Input
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
              </CardContent>
            </Card>

            {projectionResult && (
              <Card>
                <CardHeader>
                  <CardTitle>Résultats de la projection</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-blue-500/10">
                      <p className="text-sm text-muted-foreground">Valeur finale</p>
                      <p className="text-2xl font-bold">{formatCurrency(projectionResult.final_value)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-green-500/10">
                      <p className="text-sm text-muted-foreground">Valeur réelle (inflation)</p>
                      <p className="text-2xl font-bold">{formatCurrency(projectionResult.real_final_value)}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-purple-500/10">
                      <p className="text-sm text-muted-foreground">Contributions totales</p>
                      <p className="text-xl font-bold">{formatCurrency(projectionResult.total_contributions)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-orange-500/10">
                      <p className="text-sm text-muted-foreground">Gains totaux</p>
                      <p className="text-xl font-bold text-green-600">
                        +{formatCurrency(projectionResult.total_returns)}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {projectionResult && (
            <Card>
              <CardHeader>
                <CardTitle>Évolution du portefeuille</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={projectionResult.projections}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(value: number) => formatCurrency(value)}
                        labelFormatter={(label) => `Année ${label}`}
                      />
                      <Legend />
                      <Area
                        type="monotone"
                        dataKey="nominal_value"
                        name="Valeur nominale"
                        stroke="#3b82f6"
                        fill="#3b82f6"
                        fillOpacity={0.3}
                      />
                      <Area
                        type="monotone"
                        dataKey="real_value"
                        name="Valeur réelle"
                        stroke="#22c55e"
                        fill="#22c55e"
                        fillOpacity={0.3}
                      />
                      <Line
                        type="monotone"
                        dataKey="contributions"
                        name="Contributions"
                        stroke="#a855f7"
                        strokeDasharray="5 5"
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Monte Carlo */}
        <TabsContent value="montecarlo" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-indigo-500" />
                  Simulation Monte Carlo
                </CardTitle>
                <CardDescription>
                  5 000 simulations stochastiques basées sur la volatilité historique de votre portefeuille.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Horizon (jours)</Label>
                  <Select
                    value={String(mcParams.horizon)}
                    onValueChange={(v) => setMcParams({ ...mcParams, horizon: parseInt(v) })}
                  >
                    <SelectTrigger>
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
                    <Label>Taux de retrait annuel (%)</Label>
                    <Input
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
                    <Label>TER / Frais annuels (%)</Label>
                    <Input
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

                <div className="flex items-start gap-2 p-3 rounded-lg bg-blue-500/5 text-sm text-muted-foreground">
                  <Info className="h-4 w-4 mt-0.5 shrink-0 text-blue-500" />
                  <span>
                    Les rendements sont corrélés (Cholesky) avec shrinkage de volatilité pour les horizons longs.
                    Les retraits et frais sont appliqués proportionnellement chaque jour.
                  </span>
                </div>

                <Button
                  className="w-full"
                  onClick={() => mcMutation.mutate()}
                  disabled={mcMutation.isPending}
                >
                  {mcMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <BarChart3 className="mr-2 h-4 w-4" />
                  )}
                  Simuler (5 000 chemins)
                </Button>
              </CardContent>
            </Card>

            {mcResult && (
              <Card>
                <CardHeader>
                  <CardTitle>Résultats Monte Carlo</CardTitle>
                  <CardDescription>
                    {mcResult.simulations.toLocaleString()} simulations sur {mcResult.horizon_days} jours
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-blue-500/10">
                      <p className="text-sm text-muted-foreground">Rendement attendu</p>
                      <p
                        className={`text-2xl font-bold ${mcResult.expected_return >= 0 ? 'text-green-600' : 'text-red-600'}`}
                      >
                        {mcResult.expected_return >= 0 ? '+' : ''}
                        {mcResult.expected_return.toFixed(2)}%
                      </p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-green-500/10">
                      <p className="text-sm text-muted-foreground">Prob. gain</p>
                      <p className="text-2xl font-bold">{mcResult.prob_positive.toFixed(1)}%</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-red-500/10">
                      <p className="text-sm text-muted-foreground">Prob. perte &gt;10%</p>
                      <p className="text-2xl font-bold text-red-600">{mcResult.prob_loss_10.toFixed(1)}%</p>
                    </div>
                    <div
                      className={`text-center p-4 rounded-lg ${mcResult.prob_ruin > 20 ? 'bg-red-500/20' : 'bg-orange-500/10'}`}
                    >
                      <p className="text-sm text-muted-foreground">Prob. ruine</p>
                      <p className={`text-2xl font-bold ${mcResult.prob_ruin > 20 ? 'text-red-600' : ''}`}>
                        {mcResult.prob_ruin.toFixed(1)}%
                      </p>
                    </div>
                  </div>

                  {mcResult.prob_ruin > 20 && (
                    <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/20 text-red-700 text-sm">
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
            <Card>
              <CardHeader>
                <CardTitle>Fuseau de probabilité Monte Carlo</CardTitle>
                <CardDescription>Distribution des rendements : P5 (pessimiste) à P95 (optimiste)</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                      data={mcChartData}
                      layout="vertical"
                      margin={{ left: 120, right: 40, top: 10, bottom: 10 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}%`} />
                      <YAxis dataKey="label" type="category" width={110} />
                      <Tooltip formatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`} />
                      <Line
                        dataKey="value"
                        stroke="transparent"
                        dot={({ cx, cy, index }: { cx: number; cy: number; index: number }) => {
                          const colors = ['#ef4444', '#f97316', '#3b82f6', '#22c55e', '#10b981']
                          return (
                            <circle
                              key={index}
                              cx={cx}
                              cy={cy}
                              r={8}
                              fill={colors[index]}
                              stroke="white"
                              strokeWidth={2}
                            />
                          )
                        }}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>

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
                        className={`text-sm font-medium w-16 text-right ${d.value >= 0 ? 'text-green-600' : 'text-red-600'}`}
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
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Calculator className="h-5 w-5 text-purple-500" />
                  Simulateur DCA
                </CardTitle>
                <CardDescription>
                  Dollar Cost Averaging - Comparez investissement programmé vs lump sum.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Montant total à investir</Label>
                  <Input
                    type="number"
                    value={dcaParams.total_amount}
                    onChange={(e) =>
                      setDcaParams({ ...dcaParams, total_amount: parseFloat(e.target.value) || 0 })
                    }
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Fréquence</Label>
                    <Select
                      value={dcaParams.frequency}
                      onValueChange={(v) => setDcaParams({ ...dcaParams, frequency: v })}
                    >
                      <SelectTrigger>
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
                    <Label>Durée (mois)</Label>
                    <Input
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
                    <Label>Volatilité attendue (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={dcaParams.expected_volatility}
                      onChange={(e) =>
                        setDcaParams({ ...dcaParams, expected_volatility: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Rendement attendu (%)</Label>
                    <Input
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
                  Simuler
                </Button>
              </CardContent>
            </Card>

            {dcaResult && (
              <Card>
                <CardHeader>
                  <CardTitle>Résultats DCA</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-purple-500/10">
                      <p className="text-sm text-muted-foreground">Total investi</p>
                      <p className="text-2xl font-bold">{formatCurrency(dcaResult.total_invested)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-green-500/10">
                      <p className="text-sm text-muted-foreground">Valeur finale DCA</p>
                      <p className="text-2xl font-bold">{formatCurrency(dcaResult.final_value)}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-blue-500/10">
                      <p className="text-sm text-muted-foreground">Prix moyen</p>
                      <p className="text-xl font-bold">{formatCurrency(dcaResult.average_cost)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-orange-500/10">
                      <p className="text-sm text-muted-foreground">Rendement DCA</p>
                      <p
                        className={`text-xl font-bold ${dcaResult.return_percent >= 0 ? 'text-green-600' : 'text-red-600'}`}
                      >
                        {dcaResult.return_percent >= 0 ? '+' : ''}
                        {dcaResult.return_percent.toFixed(2)}%
                      </p>
                    </div>
                  </div>

                  {/* Lump sum comparison */}
                  {dcaLumpSumData && dcaLumpSumData.length > 0 && (
                    <div className="p-4 rounded-lg bg-muted space-y-2">
                      <p className="text-sm font-medium">Comparaison Lump Sum</p>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Lump Sum finale</span>
                        <span className="font-medium">
                          {formatCurrency(dcaLumpSumData[dcaLumpSumData.length - 1]?.lump_sum_value ?? 0)}
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">DCA finale</span>
                        <span className="font-medium">{formatCurrency(dcaResult.final_value)}</span>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {dcaLumpSumData && dcaLumpSumData.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>DCA vs Lump Sum</CardTitle>
                <CardDescription>
                  Comparaison entre investissement programmé et investissement direct
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsLineChart data={dcaLumpSumData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period" />
                      <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip formatter={(value: number) => formatCurrency(value)} />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="current_value"
                        name="DCA (valeur)"
                        stroke="#a855f7"
                        strokeWidth={2}
                      />
                      <Line
                        type="monotone"
                        dataKey="lump_sum_value"
                        name="Lump Sum"
                        stroke="#f97316"
                        strokeWidth={2}
                        strokeDasharray="5 5"
                      />
                      <Line
                        type="monotone"
                        dataKey="total_invested"
                        name="Capital investi"
                        stroke="#94a3b8"
                        strokeDasharray="3 3"
                      />
                    </RechartsLineChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
