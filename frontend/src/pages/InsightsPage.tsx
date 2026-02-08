import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { formatCurrency } from '@/lib/utils'
import { insightsApi } from '@/services/api'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts'
import {
  Receipt,
  Scissors,
  Coins,
  TrendingUp,
  Loader2,
  AlertTriangle,
  DollarSign,
  Calendar,
  Lightbulb,
  Play,
} from 'lucide-react'

type Tab = 'fees' | 'harvest' | 'income' | 'dca'

export default function InsightsPage() {
  const [tab, setTab] = useState<Tab>('fees')

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'fees', label: 'Frais', icon: <Receipt className="h-4 w-4" /> },
    { id: 'harvest', label: 'Tax-Loss', icon: <Scissors className="h-4 w-4" /> },
    { id: 'income', label: 'Revenus passifs', icon: <Coins className="h-4 w-4" /> },
    { id: 'dca', label: 'Backtest DCA', icon: <TrendingUp className="h-4 w-4" /> },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Insights</h1>
        <p className="text-muted-foreground">Analyse avancée de votre portefeuille</p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-2 flex-wrap">
        {tabs.map((t) => (
          <Button
            key={t.id}
            variant={tab === t.id ? 'default' : 'outline'}
            size="sm"
            onClick={() => setTab(t.id)}
          >
            {t.icon}
            <span className="ml-1.5">{t.label}</span>
          </Button>
        ))}
      </div>

      {tab === 'fees' && <FeeAnalysis />}
      {tab === 'harvest' && <TaxLossHarvesting />}
      {tab === 'income' && <PassiveIncome />}
      {tab === 'dca' && <DcaBacktest />}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Fee Analysis Tab
// ──────────────────────────────────────────────────────
function FeeAnalysis() {
  const { data, isLoading } = useQuery({
    queryKey: ['insights-fees'],
    queryFn: insightsApi.getFees,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />

  if (!data || data.total_fees === 0) {
    return <EmptyState message="Aucun frais enregistré" />
  }

  const monthlyData = Object.entries(data.by_month as Record<string, number>).map(([month, value]) => ({
    month,
    fees: value,
  }))

  const exchangeData = Object.entries(data.by_exchange as Record<string, number>).map(([name, value]) => ({
    name,
    fees: value,
  }))

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total des frais</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">{formatCurrency(data.total_fees)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_transactions_with_fees} transactions</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Moyenne mensuelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(data.avg_monthly_fee)}</div>
            <p className="text-xs text-muted-foreground">par mois</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Top exchange</CardTitle>
          </CardHeader>
          <CardContent>
            {exchangeData.length > 0 ? (
              <>
                <div className="text-2xl font-bold">{exchangeData[0].name}</div>
                <p className="text-xs text-muted-foreground">{formatCurrency(exchangeData[0].fees)}</p>
              </>
            ) : (
              <div className="text-muted-foreground">—</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Frais par mois</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => `${v}€`} tick={{ fontSize: 11 }} />
                  <RechartsTooltip formatter={(v: number) => formatCurrency(v)} />
                  <Bar dataKey="fees" fill="#ef4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Frais par exchange</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {exchangeData.map((item) => (
                <div key={item.name} className="flex items-center justify-between">
                  <span className="text-sm font-medium">{item.name}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-32 h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-red-500 rounded-full"
                        style={{ width: `${Math.min(100, (item.fees / data.total_fees) * 100)}%` }}
                      />
                    </div>
                    <span className="text-sm font-mono w-20 text-right">{formatCurrency(item.fees)}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Tax-Loss Harvesting Tab
// ──────────────────────────────────────────────────────
function TaxLossHarvesting() {
  const { data, isLoading } = useQuery({
    queryKey: ['insights-harvest'],
    queryFn: insightsApi.getTaxLossHarvesting,
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />

  if (!data || data.nb_candidates === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <TrendingUp className="h-12 w-12 mx-auto text-green-500 mb-3" />
          <h3 className="text-lg font-semibold">Aucune opportunité</h3>
          <p className="text-muted-foreground text-sm mt-1">
            Toutes vos positions sont en plus-value. Pas de tax-loss harvesting possible.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Moins-values totales</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-500">{formatCurrency(data.total_harvestable)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_candidates} positions</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Economie d'impôt estimée</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">{formatCurrency(data.estimated_tax_saving)}</div>
            <p className="text-xs text-muted-foreground">Flat tax 30%</p>
          </CardContent>
        </Card>
        <Card className="border-yellow-500/20 bg-yellow-500/5">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-1">
              <Lightbulb className="h-4 w-4 text-yellow-500" />
              Conseil
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">{data.note}</p>
          </CardContent>
        </Card>
      </div>

      {/* Opportunities table */}
      <Card>
        <CardHeader>
          <CardTitle>Opportunités de harvesting</CardTitle>
          <CardDescription>Positions en moins-value pouvant réduire votre impôt</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-2">Actif</th>
                  <th className="text-right p-2">PRU</th>
                  <th className="text-right p-2">Prix actuel</th>
                  <th className="text-right p-2">Valeur</th>
                  <th className="text-right p-2">Moins-value</th>
                  <th className="text-right p-2">%</th>
                  <th className="text-right p-2">Eco. impôt</th>
                </tr>
              </thead>
              <tbody>
                {data.opportunities.map((op: Record<string, number | string>) => (
                  <tr key={op.symbol as string} className="border-b last:border-b-0">
                    <td className="p-2">
                      <span className="font-medium">{op.symbol}</span>
                      <Badge variant="outline" className="ml-1 text-xs">{op.asset_type}</Badge>
                    </td>
                    <td className="text-right p-2">{formatCurrency(op.avg_buy_price as number)}</td>
                    <td className="text-right p-2">{formatCurrency(op.current_price as number)}</td>
                    <td className="text-right p-2">{formatCurrency(op.current_value as number)}</td>
                    <td className="text-right p-2 text-red-500 font-medium">{formatCurrency(op.unrealized_loss as number)}</td>
                    <td className="text-right p-2 text-red-500">{(op.unrealized_loss_pct as number).toFixed(1)}%</td>
                    <td className="text-right p-2 text-green-500">{formatCurrency(op.potential_tax_saving as number)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Passive Income Tab
// ──────────────────────────────────────────────────────
function PassiveIncome() {
  const { data, isLoading } = useQuery({
    queryKey: ['insights-income'],
    queryFn: () => insightsApi.getPassiveIncome(),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) return <Loader />

  if (!data || data.nb_events === 0) {
    return <EmptyState message="Aucun revenu passif enregistré (staking, airdrops)" />
  }

  const monthlyData = Object.entries(data.by_month as Record<string, number>).map(([month, value]) => ({
    month,
    income: value,
  }))

  const typeLabels: Record<string, string> = {
    staking_reward: 'Staking',
    airdrop: 'Airdrops',
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total revenus passifs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">{formatCurrency(data.total_income)}</div>
            <p className="text-xs text-muted-foreground">{data.nb_events} versements</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Moyenne mensuelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(data.avg_monthly)}</div>
            <p className="text-xs text-muted-foreground">par mois</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Projection annuelle</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-500">{formatCurrency(data.projected_annual)}</div>
            <p className="text-xs text-muted-foreground">basé sur les 3 derniers mois</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Revenus par mois</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => `${v}€`} tick={{ fontSize: 11 }} />
                  <RechartsTooltip formatter={(v: number) => formatCurrency(v)} />
                  <Bar dataKey="income" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Par type</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {Object.entries(data.by_type as Record<string, number>).map(([type, value]) => (
                <div key={type} className="flex items-center justify-between">
                  <span className="text-sm font-medium">{typeLabels[type] || type}</span>
                  <span className="text-sm font-mono text-green-500">{formatCurrency(value)}</span>
                </div>
              ))}
              {Object.keys(data.by_asset as Record<string, number>).length > 0 && (
                <>
                  <div className="border-t pt-3 mt-3">
                    <p className="text-xs text-muted-foreground mb-2">Par actif :</p>
                    {Object.entries(data.by_asset as Record<string, number>).map(([sym, val]) => (
                      <div key={sym} className="flex items-center justify-between py-1">
                        <span className="text-sm">{sym}</span>
                        <span className="text-xs font-mono">{formatCurrency(val)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────
// DCA Backtest Tab
// ──────────────────────────────────────────────────────
function DcaBacktest() {
  const [symbol, setSymbol] = useState('BTC')
  const [assetType, setAssetType] = useState('crypto')
  const [amount, setAmount] = useState(100)
  const [startYear, setStartYear] = useState(2021)
  const [started, setStarted] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['insights-dca', symbol, assetType, amount, startYear],
    queryFn: () => insightsApi.backtestDca(symbol, assetType, amount, startYear),
    enabled: started,
    staleTime: 10 * 60 * 1000,
  })

  const handleRun = () => {
    setStarted(true)
    refetch()
  }

  const chartData = data?.monthly_history?.map((m: { month: string; invested: number; value: number }) => ({
    month: m.month,
    invested: m.invested,
    value: m.value,
  })) || []

  return (
    <div className="space-y-4">
      {/* Config form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5" />
            Configuration du backtest DCA
          </CardTitle>
          <CardDescription>
            Simulez un investissement mensuel automatique sur un actif
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-5">
            <div>
              <Label>Symbole</Label>
              <Input value={symbol} onChange={(e) => { setSymbol(e.target.value.toUpperCase()); setStarted(false) }} placeholder="BTC" />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={assetType} onValueChange={(v) => { setAssetType(v); setStarted(false) }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="crypto">Crypto</SelectItem>
                  <SelectItem value="stock">Action</SelectItem>
                  <SelectItem value="etf">ETF</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Montant/mois (EUR)</Label>
              <Input type="number" value={amount} onChange={(e) => { setAmount(+e.target.value); setStarted(false) }} min={1} />
            </div>
            <div>
              <Label>Depuis</Label>
              <Input type="number" value={startYear} onChange={(e) => { setStartYear(+e.target.value); setStarted(false) }} min={2010} max={2025} />
            </div>
            <div className="flex items-end">
              <Button onClick={handleRun} disabled={isLoading} className="w-full">
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4 mr-1" />}
                Lancer
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {data && !data.error && (
        <>
          <div className="grid gap-4 grid-cols-2 sm:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Total investi</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">{formatCurrency(data.total_invested)}</div>
                <p className="text-xs text-muted-foreground">{data.nb_months} mois</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Valeur actuelle</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.gain_loss >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {formatCurrency(data.current_value)}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Plus-value</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.gain_loss >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {data.gain_loss >= 0 ? '+' : ''}{formatCurrency(data.gain_loss)}
                </div>
                <p className="text-xs text-muted-foreground">{data.gain_loss_pct >= 0 ? '+' : ''}{data.gain_loss_pct}%</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Prix moyen</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xl font-bold">{formatCurrency(data.avg_buy_price)}</div>
                <p className="text-xs text-muted-foreground">vs {formatCurrency(data.current_price)} actuel</p>
              </CardContent>
            </Card>
          </div>

          {chartData.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Evolution : investissement vs valeur</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="dcaValue" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                      <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k€`} tick={{ fontSize: 11 }} />
                      <RechartsTooltip formatter={(v: number) => formatCurrency(v)} />
                      <Area type="monotone" dataKey="invested" stroke="#94a3b8" strokeWidth={2} strokeDasharray="6 3" fillOpacity={0} name="Investi" />
                      <Area type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#dcaValue)" name="Valeur" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {data?.error && (
        <Card className="border-red-500/20">
          <CardContent className="py-6 text-center">
            <AlertTriangle className="h-8 w-8 mx-auto text-red-500 mb-2" />
            <p className="text-sm text-red-500">{data.error}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────
// Shared components
// ──────────────────────────────────────────────────────
function Loader() {
  return (
    <div className="flex items-center justify-center h-48">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <Card>
      <CardContent className="py-12 text-center">
        <DollarSign className="h-12 w-12 mx-auto text-muted-foreground mb-3" />
        <p className="text-muted-foreground">{message}</p>
      </CardContent>
    </Card>
  )
}
