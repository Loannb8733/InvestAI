import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
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
import { simulationsApi } from '@/services/api'
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
  AreaChart,
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

export default function SimulationsPage() {
  const { toast } = useToast()
  const [activeTab, setActiveTab] = useState('fire')

  // FIRE Calculator state
  const [fireParams, setFireParams] = useState({
    current_portfolio_value: 50000,
    monthly_contribution: 1000,
    monthly_expenses: 3000,
    expected_annual_return: 7,
    inflation_rate: 2,
    withdrawal_rate: 4,
    target_years: 30,
  })
  const [fireResult, setFireResult] = useState<FIREResult | null>(null)

  // Projection state
  const [projectionParams, setProjectionParams] = useState({
    years: 10,
    expected_return: 7,
    monthly_contribution: 500,
    inflation_rate: 2,
  })
  const [projectionResult, setProjectionResult] = useState<ProjectionResult | null>(null)

  // DCA state
  const [dcaParams, setDcaParams] = useState({
    total_amount: 10000,
    frequency: 'monthly',
    duration_months: 12,
    expected_volatility: 20,
    expected_return: 7,
  })
  const [dcaResult, setDcaResult] = useState<DCAResult | null>(null)

  // FIRE calculation mutation
  const fireMutation = useMutation({
    mutationFn: simulationsApi.calculateFIRE,
    onSuccess: (data) => {
      setFireResult(data)
      toast({ title: 'Calcul FIRE effectue' })
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
      toast({ title: 'Projection calculee' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de calculer la projection.' })
    },
  })

  // DCA mutation
  const dcaMutation = useMutation({
    mutationFn: simulationsApi.simulateDCA,
    onSuccess: (data) => {
      setDcaResult(data)
      toast({ title: 'Simulation DCA calculee' })
    },
    onError: () => {
      toast({ variant: 'destructive', title: 'Erreur', description: 'Impossible de simuler le DCA.' })
    },
  })

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('fr-FR', {
      style: 'currency',
      currency: 'EUR',
      maximumFractionDigits: 0,
    }).format(value)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Simulations</h1>
        <p className="text-muted-foreground">
          Calculateur FIRE, projections et simulations d'investissement.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="fire" className="flex items-center gap-2">
            <Flame className="h-4 w-4" />
            FIRE
          </TabsTrigger>
          <TabsTrigger value="projection" className="flex items-center gap-2">
            <LineChart className="h-4 w-4" />
            Projection
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
                  Financial Independence, Retire Early - Calculez votre objectif d'independance financiere.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Valeur actuelle du portefeuille</Label>
                    <Input
                      type="number"
                      value={fireParams.current_portfolio_value}
                      onChange={(e) => setFireParams({ ...fireParams, current_portfolio_value: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Contribution mensuelle</Label>
                    <Input
                      type="number"
                      value={fireParams.monthly_contribution}
                      onChange={(e) => setFireParams({ ...fireParams, monthly_contribution: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Depenses mensuelles prevues a la retraite</Label>
                  <Input
                    type="number"
                    value={fireParams.monthly_expenses}
                    onChange={(e) => setFireParams({ ...fireParams, monthly_expenses: parseFloat(e.target.value) || 0 })}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Rendement annuel attendu (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={fireParams.expected_annual_return}
                      onChange={(e) => setFireParams({ ...fireParams, expected_annual_return: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Inflation (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={fireParams.inflation_rate}
                      onChange={(e) => setFireParams({ ...fireParams, inflation_rate: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Taux de retrait (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={fireParams.withdrawal_rate}
                      onChange={(e) => setFireParams({ ...fireParams, withdrawal_rate: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Horizon (annees)</Label>
                    <Input
                      type="number"
                      value={fireParams.target_years}
                      onChange={(e) => setFireParams({ ...fireParams, target_years: parseInt(e.target.value) || 0 })}
                    />
                  </div>
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
                  <CardTitle>Resultats FIRE</CardTitle>
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
                      <p className="text-sm text-muted-foreground">Annees restantes</p>
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
                      <span className="font-medium">Felicitations ! Vous avez atteint le FIRE !</span>
                    </div>
                  )}

                  {/* Progress bar */}
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
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={fireResult.projected_values}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(value: number) => formatCurrency(value)}
                        labelFormatter={(label) => `Annee ${label}`}
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
                      />
                    </AreaChart>
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
                    <Label>Horizon (annees)</Label>
                    <Input
                      type="number"
                      value={projectionParams.years}
                      onChange={(e) => setProjectionParams({ ...projectionParams, years: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Rendement annuel (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={projectionParams.expected_return}
                      onChange={(e) => setProjectionParams({ ...projectionParams, expected_return: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Contribution mensuelle</Label>
                    <Input
                      type="number"
                      value={projectionParams.monthly_contribution}
                      onChange={(e) => setProjectionParams({ ...projectionParams, monthly_contribution: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Inflation (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={projectionParams.inflation_rate}
                      onChange={(e) => setProjectionParams({ ...projectionParams, inflation_rate: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
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
                  <CardTitle>Resultats de la projection</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-blue-500/10">
                      <p className="text-sm text-muted-foreground">Valeur finale</p>
                      <p className="text-2xl font-bold">{formatCurrency(projectionResult.final_value)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-green-500/10">
                      <p className="text-sm text-muted-foreground">Valeur reelle (inflation)</p>
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
                <CardTitle>Evolution du portefeuille</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={projectionResult.projections}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip
                        formatter={(value: number) => formatCurrency(value)}
                        labelFormatter={(label) => `Annee ${label}`}
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
                        name="Valeur reelle"
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
                    </AreaChart>
                  </ResponsiveContainer>
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
                  Dollar Cost Averaging - Simulez une strategie d'investissement programme.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>Montant total a investir</Label>
                  <Input
                    type="number"
                    value={dcaParams.total_amount}
                    onChange={(e) => setDcaParams({ ...dcaParams, total_amount: parseFloat(e.target.value) || 0 })}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Frequence</Label>
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
                    <Label>Duree (mois)</Label>
                    <Input
                      type="number"
                      value={dcaParams.duration_months}
                      onChange={(e) => setDcaParams({ ...dcaParams, duration_months: parseInt(e.target.value) || 0 })}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Volatilite attendue (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={dcaParams.expected_volatility}
                      onChange={(e) => setDcaParams({ ...dcaParams, expected_volatility: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Rendement attendu (%)</Label>
                    <Input
                      type="number"
                      step="0.1"
                      value={dcaParams.expected_return}
                      onChange={(e) => setDcaParams({ ...dcaParams, expected_return: parseFloat(e.target.value) || 0 })}
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
                  <CardTitle>Resultats DCA</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-purple-500/10">
                      <p className="text-sm text-muted-foreground">Total investi</p>
                      <p className="text-2xl font-bold">{formatCurrency(dcaResult.total_invested)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-green-500/10">
                      <p className="text-sm text-muted-foreground">Valeur finale</p>
                      <p className="text-2xl font-bold">{formatCurrency(dcaResult.final_value)}</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 rounded-lg bg-blue-500/10">
                      <p className="text-sm text-muted-foreground">Prix moyen</p>
                      <p className="text-xl font-bold">{dcaResult.average_cost.toFixed(2)}</p>
                    </div>
                    <div className="text-center p-4 rounded-lg bg-orange-500/10">
                      <p className="text-sm text-muted-foreground">Rendement</p>
                      <p className={`text-xl font-bold ${dcaResult.return_percent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {dcaResult.return_percent >= 0 ? '+' : ''}{dcaResult.return_percent.toFixed(2)}%
                      </p>
                    </div>
                  </div>

                  <div className="p-4 rounded-lg bg-muted">
                    <p className="text-sm text-muted-foreground mb-1">Unites accumulees</p>
                    <p className="text-lg font-medium">{dcaResult.total_units.toFixed(4)} unites</p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {dcaResult && (
            <Card>
              <CardHeader>
                <CardTitle>Evolution DCA</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsLineChart data={dcaResult.projections}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="period" />
                      <YAxis yAxisId="left" tickFormatter={(v) => `${v.toFixed(0)}`} />
                      <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                      <Tooltip />
                      <Legend />
                      <Line
                        yAxisId="left"
                        type="monotone"
                        dataKey="price"
                        name="Prix"
                        stroke="#f97316"
                      />
                      <Line
                        yAxisId="right"
                        type="monotone"
                        dataKey="current_value"
                        name="Valeur"
                        stroke="#22c55e"
                      />
                      <Line
                        yAxisId="right"
                        type="monotone"
                        dataKey="total_invested"
                        name="Investi"
                        stroke="#a855f7"
                        strokeDasharray="5 5"
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
