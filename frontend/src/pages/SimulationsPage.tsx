import { useState, useEffect, useRef } from 'react'
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
} from 'lucide-react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'

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
        { label: 'P5 (pessimiste)', value: mcResult.percentiles.p5, fill: 'oklch(var(--chart-4))' },
        { label: 'P25', value: mcResult.percentiles.p25, fill: 'oklch(var(--chart-1))' },
        { label: 'P50 (médian)', value: mcResult.percentiles.p50, fill: 'oklch(var(--chart-5))' },
        { label: 'P75', value: mcResult.percentiles.p75, fill: 'oklch(var(--chart-3))' },
        { label: 'P95 (optimiste)', value: mcResult.percentiles.p95, fill: 'oklch(var(--chart-3))' },
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
        <h1 className="text-3xl font-serif font-medium">Simulations</h1>
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
            <Card elevation="raised">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Flame className="h-5 w-5 text-warning" />
                  Calculateur FIRE
                </CardTitle>
                <CardDescription>
                  Financial Independence, Retire Early - Calculez votre objectif d'indépendance financière.
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
                    <Label htmlFor="fire-monthly-contribution">Contribution mensuelle</Label>
                    <Input
                      id="fire-monthly-contribution"
                      type="number"
                      value={fireParams.monthly_contribution}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, monthly_contribution: parseFloat(e.target.value) || 0 })
                      }
                    />
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
                      value={fireParams.expected_annual_return}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, expected_annual_return: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="fire-expense-ratio">Frais annuels / TER (%)</Label>
                    <Input
                      id="fire-expense-ratio"
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
                      value={fireParams.withdrawal_rate}
                      onChange={(e) =>
                        setFireParams({ ...fireParams, withdrawal_rate: parseFloat(e.target.value) || 0 })
                      }
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="fire-target-years">Horizon (années)</Label>
                  <Input
                    id="fire-target-years"
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
              <Card elevation="raised">
                <CardHeader>
                  <CardTitle>Résultats FIRE</CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-warning/10">
                      <Target className="h-8 w-8 mx-auto text-warning mb-2" />
                      <p className="text-sm text-muted-foreground">Nombre FIRE</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(fireResult.fire_number)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <Clock className="h-8 w-8 mx-auto text-accent mb-2" />
                      <p className="text-sm text-muted-foreground">Années restantes</p>
                      <p className="text-2xl font-serif font-medium">
                        {fireResult.years_to_fire !== null ? `${fireResult.years_to_fire} ans` : 'N/A'}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-gain/10">
                      <DollarSign className="h-8 w-8 mx-auto text-gain mb-2" />
                      <p className="text-sm text-muted-foreground">Revenu passif mensuel</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(fireResult.monthly_passive_income)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <Percent className="h-8 w-8 mx-auto text-accent mb-2" />
                      <p className="text-sm text-muted-foreground">Progression</p>
                      <p className="text-2xl font-serif font-medium">{fireResult.current_progress_percent.toFixed(1)}%</p>
                    </div>
                  </div>

                  {fireResult.is_fire_achieved && (
                    <div className="flex items-center gap-2 p-4 rounded-lg bg-gain/20 text-gain">
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
                        className="h-full bg-gain transition-all"
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
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>Projection FIRE</CardTitle>
                <CardDescription>
                  Croissance du capital vs objectif FIRE sur {fireParams.target_years} ans
                  (TER {fireParams.expense_ratio}% déduit, inflation {fireParams.inflation_rate}%)
                </CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const cPortfolio = color('--chart-1')
                  const cFire = color('--chart-4')
                  const fireData = fireResult.projected_values
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
                    <>
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
                          axisBottom={{ tickSize: 0, tickPadding: 8 }}
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
                                    <span className="text-xs text-muted-foreground">Portefeuille</span>
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
                              itemWidth: 110,
                              itemHeight: 18,
                              symbolSize: 10,
                              symbolShape: 'circle',
                              itemTextColor: color('--muted-foreground'),
                              data: [
                                { id: 'portfolio_value', label: 'Portefeuille', color: cPortfolio },
                                { id: 'fire_number', label: 'Objectif FIRE', color: cFire },
                              ],
                            },
                          ]}
                          animate
                          motionConfig="gentle"
                        />
                      </div>
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

                <div className="flex items-start gap-2 p-3 rounded-lg bg-accent/5 text-sm text-muted-foreground">
                  <Info className="h-4 w-4 mt-0.5 shrink-0 text-accent" />
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
              <Card elevation="raised">
                <CardHeader>
                  <CardTitle>Résultats Monte Carlo</CardTitle>
                  <CardDescription>
                    {mcResult.simulations.toLocaleString()} simulations sur {mcResult.horizon_days} jours
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
                  Dollar Cost Averaging - Comparez investissement programmé vs lump sum.
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
                  Simuler
                </Button>
              </CardContent>
            </Card>

            {dcaResult && (
              <Card elevation="raised">
                <CardHeader>
                  <CardTitle>Résultats DCA</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <p className="text-sm text-muted-foreground">Total investi</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(dcaResult.total_invested)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-gain/10">
                      <p className="text-sm text-muted-foreground">Valeur finale DCA</p>
                      <p className="text-2xl font-serif font-medium">{formatCurrency(dcaResult.final_value)}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-accent/10">
                      <p className="text-sm text-muted-foreground">Prix moyen</p>
                      <p className="text-xl font-bold">{formatCurrency(dcaResult.average_cost)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-warning/10">
                      <p className="text-sm text-muted-foreground">Rendement DCA</p>
                      <p
                        className={`text-xl font-bold ${dcaResult.return_percent >= 0 ? 'text-gain' : 'text-loss'}`}
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
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>DCA vs Lump Sum</CardTitle>
                <CardDescription>
                  Comparaison entre investissement programmé et investissement direct
                </CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const cDca = color('--chart-2')
                  const cLump = color('--chart-1')
                  const cInvested = color('--muted-foreground')
                  const dcaData = dcaLumpSumData
                  // Solid DCA value as the real Nivo line; the two dashed references via a custom layer.
                  const series: LineSeries[] = [
                    { id: 'current_value', data: dcaData.map((d) => ({ x: String(d.period), y: d.current_value })) },
                  ]
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
                        layers={['grid', 'axes', DashedLinesLayer, 'lines', 'slices']}
                        enableSlices="x"
                        sliceTooltip={({ slice }) => {
                          const period = slice.points[0]?.data.x as string
                          const point = dcaData.find((d) => String(d.period) === period)
                          if (!point) return null
                          const rows = [
                            { label: 'DCA (valeur)', value: point.current_value, color: cDca },
                            { label: 'Lump Sum', value: point.lump_sum_value, color: cLump },
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
                              { id: 'current_value', label: 'DCA (valeur)', color: cDca },
                              { id: 'lump_sum_value', label: 'Lump Sum', color: cLump },
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
    </div>
  )
}
