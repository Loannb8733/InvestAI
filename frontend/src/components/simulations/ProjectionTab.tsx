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
import { LineChart, Loader2, Save, TrendingUp } from 'lucide-react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import { INFLATION_BY_CURRENCY } from '@/components/simulations/inflation'
import type { ProjectionResult } from '@/types/simulations'

export interface ProjectionParams {
  years: number
  expected_return: number
  expense_ratio: number
  monthly_contribution: number
  inflation_rate: number
}

interface Props {
  params: ProjectionParams
  setParams: (p: ProjectionParams) => void
  resultat: ProjectionResult | null
  mutation: { mutate: (p: ProjectionParams) => void; isPending: boolean }
  formatCurrency: (v: number) => string
  userCurrency: string
  onSauvegarder: () => void
}

/**
 * Onglet Projection — valeur du portefeuille annee par annee, nominale et reelle.
 *
 * Les parametres partent **tels quels** : `expected_return: 7` signifie 7 %, et
 * l'endpoint le valide en `ge=-20, le=50`. Le convertir en 0.07 pour
 * ressembler a l'onglet FIRE donnerait une projection a 0,07 %.
 */
export default function ProjectionTab({
  params,
  setParams,
  resultat,
  mutation,
  formatCurrency,
  userCurrency,
  onSauvegarder,
}: Props) {
  const { theme, color } = useNivoTheme()

  return (
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
                value={params.years}
                onChange={(e) =>
                  setParams({ ...params, years: parseInt(e.target.value) || 0 })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="projection-expected-return">Rendement annuel (%)</Label>
              <Input
                id="projection-expected-return"
                type="number"
                step="0.1"
                value={params.expected_return}
                onChange={(e) =>
                  setParams({ ...params, expected_return: parseFloat(e.target.value) || 0 })
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
                value={params.expense_ratio}
                onChange={(e) =>
                  setParams({ ...params, expense_ratio: parseFloat(e.target.value) || 0 })
                }
              />
              <p className="text-xs text-muted-foreground">Déduit du rendement brut</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="projection-monthly-contribution">Contribution mensuelle</Label>
              <Input
                id="projection-monthly-contribution"
                type="number"
                value={params.monthly_contribution}
                onChange={(e) =>
                  setParams({
                    ...params,
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
                value={params.inflation_rate}
                onChange={(e) =>
                  setParams({ ...params, inflation_rate: parseFloat(e.target.value) || 0 })
                }
                className="flex-1"
              />
              <Select
                onValueChange={(currency) => {
                  const info = INFLATION_BY_CURRENCY[currency]
                  if (info) setParams({ ...params, inflation_rate: info.rate })
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
            onClick={() => mutation.mutate(params)}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <TrendingUp className="mr-2 h-4 w-4" />
            )}
            Projeter
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
        </CardContent>
      </Card>

      {resultat && (
        <Card elevation="raised">
          <CardHeader>
            <CardTitle>Résultats de la projection</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 rounded-lg bg-accent/10">
                <p className="text-sm text-muted-foreground">Valeur finale</p>
                <p className="text-2xl font-serif font-medium">{formatCurrency(resultat.final_value)}</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-gain/10">
                <p className="text-sm text-muted-foreground">Valeur réelle (inflation)</p>
                <p className="text-2xl font-serif font-medium">{formatCurrency(resultat.real_final_value)}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 rounded-lg bg-accent/10">
                <p className="text-sm text-muted-foreground">Contributions totales</p>
                <p className="text-xl font-bold">{formatCurrency(resultat.total_contributions)}</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-warning/10">
                <p className="text-sm text-muted-foreground">Gains totaux</p>
                <p className="text-xl font-bold text-gain">
                  +{formatCurrency(resultat.total_returns)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>

    {resultat && (
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Évolution du portefeuille</CardTitle>
        </CardHeader>
        <CardContent>
          {(() => {
            const cNominal = color('--chart-5')
            const cReal = color('--chart-3')
            const cContrib = color('--chart-2')
            const projData = resultat.projections
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
  )
}
