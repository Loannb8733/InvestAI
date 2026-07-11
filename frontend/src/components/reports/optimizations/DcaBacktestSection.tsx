import { useId, useState } from 'react'
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
import { formatCurrency } from '@/lib/utils'
import { insightsApi } from '@/services/api'
import { queryKeys } from '@/lib/queryKeys'
import SharedEmptyState from '@/components/ui/empty-state'
import StatCard from '@/components/ui/stat-card'
import SpotlightGroup from '@/components/ui/spotlight-group'
import { ResponsiveLine, type LineSeries } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import { AlertTriangle, Calendar, Loader2, Play } from 'lucide-react'

/**
 * Backtest DCA : simulation d'un investissement mensuel automatique sur un
 * actif (config + résultats + courbe investi vs valeur).
 */
export default function DcaBacktestSection() {
  const { theme, color } = useNivoTheme()
  const uid = useId().replace(/:/g, '')
  const [symbol, setSymbol] = useState('BTC')
  const [assetType, setAssetType] = useState('crypto')
  const [amount, setAmount] = useState(100)
  const [startYear, setStartYear] = useState(2021)
  const [started, setStarted] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: queryKeys.insights.dcaBacktest(symbol, assetType, amount, startYear),
    queryFn: () => insightsApi.backtestDca(symbol, assetType, amount, startYear),
    enabled: started,
    staleTime: 10 * 60 * 1000,
  })

  const handleRun = () => {
    if (started) {
      refetch()
    } else {
      setStarted(true)
    }
  }

  const chartData: { month: string; invested: number; value: number }[] =
    data?.monthly_history?.map((m: { month: string; invested: number; value: number }) => ({
      month: m.month,
      invested: m.invested,
      value: m.value,
    })) || []

  const dcaSeries: LineSeries[] = [
    { id: 'invested', data: chartData.map((m) => ({ x: m.month, y: m.invested })) },
    { id: 'value', data: chartData.map((m) => ({ x: m.month, y: m.value })) },
  ]
  const dcaLabels: Record<string, string> = { invested: 'Investi', value: 'Valeur' }
  const dcaColors: Record<string, string> = {
    invested: color('--muted-foreground'),
    value: color('--chart-3'),
  }
  const dcaTickValues = (() => {
    if (chartData.length === 0) return [] as string[]
    const target = Math.min(6, chartData.length)
    const step = Math.max(1, Math.floor(chartData.length / target))
    return chartData.filter((_, i) => i % step === 0).map((m) => m.month)
  })()

  return (
    <div className="space-y-4">
      {/* Config form */}
      <Card elevation="raised">
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
              <Input type="number" value={startYear} onChange={(e) => { setStartYear(+e.target.value); setStarted(false) }} min={2010} max={new Date().getFullYear()} />
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
          <SpotlightGroup className="grid gap-4 grid-cols-2 sm:grid-cols-4">
            <StatCard
              className="spot-card"
              label="Total investi"
              value={data.total_invested}
              format={formatCurrency}
              hint={<>{data.nb_months} mois</>}
            />
            <Card elevation="raised" className="spot-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Valeur actuelle</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.gain_loss >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {formatCurrency(data.current_value)}
                </div>
              </CardContent>
            </Card>
            <Card elevation="raised" className="spot-card">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Plus-value</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`text-xl font-bold ${data.gain_loss >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {data.gain_loss >= 0 ? '+' : ''}{formatCurrency(data.gain_loss)}
                </div>
                <p className="text-xs text-muted-foreground">{data.gain_loss_pct >= 0 ? '+' : ''}{Number(data.gain_loss_pct).toFixed(2)}%</p>
              </CardContent>
            </Card>
            <StatCard
              className="spot-card"
              label="Prix moyen"
              value={data.avg_buy_price}
              format={formatCurrency}
              hint={<>vs {formatCurrency(data.current_price)} actuel</>}
            />
          </SpotlightGroup>

          {chartData.length > 0 && (
            <Card elevation="raised">
              <CardHeader>
                <CardTitle>Evolution : investissement vs valeur</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-72">
                  <ResponsiveLine
                    data={dcaSeries}
                    theme={theme}
                    margin={{ top: 28, right: 16, bottom: 28, left: 56 }}
                    xScale={{ type: 'point' }}
                    yScale={{ type: 'linear', min: 'auto', max: 'auto', stacked: false }}
                    curve="monotoneX"
                    colors={(s) => dcaColors[s.id as string]}
                    lineWidth={2}
                    enablePoints={false}
                    enableGridX={false}
                    enableArea
                    areaOpacity={1}
                    defs={[
                      {
                        id: `${uid}-value`,
                        type: 'linearGradient',
                        colors: [
                          { offset: 0, color: dcaColors.value, opacity: 0.3 },
                          { offset: 100, color: dcaColors.value, opacity: 0 },
                        ],
                      },
                    ]}
                    fill={[
                      { match: { id: 'value' }, id: `${uid}-value` },
                      { match: { id: 'invested' }, id: 'none' },
                    ]}
                    axisBottom={{ tickSize: 0, tickPadding: 8, tickValues: dcaTickValues }}
                    axisLeft={{ tickSize: 0, tickPadding: 6, format: (v) => `${(Number(v) / 1000).toFixed(0)}k€` }}
                    enableSlices="x"
                    sliceTooltip={({ slice }) => (
                      <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
                        <p className="mb-1.5 text-xs text-muted-foreground">{slice.points[0]?.data.x as string}</p>
                        {slice.points.map((p) => (
                          <div key={p.id} className="flex items-center justify-between gap-4">
                            <span className="flex items-center gap-2">
                              <span
                                className="h-2 w-2 rounded-[2px]"
                                style={{ backgroundColor: dcaColors[p.seriesId as string] }}
                              />
                              <span className="text-xs text-muted-foreground">
                                {dcaLabels[p.seriesId as string] ?? p.seriesId}
                              </span>
                            </span>
                            <span className="font-mono text-sm tabular-nums">
                              {formatCurrency(p.data.y as number)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                    legends={[
                      {
                        anchor: 'top-right',
                        direction: 'row',
                        translateY: -22,
                        itemWidth: 90,
                        itemHeight: 18,
                        symbolSize: 10,
                        symbolShape: 'circle',
                        itemTextColor: color('--muted-foreground'),
                        data: [
                          { id: 'value', label: dcaLabels.value, color: dcaColors.value },
                          { id: 'invested', label: dcaLabels.invested, color: dcaColors.invested },
                        ],
                      },
                    ]}
                    animate
                    motionConfig="gentle"
                  />
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {data?.error && (
        <SharedEmptyState variant="error" icon={AlertTriangle} title={data.error} />
      )}
    </div>
  )
}
