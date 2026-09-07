import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { TabsContent } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Calculator, Info, Loader2, Save } from 'lucide-react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import type { DCAResult } from '@/types/simulations'

export interface DcaParams {
  total_amount: number
  frequency: string
  duration_months: number
  expected_volatility: number
  expected_return: number
}

interface Props {
  params: DcaParams
  setParams: (p: DcaParams) => void
  resultat: DCAResult | null
  mutation: { mutate: (p: DcaParams) => void; isPending: boolean }
  formatCurrency: (v: number) => string
  onSauvegarder: () => void
}

/**
 * Onglet DCA — investissement progressif contre achat en une fois.
 *
 * Les taux partent en **pourcentages**, sans conversion : l'endpoint
 * `simulate_dca` divise lui-meme par 100. C'est la convention de trois des
 * quatre onglets ; seul FIRE convertit cote client. Uniformiser ici
 * diviserait les taux deux fois.
 */
export default function DcaTab({
  params,
  setParams,
  resultat,
  mutation,
  formatCurrency,
  onSauvegarder,
}: Props) {
  const { theme, color } = useNivoTheme()
  const donneesGraphique = resultat?.projections

  return (
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
              value={params.total_amount}
              onChange={(e) =>
                setParams({ ...params, total_amount: parseFloat(e.target.value) || 0 })
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="dca-frequency">Fréquence</Label>
              <Select
                value={params.frequency}
                onValueChange={(v) => setParams({ ...params, frequency: v })}
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
                value={params.duration_months}
                onChange={(e) =>
                  setParams({ ...params, duration_months: parseInt(e.target.value) || 0 })
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
                value={params.expected_volatility}
                onChange={(e) =>
                  setParams({ ...params, expected_volatility: parseFloat(e.target.value) || 0 })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dca-expected-return">Rendement attendu (%)</Label>
              <Input
                id="dca-expected-return"
                type="number"
                step="0.1"
                value={params.expected_return}
                onChange={(e) =>
                  setParams({ ...params, expected_return: parseFloat(e.target.value) || 0 })
                }
              />
            </div>
          </div>

          <Button
            className="w-full"
            onClick={() => mutation.mutate(params)}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Calculator className="mr-2 h-4 w-4" />
            )}
            Simuler (500 trajectoires)
          </Button>

          <Button
            variant="outline"
            className="w-full"
            onClick={() => onSauvegarder()}
            disabled={!resultat}
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

      {resultat && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Résultats DCA</CardTitle>
            <CardDescription>
              Simulation sur {resultat.n_paths} trajectoires — médianes et fourchettes p10-p90.
              Aucun chiffre n'est garanti.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 rounded-lg bg-accent/10">
                <p className="text-sm text-muted-foreground">Total investi</p>
                <p className="text-2xl font-serif font-medium">{formatCurrency(resultat.total_invested)}</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-gain/10">
                <p className="text-sm text-muted-foreground">Médiane DCA (valeur finale)</p>
                <p className="text-2xl font-serif font-medium">{formatCurrency(resultat.dca_p50)}</p>
                <p className="text-xs text-muted-foreground">
                  p10-p90 : {formatCurrency(resultat.dca_p10)} – {formatCurrency(resultat.dca_p90)}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 rounded-lg bg-accent/10">
                <p className="text-sm text-muted-foreground">Médiane Lump Sum</p>
                <p className="text-xl font-bold">{formatCurrency(resultat.lumpsum_p50)}</p>
                <p className="text-xs text-muted-foreground">
                  p10-p90 : {formatCurrency(resultat.lumpsum_p10)} – {formatCurrency(resultat.lumpsum_p90)}
                </p>
              </div>
              <div className="text-center p-4 rounded-lg bg-warning/10">
                <p className="text-sm text-muted-foreground">Rendement DCA (médiane)</p>
                <p
                  className={`text-xl font-bold ${resultat.return_percent >= 0 ? 'text-gain' : 'text-loss'}`}
                >
                  {resultat.return_percent >= 0 ? '+' : ''}
                  {resultat.return_percent.toFixed(2)}%
                </p>
              </div>
            </div>

            {/* DCA vs Lump Sum : probabilité sur les mêmes trajectoires */}
            <div className="p-4 rounded-lg bg-muted space-y-2">
              <p className="text-sm font-medium">Médiane DCA vs Médiane Lump Sum</p>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">
                  Dans {resultat.prob_dca_beats_ls.toFixed(0)} % des scénarios simulés
                </span>
                <span className="font-medium">le DCA fait mieux que le Lump Sum</span>
              </div>
              <div className="h-2 bg-background rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent transition-all"
                  style={{ width: `${Math.min(Math.max(resultat.prob_dca_beats_ls, 0), 100)}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Les deux stratégies sont évaluées sur les mêmes {resultat.n_paths} trajectoires de
                rendements — la comparaison est donc à risque identique.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>

    {donneesGraphique && donneesGraphique.length > 0 && (
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>DCA vs Lump Sum</CardTitle>
          <CardDescription>
            Trajectoires médianes sur {resultat?.n_paths ?? 500} scénarios simulés —
            bande p10-p90 pour le DCA
          </CardDescription>
        </CardHeader>
        <CardContent>
          {(() => {
            const cDca = color('--chart-2')
            const cLump = color('--chart-1')
            const cInvested = color('--muted-foreground')
            const dcaData = donneesGraphique
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
  )
}
