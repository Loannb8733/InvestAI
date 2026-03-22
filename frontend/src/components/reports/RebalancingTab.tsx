import { useState, useMemo, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/hooks/use-toast'
import { reportsApi } from '@/services/api'
import { formatCurrency } from '@/lib/utils'
import { CRYPTO_CLASS_LABELS, CRYPTO_CLASS_COLORS } from '@/lib/constants'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import {
  ArrowRightLeft,
  TrendingDown,
  TrendingUp,
  FileText,
  Loader2,
  Scale,
  AlertTriangle,
} from 'lucide-react'

interface RebalanceOrder {
  category: string
  action: 'buy' | 'sell'
  amount_eur: number
  current_pct: number
  target_pct: number
  drift_pct: number
  estimated_gain: number
  estimated_tax: number
}

interface RebalancingData {
  total_value: number
  categories: Array<{
    category: string
    label: string
    current_value: number
    current_pct: number
    target_pct: number
    drift_pct: number
    drift_eur: number
  }>
  orders: RebalanceOrder[]
  total_sell_amount: number
  total_buy_amount: number
  total_estimated_gain: number
  total_estimated_tax: number
  hhi_before: number
  hhi_after: number
}

const CATEGORY_KEYS = ['L1', 'L2', 'DeFi', 'Stable', 'Meme', 'Other'] as const

const DEFAULT_TARGETS: Record<string, number> = {
  L1: 50,
  L2: 10,
  DeFi: 15,
  Stable: 15,
  Meme: 5,
  Other: 5,
}

export default function RebalancingTab() {
  const { toast } = useToast()
  const [targets, setTargets] = useState<Record<string, number>>(DEFAULT_TARGETS)
  const [data, setData] = useState<RebalancingData | null>(null)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)

  const totalPct = useMemo(
    () => Object.values(targets).reduce((s, v) => s + v, 0),
    [targets]
  )

  const isValid = totalPct === 100

  const updateTarget = useCallback((key: string, value: number) => {
    setTargets((prev) => ({ ...prev, [key]: Math.max(0, Math.min(100, value)) }))
  }, [])

  const handleCompute = async () => {
    if (!isValid) return
    setLoading(true)
    try {
      const allocations: Record<string, number> = {}
      for (const [k, v] of Object.entries(targets)) {
        if (v > 0) allocations[k] = v / 100
      }
      const result = await reportsApi.getRebalancingReport(allocations)
      setData(result)
    } catch {
      toast({ title: 'Erreur lors du calcul', variant: 'destructive' })
    } finally {
      setLoading(false)
    }
  }

  const handleExportPDF = async () => {
    if (!isValid) return
    setExporting(true)
    try {
      const allocations: Record<string, number> = {}
      for (const [k, v] of Object.entries(targets)) {
        if (v > 0) allocations[k] = v / 100
      }
      const blob = await reportsApi.downloadRebalancingPDF(allocations)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `rapport_reequilibrage_${new Date().toISOString().split('T')[0]}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast({ title: 'Rapport PDF téléchargé' })
    } catch {
      toast({ title: 'Erreur lors de l\'export', variant: 'destructive' })
    } finally {
      setExporting(false)
    }
  }

  const chartData = useMemo(() => {
    if (!data) return []
    return data.categories.map((cat) => ({
      name: CRYPTO_CLASS_LABELS[cat.category] || cat.category,
      category: cat.category,
      Actuel: cat.current_pct,
      Cible: cat.target_pct,
    }))
  }, [data])

  return (
    <div className="space-y-6">
      {/* Target allocation inputs */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Scale className="h-5 w-5" />
            Allocation cible
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {CATEGORY_KEYS.map((key) => (
              <div key={key} className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full inline-block"
                      style={{ backgroundColor: CRYPTO_CLASS_COLORS[key] || '#64748B' }}
                    />
                    {CRYPTO_CLASS_LABELS[key] || key}
                  </label>
                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      value={targets[key]}
                      onChange={(e) => updateTarget(key, parseInt(e.target.value) || 0)}
                      className="w-16 h-8 text-right text-sm"
                    />
                    <span className="text-sm text-muted-foreground">%</span>
                  </div>
                </div>
                <Slider
                  value={[targets[key]]}
                  onValueChange={([v]) => updateTarget(key, v)}
                  max={100}
                  step={1}
                  className="cursor-pointer"
                />
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between pt-2 border-t">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Total :</span>
              <Badge variant={isValid ? 'default' : 'destructive'}>
                {totalPct}%
              </Badge>
              {!isValid && (
                <span className="text-sm text-destructive flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  Doit être 100%
                </span>
              )}
            </div>
            <Button onClick={handleCompute} disabled={!isValid || loading}>
              {loading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <ArrowRightLeft className="h-4 w-4 mr-2" />
              )}
              Calculer
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {data && (
        <>
          {/* Chart: Current vs Target */}
          <Card>
            <CardHeader>
              <CardTitle>Allocation Actuelle vs Cible</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    formatter={(value: number) => [`${value.toFixed(1)}%`]}
                    contentStyle={{
                      backgroundColor: 'hsl(var(--popover))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                  <Bar dataKey="Actuel" fill="#6366F1" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Cible" fill="#10B981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Drift table */}
          <Card>
            <CardHeader>
              <CardTitle>Écarts d'allocation</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2 px-3">Catégorie</th>
                      <th className="text-right py-2 px-3">Valeur</th>
                      <th className="text-right py-2 px-3">Actuel</th>
                      <th className="text-right py-2 px-3">Cible</th>
                      <th className="text-right py-2 px-3">Écart</th>
                      <th className="text-right py-2 px-3">Écart EUR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.categories.map((cat) => (
                      <tr key={cat.category} className="border-b last:border-0">
                        <td className="py-2 px-3 flex items-center gap-2">
                          <span
                            className="w-2.5 h-2.5 rounded-full"
                            style={{ backgroundColor: CRYPTO_CLASS_COLORS[cat.category] || '#64748B' }}
                          />
                          {cat.label}
                        </td>
                        <td className="text-right py-2 px-3">{formatCurrency(cat.current_value)}</td>
                        <td className="text-right py-2 px-3">{cat.current_pct.toFixed(1)}%</td>
                        <td className="text-right py-2 px-3">{cat.target_pct.toFixed(1)}%</td>
                        <td className={`text-right py-2 px-3 font-medium ${
                          Math.abs(cat.drift_pct) < 3
                            ? 'text-green-600'
                            : 'text-red-600'
                        }`}>
                          {cat.drift_pct > 0 ? '+' : ''}{cat.drift_pct.toFixed(1)}%
                        </td>
                        <td className={`text-right py-2 px-3 ${
                          cat.drift_eur > 0 ? 'text-red-600' : 'text-green-600'
                        }`}>
                          {cat.drift_eur > 0 ? '+' : ''}{formatCurrency(cat.drift_eur)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Orders */}
          {data.orders.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Ordres de rééquilibrage suggérés</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3">
                  {data.orders.map((order, i) => (
                    <div
                      key={i}
                      className={`flex items-center justify-between p-3 rounded-lg border ${
                        order.action === 'sell'
                          ? 'border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30'
                          : 'border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/30'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        {order.action === 'sell' ? (
                          <TrendingDown className="h-5 w-5 text-red-600" />
                        ) : (
                          <TrendingUp className="h-5 w-5 text-green-600" />
                        )}
                        <div>
                          <span className="font-medium">
                            {order.action === 'sell' ? 'Vendre' : 'Acheter'}
                          </span>
                          <span className="text-muted-foreground ml-2">
                            {CRYPTO_CLASS_LABELS[order.category] || order.category}
                          </span>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="font-semibold">{formatCurrency(order.amount_eur)}</div>
                        {order.action === 'sell' && order.estimated_tax > 0 && (
                          <div className="text-xs text-muted-foreground">
                            PV latente : {formatCurrency(order.estimated_gain)} · Impôt : {formatCurrency(order.estimated_tax)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Tax impact summary */}
                <div className="grid gap-3 md:grid-cols-4 pt-3 border-t">
                  <div className="text-center">
                    <div className="text-sm text-muted-foreground">Total ventes</div>
                    <div className="text-lg font-semibold text-red-600">
                      {formatCurrency(data.total_sell_amount)}
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-sm text-muted-foreground">Total achats</div>
                    <div className="text-lg font-semibold text-green-600">
                      {formatCurrency(data.total_buy_amount)}
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-sm text-muted-foreground">PV latente estimée</div>
                    <div className="text-lg font-semibold">
                      {formatCurrency(data.total_estimated_gain)}
                    </div>
                  </div>
                  <div className="text-center">
                    <div className="text-sm text-muted-foreground">Coût fiscal (PFU 30%)</div>
                    <div className="text-lg font-semibold text-orange-600">
                      {formatCurrency(data.total_estimated_tax)}
                    </div>
                  </div>
                </div>

                {/* HHI */}
                <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg text-sm">
                  <span>Score de diversification (HHI)</span>
                  <div className="flex items-center gap-4">
                    <span>
                      Avant : <strong>{data.hhi_before.toFixed(0)}</strong>
                    </span>
                    <span className="text-muted-foreground">→</span>
                    <span>
                      Après : <strong className={
                        data.hhi_after < data.hhi_before ? 'text-green-600' : 'text-orange-600'
                      }>{data.hhi_after.toFixed(0)}</strong>
                    </span>
                  </div>
                </div>

                {/* Export */}
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    onClick={handleExportPDF}
                    disabled={exporting}
                  >
                    {exporting ? (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <FileText className="h-4 w-4 mr-2" />
                    )}
                    Exporter en PDF
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {data.orders.length === 0 && (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Votre portefeuille est déjà aligné avec la cible. Aucun rééquilibrage nécessaire.
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
