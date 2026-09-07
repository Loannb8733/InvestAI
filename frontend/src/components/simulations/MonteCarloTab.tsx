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
import { BarChart3, Flame, Info, Loader2, Save } from 'lucide-react'
import { ResponsiveLine, type LineSeries, type CommonCustomLayerProps } from '@nivo/line'
import { useNivoTheme } from '@/components/charts/nivo-theme'
import type { MonteCarloData } from '@/types/simulations'

export interface MonteCarloParams {
  horizon: number
  annual_withdrawal_rate: number
  ter_percentage: number
  monthly_withdrawal: number
}

interface Props {
  params: MonteCarloParams
  setParams: (p: MonteCarloParams) => void
  resultat: MonteCarloData | null
  /**
   * Paramètres du dernier calcul, distincts de `params` : les champs restent
   * modifiables après coup sans relancer la simulation. Afficher `params` ferait
   * décrire au résultat des hypothèses qui ne sont pas les siennes.
   */
  applique: MonteCarloParams | null
  mutation: { mutate: (p: MonteCarloParams) => void; isPending: boolean }
  formatCurrency: (v: number) => string
  onSauvegarder: () => void
}

/**
 * Onglet Monte Carlo — distribution des trajectoires du portefeuille.
 *
 * Seul onglet dont l'appel passe des **arguments positionnels** plutôt qu'un
 * objet : `getMonteCarlo(horizon, _, retrait, ter, retraitMensuel)`. Les zéros
 * y deviennent `undefined` (`|| undefined`), ce qui laisse le backend appliquer
 * ses défauts au lieu de forcer un retrait nul.
 */
export default function MonteCarloTab({
  params,
  setParams,
  resultat,
  applique,
  mutation,
  formatCurrency,
  onSauvegarder,
}: Props) {
  const { theme, color } = useNivoTheme()
  const donneesGraphique = resultat
    ? [
        { label: 'P5 (pessimiste)', value: resultat.percentiles.p5, fill: 'oklch(var(--chart-4))' },
        { label: 'P25', value: resultat.percentiles.p25, fill: 'oklch(var(--chart-1))' },
        { label: 'P50 (médian)', value: resultat.percentiles.p50, fill: 'oklch(var(--chart-5))' },
        { label: 'P75', value: resultat.percentiles.p75, fill: 'oklch(var(--chart-3))' },
        { label: 'P95 (optimiste)', value: resultat.percentiles.p95, fill: 'oklch(var(--chart-3))' },
      ]
    : []

  return (
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
              value={String(params.horizon)}
              onValueChange={(v) => setParams({ ...params, horizon: parseInt(v) })}
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
                value={params.annual_withdrawal_rate}
                onChange={(e) =>
                  setParams({ ...params, annual_withdrawal_rate: parseFloat(e.target.value) || 0 })
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
                value={params.ter_percentage}
                onChange={(e) =>
                  setParams({ ...params, ter_percentage: parseFloat(e.target.value) || 0 })
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
              value={params.monthly_withdrawal}
              onChange={(e) =>
                setParams({ ...params, monthly_withdrawal: parseFloat(e.target.value) || 0 })
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
            onClick={() => mutation.mutate(params)}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <BarChart3 className="mr-2 h-4 w-4" />
            )}
            Simuler (5 000 chemins)
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
            <CardTitle>Résultats Monte Carlo</CardTitle>
            <CardDescription>
              {resultat.simulations.toLocaleString()} simulations sur {resultat.horizon_days} jours
              {applique && applique.monthly_withdrawal > 0 && (
                <> — avec retraits de {formatCurrency(applique.monthly_withdrawal)}/mois</>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 rounded-lg bg-accent/10">
                <p className="text-sm text-muted-foreground">Rendement attendu</p>
                <p
                  className={`text-2xl font-serif font-medium ${resultat.expected_return >= 0 ? 'text-gain' : 'text-loss'}`}
                >
                  {resultat.expected_return >= 0 ? '+' : ''}
                  {resultat.expected_return.toFixed(2)}%
                </p>
              </div>
              <div className="text-center p-4 rounded-lg bg-gain/10">
                <p className="text-sm text-muted-foreground">Prob. gain</p>
                <p className="text-2xl font-serif font-medium">{resultat.prob_positive.toFixed(1)}%</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 rounded-lg bg-loss/10">
                <p className="text-sm text-muted-foreground">Prob. perte &gt;10%</p>
                <p className="text-2xl font-serif font-medium text-loss">{resultat.prob_loss_10.toFixed(1)}%</p>
              </div>
              <div
                className={`text-center p-4 rounded-lg ${resultat.prob_ruin > 20 ? 'bg-loss/20' : 'bg-warning/10'}`}
              >
                <p className="text-sm text-muted-foreground">Prob. ruine</p>
                <p className={`text-2xl font-serif font-medium ${resultat.prob_ruin > 20 ? 'text-loss' : ''}`}>
                  {resultat.prob_ruin.toFixed(1)}%
                </p>
              </div>
            </div>

            {resultat.prob_ruin > 20 && (
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
    {resultat && (
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
              { id: 'mc', data: donneesGraphique.map((d) => ({ x: d.label, y: d.value })) },
            ]
            const DotsLayer = ({ xScale, yScale }: CommonCustomLayerProps<LineSeries>) => {
              const sx = xScale as (v: string) => number
              const sy = yScale as (v: number) => number
              return (
                <>
                  {donneesGraphique.map((d, i) => (
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
            {donneesGraphique.map((d) => (
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
  )
}
