import { useMemo } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { TabsContent } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Calculator,
  CheckCircle,
  Clock,
  DollarSign,
  Flame,
  Info,
  Loader2,
  Percent,
  Save,
  Target,
} from 'lucide-react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import { INFLATION_BY_CURRENCY } from '@/components/simulations/inflation'
import type { FIREProbResult } from '@/types/simulations'

export interface FireParams {
  current_portfolio_value: number
  monthly_contribution: number | null
  monthly_expenses: number
  expected_annual_return: number | null
  annual_volatility: number | null
  inflation_rate: number
  withdrawal_rate: number
  index_contributions: boolean
  years_horizon: number
}

interface Props {
  params: FireParams
  setParams: (maj: FireParams | ((prev: FireParams) => FireParams)) => void
  resultat: FIREProbResult | null
  mutation: { mutate: (p: FireParams) => void; isPending: boolean }
  valeurPortefeuille: number
  formatCurrency: (v: number) => string
  userCurrency: string
  onSauvegarder: () => void
}

/**
 * Onglet FIRE — probabilite d'atteindre l'independance financiere.
 *
 * Le seul des quatre onglets a convertir les taux avant l'envoi : ce que
 * l'utilisateur lit en pourcentages (4 %) part en decimales (0.04), et les
 * depenses mensuelles saisies deviennent des depenses annuelles. Un champ
 * laisse a `null` est **omis** du payload plutot qu'envoye a zero — c'est ainsi
 * que le backend sait qu'il doit appliquer le profil investisseur, et qu'il
 * l'annonce en retour dans `assumptions.defaults_from`.
 */
export default function FireTab({
  params,
  setParams,
  resultat,
  mutation,
  valeurPortefeuille,
  formatCurrency,
  userCurrency,
  onSauvegarder,
}: Props) {
  const { theme, color } = useNivoTheme()
  const livePortfolioValue = valeurPortefeuille

  // Champs que le backend a tires du profil investisseur (badge dans l'UI).
  const defautsDuProfil = useMemo(() => {
    const from = resultat?.assumptions.defaults_from
    if (!from) return []
    return Object.entries(from)
      .filter(([, source]) => source.includes('profil investisseur'))
      .map(([field]) => field)
  }, [resultat])

  return (
  <TabsContent value="fire" className="space-y-6">
    <div className="grid gap-6 lg:grid-cols-2">
      <Card elevation="raised">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Flame className="h-5 w-5 text-warning" />
            Calculateur FIRE probabiliste
            {defautsDuProfil.length > 0 && (
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
                  value={params.current_portfolio_value}
                  onChange={(e) =>
                    setParams({ ...params, current_portfolio_value: parseFloat(e.target.value) || 0 })
                  }
                />
                {livePortfolioValue > 0 &&
                  params.current_portfolio_value !== Math.round(livePortfolioValue * 100) / 100 && (
                    <button
                      type="button"
                      onClick={() =>
                        setParams({
                          ...params,
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
                value={params.monthly_contribution ?? ''}
                onChange={(e) =>
                  setParams({
                    ...params,
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
              value={params.monthly_expenses}
              onChange={(e) =>
                setParams({ ...params, monthly_expenses: parseFloat(e.target.value) || 0 })
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
                value={params.expected_annual_return ?? ''}
                onChange={(e) =>
                  setParams({
                    ...params,
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
                value={params.annual_volatility ?? ''}
                onChange={(e) =>
                  setParams({
                    ...params,
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
            <div className="space-y-2">
              <Label htmlFor="fire-withdrawal-rate">Taux de retrait (%)</Label>
              <Input
                id="fire-withdrawal-rate"
                type="number"
                step="0.1"
                min={2}
                max={8}
                value={params.withdrawal_rate}
                onChange={(e) =>
                  setParams({ ...params, withdrawal_rate: parseFloat(e.target.value) || 0 })
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
                value={params.years_horizon}
                onChange={(e) =>
                  setParams({ ...params, years_horizon: parseInt(e.target.value) || 0 })
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
                  checked={params.index_contributions}
                  onCheckedChange={(checked) =>
                    setParams({ ...params, index_contributions: checked === true })
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
            onClick={() => mutation.mutate(params)}
            disabled={mutation.isPending || params.monthly_expenses <= 0}
          >
            {mutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Calculator className="mr-2 h-4 w-4" />
            )}
            Simuler (1 000 trajectoires)
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
            <CardTitle>Résultats FIRE</CardTitle>
            <CardDescription>
              Simulation sur {resultat.n_paths.toLocaleString('fr-FR')} trajectoires — le passé
              ne préjuge pas des performances futures.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Headline probabiliste */}
            <div className="text-center p-5 rounded-lg bg-warning/10">
              <Flame className="h-8 w-8 mx-auto text-warning mb-2" />
              <p className="text-3xl font-serif font-medium">
                {(resultat.prob_at_horizon * 100).toFixed(0)} % de chances d'être FIRE
              </p>
              <p className="text-sm text-muted-foreground">
                d'ici {resultat.prob_by_year[resultat.prob_by_year.length - 1]?.year}
              </p>
            </div>

            <div className="text-center p-4 rounded-lg bg-accent/10">
              <Clock className="h-6 w-6 mx-auto text-accent mb-1" />
              <p className="text-sm text-muted-foreground">Année FIRE médiane</p>
              <p className="text-2xl font-serif font-medium">
                {resultat.fire_year_p50 ?? 'au-delà de l’horizon'}
              </p>
              <p className="text-xs text-muted-foreground">
                optimiste {resultat.fire_year_p10 ?? '—'} · prudent{' '}
                {resultat.fire_year_p90 ?? 'au-delà de l’horizon'}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 rounded-lg bg-accent/10">
                <Target className="h-6 w-6 mx-auto text-accent mb-1" />
                <p className="text-sm text-muted-foreground">Nombre FIRE (aujourd'hui)</p>
                <p className="text-xl font-serif font-medium">
                  {formatCurrency(resultat.fire_number_today)}
                </p>
                <p className="text-xs text-muted-foreground">indexé sur l'inflation ensuite</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-gain/10">
                <DollarSign className="h-6 w-6 mx-auto text-gain mb-1" />
                <p className="text-sm text-muted-foreground">Valeur finale médiane</p>
                <p className="text-xl font-serif font-medium">
                  {formatCurrency(resultat.final_value_p50)}
                </p>
                <p className="text-xs text-muted-foreground">
                  p10-p90 : {formatCurrency(resultat.final_value_p10)} –{' '}
                  {formatCurrency(resultat.final_value_p90)}
                </p>
              </div>
            </div>

            {/* Survie post-FIRE (test Trinity) */}
            <div
              className={`p-4 rounded-lg ${resultat.survival_prob_30y < 0.8 ? 'bg-loss/10' : 'bg-gain/10'}`}
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium flex items-center gap-1.5">
                  <Percent className="h-4 w-4" />
                  Survie post-FIRE : {(resultat.survival_prob_30y * 100).toFixed(1)} % sur 30
                  ans de retraits
                </p>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Simulation séparée façon Trinity study : départ au nombre FIRE, retraits de vos
                dépenses indexées sur l'inflation pendant 30 ans, sans aucune épargne. C'est le
                pourcentage de trajectoires où le capital n'est jamais épuisé.
              </p>
            </div>

            {resultat.prob_by_year[0]?.prob === 1 && (
              <div className="flex items-center gap-2 p-4 rounded-lg bg-gain/20 text-gain">
                <CheckCircle className="h-5 w-5" />
                <span className="font-medium">
                  Félicitations ! Votre portefeuille atteint déjà le nombre FIRE.
                </span>
              </div>
            )}

            {(() => {
              const progress = Math.min(
                (resultat.assumptions.current_value / resultat.fire_number_today) * 100,
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
    {resultat && (
      <Card elevation="raised">
        <CardHeader>
          <CardTitle>Probabilité d'être FIRE, année par année</CardTitle>
          <CardDescription>
            Probabilité CUMULÉE d'avoir atteint le nombre FIRE (une fois atteint, l'état est
            acquis) — {resultat.n_paths.toLocaleString('fr-FR')} trajectoires simulées.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {(() => {
            const cProb = color('--chart-1')
            const probData = resultat.prob_by_year
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
    {resultat && (
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
            const fireData = resultat.median_path
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
    {resultat && (
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
            const a = resultat.assumptions
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
                  constantes). Simulation sur {resultat.n_paths.toLocaleString('fr-FR')}{' '}
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
  )
}
